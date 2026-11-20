# Métodos de ajuste de parámetros

## Recomendación para SimOps

No hay un único optimizador que gane en todos los casos. El afinado de navegación tiene evaluaciones costosas, métricas ruidosas, parámetros mixtos y condiciones de seguridad. La estrategia recomendada es un flujo por etapas:

1. **Línea base reproducible:** Latin Hypercube Sampling (LHS) para cubrir mejor cada dimensión con presupuesto fijo; conservar búsqueda aleatoria y barridos pequeños como comparadores. Grid se reserva para espacios discretos muy pequeños.
2. **Ajuste adaptativo:** TPE (Tree-structured Parzen Estimator) como opción inicial para espacios mixtos y discretos. Para espacios pequeños, casi continuos y con ensayos muy caros, añadir más adelante Gaussian-process BO (GPSampler/BoTorch).
3. **Restricciones por separado:** colisión, tasa de éxito, margen mínimo y otros criterios críticos no se compensan con una puntuación media. Se codifican como residuos con convención valor <= 0 factible.
4. **Réplicas y selección:** usar semillas emparejadas en screening; ampliar candidatos prometedores a varias semillas y escenarios. Conservar el frente de Pareto entre factibles.
5. **Confirmación independiente:** ejecutar finalistas en escenarios y semillas hold-out, con más repeticiones y protocolo estadístico fijado antes de ver resultados.
6. **Pruning con cautela:** Hyperband/racing solo cuando exista una fidelidad más barata cuyo ranking prediga el ensayo completo. No truncar una navegación en curso por defecto: colisión y éxito final pueden aparecer tarde.

LHS proporciona un baseline reproducible y visible. TPE propone configuraciones a partir del historial y puede atender varios objetivos y restricciones; estas restricciones guían la búsqueda y no son garantía de seguridad. Los primeros `n_startup_trials` de TPE son exploratorios; si el presupuesto no los supera, el estudio no llega a proponer a partir de resultados previos. Cuando se configura `storage_url`, Optuna persiste el estudio en un backend RDB con heartbeat; para paralelismo se exige un RDB compartido, no SQLite. El core no adquiere dependencias externas y TPE se instala como extra opcional.

## Comparación de métodos

| Método | Cuándo usarlo | Coste / límite | Decisión en SimOps |
|---|---|---|---|
| Grid | Pocos parámetros discretos, verificación exhaustiva | Crece exponencialmente; desperdicia presupuesto en dimensiones menos relevantes | Mantener como futura estrategia pequeña |
| Aleatorio/LHS | Screening reproducible; mezcla de tipos; baseline | No usa resultados previos; al discretizar pueden repetirse valores | LHS se implementa como estrategia nativa |
| Búsqueda por fases/OAT | Interpretación simple, pequeños cambios locales | Puede perder interacciones; depende del orden y del coste agregado | Conservar como baseline de legado, no como default único |
| TPE/Optuna | Evaluaciones caras; mezcla floats/ints/categorías; estudios reanudables | Startup exploratorio; dependencia y versión fijadas; sensibilidad al objetivo/ruido | Implementación opcional, múltiples métricas y restricciones |
| GP Bayesian Optimization | Pocas dimensiones continuas y pocas evaluaciones | Coste de modelo, instalación pesada y fragilidad ante discontinuidad/variables mixtas | Plugin futuro de BoTorch/GPSampler |
| NSGA-II/III | Multiobjetivo, discontinuidades y presupuesto amplio | Usualmente necesita más evaluaciones que BO en problemas caros | Comparador futuro, no default |
| Hyperband / Successive Halving / racing | Corridas divisibles por fidelidad/etapas y puntuación parcial informativa | Puede descartar tarde al mejor si los rankings tempranos no correlacionan | Asignación futura de semillas/escenarios, tras validar fidelidad |
| Morris / Sobol | Detectar parámetros influyentes e interacciones antes de buscar | Sobol puede requerir muchas corridas | Morris como análisis previo opcional; Sobol según presupuesto |
| Safe BO | Experimentos donde ciertas regiones pueden dañar equipo/personas | Garantías dependen del modelo, ruido, conjunto seguro inicial y supuestos | No habilitado en hardware real por esta implementación |

## Implementación añadida

- `src/simops/optimization.py`: especificaciones de parámetros, objetivos, restricciones, observaciones, frente Pareto y estrategia nativa LHS.
- `src/simops/optuna_tpe.py`: plugin opcional TPE con almacenamiento Optuna con heartbeat/reanudación, objetivos múltiples y restricciones explícitas.
- `src/simops/tuning.py`: adapta cada candidato a una campaña persistida del runner, calcula objetivos/restricciones a partir de todas las corridas y escribe el resumen auditable.
- Las evaluaciones de infraestructura inválidas no reciben un valor objetivo ficticio; quedan como trials fallidos y visibles en el resumen.
- Una evaluación funcionalmente fallida del sistema debe ser una evaluación completa con valores medidos (p. ej. no llega o colisiona) y restricciones correspondientes. No debe convertirse en fallo de infraestructura.
- El presupuesto cuenta candidatos; cada candidato expande la misma matriz de escenarios/repeticiones y guarda sus corridas bajo el diario SQLite compartido. Los candidatos con métricas objetivo ausentes o fallos de infraestructura quedan inválidos, sin imputación.

## Ejemplo de integración

~~~python
from simops import (
    ConstraintSpec,
    Direction,
    EvaluationStatus,
    LatinHypercubeSearch,
    ObjectiveSpec,
    ParameterKind,
    ParameterSpec,
    TuningEvaluation,
    TuningSpec,
)
from simops.optuna_tpe import OptunaTPESearch

spec = TuningSpec(
    parameters=(ParameterSpec("gain", ParameterKind.FLOAT, 0.1, 2.0),),
    objectives=(ObjectiveSpec("mission.time_s", Direction.MINIMIZE),),
    constraints=(ConstraintSpec("safety.collisions", "must equal zero"),),
    storage_url="sqlite:///tuning-study.db",  # use a shared PostgreSQL URL for workers > 1
)

def evaluate(parameters):
    # The application runs scenario/seed replications and aggregates them here.
    return TuningEvaluation(
        status=EvaluationStatus.COMPLETE,
        objectives={"mission.time_s": 100.0},
        constraints={"safety.collisions": 0.0},
    )

lhs_result = LatinHypercubeSearch().optimize(spec, evaluate, budget=30)
tpe_result = OptunaTPESearch().optimize(spec, evaluate, budget=30)
~~~

El manifiesto de afinado compone las dimensiones de búsqueda con una campaña real. Por ejemplo, `simops tune examples/nav2-turtlebot3/tuning.json` ejecuta cada candidato LHS mediante el adapter Docker de Nav2 y evalúa las métricas guardadas. `simops tune examples/demo-tuning.json` permite probar el mismo flujo sin descargar simuladores. El presupuesto cuenta candidatos; el coste en simulaciones es candidatos × escenarios × sistemas × repeticiones. Los resultados quedan en SQLite y en `tuning.json`/`tuning.md`.

## Uso responsable de los métodos

El estudio optimiza los agregados que el evaluador devuelve; no toma mensajes de telemetría como muestras independientes. Para resultados ruidosos, el evaluador debe repetir seeds y devolver una estimación por candidato. La validación final vuelve a correr el protocolo completo sobre hold-out.

La exploración TPE/BO aquí es para simulación. No se debe conectar a hardware real sin una extensión de Safe BO revisada, un conjunto inicial seguro, límites independientes y autorización operativa.

## Fuentes

- Bergstra y Bengio, 2012, búsqueda aleatoria como baseline competitivo: [JMLR](https://www.jmlr.org/papers/v13/bergstra12a.html).
- Berkenkamp, Krause y Schoellig, 2023, restricciones independientes para Safe BO en robótica: [artículo de acceso abierto](https://pmc.ncbi.nlm.nih.gov/articles/PMC10485113/).
- Documentación Optuna 5.1 para [TPE](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html), [GPSampler](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.GPSampler.html), [multiobjetivo](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/002_multi_objective.html) y [pruners](https://optuna.readthedocs.io/en/stable/reference/pruners.html).
- Documentación BoTorch para BO multiobjetivo con restricciones: [qNEHVI/qParEGO](https://botorch.org/docs/next/tutorials/constrained_multi_objective_bo).
- Hyperband: [artículo](https://arxiv.org/abs/1603.06560); BOHB: [PMLR](https://proceedings.mlr.press/v80/falkner18a.html).


## Agregación por corrida y seguridad

Los datos se conservan por corrida y por escenario. Cada restricción numérica usa `worst_case` por defecto: máximo para `<=`, mínimo para `>=`, antes de convertirlo a residuo factible. De ese modo, una sola colisión o una sola misión fallida no se disuelve en una media de muchas rutas. Para tasas poblacionales se puede declarar explícitamente `aggregation: "mean"`; escribe el umbral y justifica la tolerancia de fallos. `missing`, `invalid` o cobertura incompleta vuelven la evaluación inválida y no alimentan el optimizador.

Los objetivos aceptan `mean`, `median`, `min`, `max` y `p95`. El resumen de búsqueda guarda métricas y valores por corrida; el informe muestra estado factible y margen de cada restricción para todos los candidatos. La confirmación en hold-out sigue siendo obligatoria para afirmar mejora.
