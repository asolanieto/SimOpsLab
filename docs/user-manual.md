# Manual de usuario de SimOps Lab

Esta guía describe la interfaz local de SimOps Lab. El runner conserva campañas en SQLite, guarda artefactos con SHA-256 y produce informes JSON, Markdown y HTML. Incluye `demo` para comprobar el flujo sin simulador y `nav2-docker`, un adaptador de demostración para Nav2 y TurtleBot3 en Gazebo Sim. El adaptador Nav2 cubre un mapa y una ruta de ejemplo; otros simuladores se conectan mediante plugins de backend.

## Primera búsqueda desde el checkout

Desde la raíz del repositorio, se puede probar el afinado LHS sin instalar el paquete ni descargar un simulador:

```sh
PYTHONPATH=src python3 -m simops tune examples/demo-tuning.json
```

El ejemplo explora tres parámetros en dos escenarios con cuatro semillas y guarda las campañas, `tuning.json` y `tuning.md` bajo `.simops/`. `demo` es sintético: sirve para comprobar el flujo de búsqueda, persistencia e informes, pero no modela Nav2 ni permite sacar conclusiones sobre un robot. Para medir una simulación real, sigue el ejemplo Nav2 más abajo.

## Requisitos e instalación local

- Python 3.11 o posterior.
- No se requieren ROS, Gazebo ni dependencias externas para el núcleo y el CLI.
- Para el ejemplo Nav2: Docker Engine con daemon accesible, Linux `amd64`/x86_64, acceso a GHCR y Ubuntu Archive durante la construcción, y varios GB libres para las imágenes.

Desde la raíz del repositorio:

```sh
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
simops --help
simops backends
```

La instalación editable crea el comando `simops` y permite que el entorno virtual descubra los backends instalados. La base de datos y los informes se crean relativos al directorio desde el que se ejecuta el comando, salvo que se indiquen otras rutas. La instalación estándar necesita que `pip` pueda resolver el backend de construcción definido en `pyproject.toml`.

Construye la imagen de demostración una vez. El Dockerfile parte de Nav2 Lyrical 1.5.3 fijado por digest e instala la versión fijada de la dependencia runtime que la imagen upstream omite:

```sh
docker build -f examples/nav2-turtlebot3/Dockerfile \
  -t simops-lab/nav2-turtlebot3:lyrical-1.5.3-gm1.3.46 .
```

## Flujo de trabajo

1. Escribe un manifiesto JSON.
2. Usa `simops backends` para consultar los adaptadores disponibles.
3. Ejecuta `simops validate manifiesto.json` para comprobar la matriz y la aceptación del backend.
4. Ejecuta `simops plan manifiesto.json` para inspeccionar las corridas que se generarán.
5. Ejecuta `simops run manifiesto.json` para guardar la campaña y lanzar las corridas.
6. Consulta el estado con `simops status ID` y reanuda trabajo incompleto con `simops resume ID`.
7. Usa `simops report ID` para regenerar los informes desde los datos guardados.
8. Opcionalmente, define una búsqueda de parámetros y ejecútala con `simops tune ajuste.json`.

`plan` expande la matriz, pero no valida el backend ni guarda la campaña. `validate` sí carga el backend y llama a su validación para cada corrida, pero tampoco inicia ni persiste una ejecución.

## Manifiesto JSON v0.1.0

El cargador acepta JSON con `schema_version`, `backend` y `campaign`. Rechaza claves desconocidas. Las configuraciones y parámetros son objetos JSON; no se admite el ejemplo YAML de planificación que acompaña al repositorio.

Ejemplo ejecutable con el backend `demo`:

```json
{
  "schema_version": "0.1.0",
  "backend": "demo",
  "campaign": {
    "campaign_id": "demo-navegacion-01",
    "title": "Prueba sintética de navegación",
    "systems": ["controlador-a"],
    "scenarios": [
      {
        "scenario_id": "facil",
        "parameters": {"difficulty": 0.2, "distance_m": 8.0}
      },
      {
        "scenario_id": "dificil",
        "parameters": {"difficulty": 0.7, "distance_m": 12.0}
      }
    ],
    "configurations": [
      {
        "configuration_id": "base",
        "values": {
          "max_speed_mps": 0.45,
          "controller_gain": 1.0,
          "inflation_radius_m": 0.45
        }
      },
      {
        "configuration_id": "prudente",
        "values": {
          "max_speed_mps": 0.35,
          "controller_gain": 1.2,
          "inflation_radius_m": 0.55
        }
      }
    ],
    "repetitions": 3,
    "seeds": [11, 22, 33],
    "max_parallel": 1,
    "max_infrastructure_retries": 1,
    "wall_time_budget_s": 600,
    "metadata": {"purpose": "tutorial"}
  }
}
```

La matriz produce el producto `systems × scenarios × configurations × repetitions`: este ejemplo planifica 12 corridas. Los IDs de corrida se derivan de forma determinista de la identidad y los parámetros de cada corrida.

Campos y reglas:

- `schema_version`: actualmente debe ser exactamente `"0.1.0"`.
- `backend`: nombre del backend instalado, por ejemplo `demo`.
- `campaign_id` y `title`: cadenas no vacías. El ID identifica la campaña en la base local.
- `systems`: lista no vacía de identificadores únicos y no vacíos.
- `scenarios`: lista no vacía de objetos con `scenario_id` y, opcionalmente, `parameters` (objeto; por defecto `{}`).
- `configurations`: lista no vacía de objetos con `configuration_id` y, opcionalmente, `values` (objeto; por defecto `{}`).
- `repetitions`: entero de al menos 1.
- `seeds`: campo opcional; si aparece, debe contener un entero único por repetición, en el mismo orden. Si se omite, cada corrida tiene `seed: null` y la aleatoriedad queda a cargo del backend.
- `max_parallel`: entero de al menos 1; por defecto 1. Un backend que no declare `thread_safe` no admite valores superiores a 1.
- `max_infrastructure_retries`: cantidad de reintentos adicionales por fallo de infraestructura; entero no negativo, por defecto 0.
- `wall_time_budget_s`: opcional, numérico, finito y mayor que cero. Limita el inicio de corridas nuevas; no termina a la fuerza una llamada al backend que ya está ejecutándose.
- `metadata`: objeto JSON opcional, por defecto `{}`.

El planificador comprueba que los identificadores no estén vacíos ni duplicados, y que los datos sean JSON finito. El backend puede aplicar validaciones de dominio adicionales.

## Comandos del CLI

```sh
simops backends
simops validate campaña.json
simops plan campaña.json
simops plan campaña.json --json
simops run campaña.json
simops status demo-navegacion-01
simops resume demo-navegacion-01
simops report demo-navegacion-01
simops tune examples/demo-tuning.json
simops validate examples/nav2-turtlebot3/campaign.json
simops run examples/nav2-turtlebot3/campaign.json
simops tune examples/nav2-turtlebot3/tuning.json
```

`run`, `resume`, `status`, `report` y `tune` aceptan `--store RUTA`; por defecto usan `.simops/campaigns.sqlite3`. `run`, `resume` y `report` aceptan `--report-dir RUTA`; por defecto usan `.simops/reports`. Cada informe se escribe en un subdirectorio derivado del ID de campaña. `run` y `resume` generan el informe al terminar y muestran las rutas. `report` lo vuelve a generar sin ejecutar corridas. `tune` acepta `--result-dir RUTA`, por defecto `.simops/tunings`.

Al volver a ejecutar el mismo manifiesto con el mismo ID, SimOps conserva los resultados ya terminados y trabaja sobre las corridas incompletas. Si el ID ya existe asociado a otro manifiesto o a otro backend/versión, el registro falla; usa un ID nuevo para una campaña distinta.

`status` imprime JSON con el estado de campaña, backend y versión, huella del manifiesto, estado y número de intentos por corrida, número de fallos de infraestructura, cantidad de eventos y el último evento. El historial completo también se conserva en SQLite, aunque el CLI actual no tiene un comando para listar todos los eventos o los resultados de cada intento.

Si se interrumpe el proceso, `resume` recupera corridas que quedaron marcadas como `running`, las registra como interrumpidas y decide si puede volver a intentarlas. La reanudación usa la especificación guardada; no necesita el manifiesto original. El backend debe seguir instalado y declarar la misma `backend_version` que quedó almacenada. Si la versión cambió, el CLI rechaza la reanudación y pide usar un ID de campaña nuevo.

El runner mantiene un bloqueo del sistema operativo por base SQLite e ID de campaña mientras coordina `run` o `resume`. Dos procesos locales no pueden recuperar o ejecutar a la vez la misma campaña; el segundo espera hasta 30 segundos por el bloqueo y luego informa que se reintente. La base local no coordina hosts distintos.

Al pulsar Ctrl+C durante `run` o `resume`, el CLI activa una señal cooperativa. El backend puede consultar `context.cancellation_requested`; las corridas nuevas se difieren. No existe un comando `cancel` ni una terminación forzada de una ejecución en curso.

## Ejemplo real: Nav2 y TurtleBot3 en Docker

`examples/nav2-turtlebot3/campaign.json` lanza el mapa sandbox incluido en Nav2 con TurtleBot3 Waffle. `examples/nav2-turtlebot3/tuning.json` prueba tres candidatos LHS en dos rutas. Cada candidato ejecuta una navegación headless en su propio contenedor; se ejecutan secuencialmente para aislar DDS y Gazebo. El adaptador combina los parámetros elegidos con el YAML completo por defecto de Nav2 y conserva el log, los overrides y las medidas como artefactos.

Parámetros ajustables en este adaptador:

- `controller.vx_max`: velocidad lineal máxima MPPI, de 0.1 a 0.8 m/s.
- `controller.wz_max`: velocidad angular máxima MPPI, de 0.2 a 2.5 rad/s.
- `controller.temperature`: temperatura MPPI, de 0.05 a 2.0.
- `costmap.inflation_radius_m`: radio de inflación de los costmaps local y global, de 0.25 a 1.0 m.

La ruta usa posición inicial `(-2.0, -0.5)` y meta `(0.0, -0.5)` en el mapa sandbox; se pueden configurar `start_x`, `start_y`, `start_yaw`, `goal_x`, `goal_y`, `goal_yaw` y `timeout_s` (10–600 s). El backend registra el estado de la acción, tiempos de pared y simulado, trayectoria odométrica, rango láser mínimo, picos y tasa de comandos, fracción de saturación, alternancias angulares, aceleración angular RMS, muestras de odometría y latencia hasta el primer comando nulo tras el éxito. El [catálogo](metrics-catalog.md) precisa qué significa cada una. No mide contactos Gazebo, clearance de huella, ground truth ni error de localización; por tanto, no permite afirmar seguridad. El seed del manifiesto no se aplica a este mundo determinista; no debe tratarse como repetición aleatoria.

```sh
simops validate examples/nav2-turtlebot3/campaign.json
simops run examples/nav2-turtlebot3/campaign.json
simops tune examples/nav2-turtlebot3/tuning.json
```

Para ejecutar el manifiesto de ejemplo con TPE en vez de LHS, instala Optuna y usa `examples/nav2-turtlebot3/tuning-tpe.json`:

```sh
python -m pip install -e ".[optimize]"
simops tune examples/nav2-turtlebot3/tuning-tpe.json
```

El presupuesto LHS cuenta candidatos; el ejemplo tiene cuatro navegaciones. Antes de interpretar un ajuste, inspecciona `tuning.md` y `tuning.json`, compara la tasa de éxito y las métricas con la configuración base y confirma cualquier candidato con más escenarios y condiciones distintas. Un resultado de esta ruta no demuestra seguridad ni generalidad para otros mapas o robots.

## Crear e instalar un backend plugin

Los backends de terceros se descubren con entry points de Python del grupo `simops.backends`. En el `pyproject.toml` del paquete adaptador se declara, por ejemplo:

```toml
[project.entry-points."simops.backends"]
mi_simulador = "mi_paquete.backend:Backend"
```

Instala ese paquete en el mismo entorno donde se instaló SimOps. `simops backends` debe mostrar `mi_simulador`; el manifiesto debe indicar exactamente ese nombre. Si dos paquetes reclaman el mismo nombre, la carga falla.

El objeto backend debe proporcionar:

- `backend_id`: igual al nombre del entry point.
- `backend_version`: cadena de versión que identifique la implementación.
- `thread_safe`: booleano declarativo; solo se permite concurrencia mayor que uno cuando es verdadero.
- `validate(run)`: devuelve una secuencia de mensajes de error; una secuencia vacía acepta la corrida.
- `execute(run, context)`: ejecuta una corrida y devuelve `RunResult`.

El entry point puede apuntar a una clase (se instancia sin argumentos) o a un objeto ya creado. `run` es un `RunSpec` con `run_id`, sistema, escenario, configuración, repetición, semilla y sus parámetros. `context` es `ExecutionContext`: contiene número de intento, carpeta de trabajo, almacén de artefactos, fecha límite monotónica opcional y señal cooperativa de cancelación. El backend puede guardar bytes con `context.artifacts.put(nombre, contenido, tipo_mime, versión_esquema)`; recibe una referencia con URI SHA-256, hash y tamaño.

El runner verifica que el resultado corresponda al `run_id`, que tenga un estado terminal, que las métricas sean coherentes y que los artefactos no declaren tamaños negativos. Las excepciones de `execute` se registran como fallos de infraestructura. Para un resultado válido, SimOps añade al campo de procedencia el ID y la versión reales del backend.

## Estados, resultados y reintentos

El estado operativo de una corrida está separado del resultado funcional del sistema:

- Estados definidos para corridas: `planned`, `queued`, `running`, `completed`, `failed_system`, `failed_infrastructure`, `cancelled` e `interrupted`. El runner local pasa normalmente de planificada a ejecución y a un estado terminal; `queued` está definido en el contrato, pero no se persiste como fase de cola en este runner.
- Resultados funcionales: `success`, `failure`, `expected_abort`, `unknown` o `not_applicable`. Por ejemplo, una corrida puede terminar operativamente como `completed` y tener resultado funcional `failure`.
- Estados de campaña producidos por el runner: `running`, `paused`, `failed`, `completed_with_system_failures` o `completed`. `paused` indica que quedan corridas pendientes, por ejemplo por una petición de cancelación o por agotarse el presupuesto. `failed` indica que quedan fallos de infraestructura/interrupciones que no se reintentaron. Los fallos del sistema se reflejan en `completed_with_system_failures`.

Cada intento se conserva en el diario SQLite. Un fallo de infraestructura o una interrupción puede volver a intentarse hasta `max_infrastructure_retries` veces además del primer intento. Los fallos funcionales del sistema no se reintentan automáticamente. Al reanudar, las corridas completas, fallidas del sistema o canceladas se consideran terminales; las de infraestructura/interrumpidas se retoman solo si no se agotó el límite. Un presupuesto vencido impide empezar más corridas; el backend recibe la fecha límite para poder consultarla durante la ejecución.

## Métricas e informes

Las métricas las entrega el backend dentro de `RunResult`; el CLI no implementa un catálogo ni calcula mediciones de simulador. Cada `MetricValue` incluye `metric_id`, valor, unidad opcional, `definition_version` y estado. Los estados admitidos son `observed`, `not_applicable`, `missing` e `invalid`. Un valor observado requiere dato; para los otros estados el valor debe ser `null` y se exige un motivo. La ausencia o invalidez no equivale a cero.

Los informes disponibles son `analysis.json`, `report.md` y `report.html`, generados desde un modelo de análisis común. Agrupan por sistema, escenario y configuración. Presentan corridas planificadas y con resultado, conteos de estados y resultados funcionales, y resumen de métricas:

- Numéricas: cantidad observada/planificada, faltantes, media, mediana, cuartiles, mínimo y máximo.
- Booleanas: cantidad verdadera y proporción sobre valores observados.
- Otros valores: tipo y valores distintos observados.
- También se conservan unidades, versiones de definición, estados no observados y motivos.
- Para éxito, muestran éxitos entre resultados funcionales conocidos e intervalo de Wilson del 95%; excluyen resultados desconocidos/no aplicables y corridas con estado `failed_infrastructure` o `interrupted` de ese denominador.

El JSON es la salida estructurada. El informe declara que describe solo la campaña suministrada y recomienda separar selección de configuración y confirmación en escenarios o semillas distintos. El renderizador actual es resumido: no genera gráficos, PDF ni análisis de comparación entre configuraciones. Tampoco muestra el detalle de todos los intentos en las tablas del informe; para inspección operativa, consulta `status` y conserva la base SQLite.

## Backend `demo` y límites actuales

`demo` es un benchmark sintético determinista con variación pseudoaleatoria basada en la semilla (o en el ID de corrida si no se indica). Emite `task.success`, `task.duration_s`, `safety.collision_count`, `navigation.path_length_m` y `safety.min_clearance_m`. Acepta `max_speed_mps` entre 0.1 y 1.5, `controller_gain` entre 0.2 y 2.5 e `inflation_radius_m` entre 0.05 y 1.0. Los escenarios aceptan `difficulty` entre 0 y 1 y `distance_m` positivo. Si se omiten, usa valores predeterminados.

El backend genera números mediante fórmulas sintéticas; no inicia un simulador, no modela la física, no ejecuta ROS ni describe el rendimiento de un robot. Sus métricas sirven para explorar el flujo del CLI, comprobar formatos y producir un informe de ejemplo. No deben usarse como evidencia sobre un robot ni sobre navegación real.

## Ajuste de parámetros con `tune`

`simops tune` genera candidatos, ejecuta para cada uno la matriz de campañas definida y compara las métricas declaradas. El ejemplo completo está en [examples/demo-tuning.json](../examples/demo-tuning.json). Para usar TPE, instala la dependencia opcional dentro del entorno virtual:

```sh
python -m pip install -e ".[optimize]"
simops tune examples/nav2-turtlebot3/tuning-tpe.json
```

La forma general del manifiesto es un objeto JSON con `schema_version: "0.1.0"`, `backend` y `tuning`. En `tuning`:

- `tuning_id` y `title` identifican la búsqueda; `strategy` admite `lhs` o `tpe` (por defecto `lhs`).
- `budget` es un entero positivo: indica cuántos ensayos nuevos solicita la estrategia en cada invocación. El resultado TPE puede incluir también ensayos anteriores del estudio. LHS usa el `seed` configurado para muestrear; si se repite el mismo manifiesto con la misma semilla, puede proponer los mismos parámetros, cuyas corridas ya completas se reutilizan desde el diario.
- `base_configuration` es opcional. Cada vector de parámetros propuesto se combina con ella y la propuesta reemplaza cualquier valor con el mismo nombre.
- `parameters` define el espacio de búsqueda. `kind` puede ser `float`, `integer` o `categorical`. Los parámetros numéricos requieren límites `lower` y `upper`; opcionalmente admiten `step` o muestreo `log`. Los categóricos declaran `choices`.
- `objectives` contiene uno o más `metric_id` con dirección `minimize` o `maximize`.
- `constraints` es opcional. Cada restricción declara `constraint_id`, descripción, `metric_id`, operador `<=` o `>=` y un umbral numérico finito.
- `campaign` describe las corridas de cada candidato: `systems`, `scenarios`, `repetitions` y, opcionalmente, `seeds`, concurrencia, reintentos, presupuesto de pared y metadatos. Usa el mismo escenario y las mismas semillas para evaluar cada candidato.
- `seed`, `workers`, `n_startup_trials`, `study_name` y `storage_url` configuran el muestreo/estudio; `workers` y `n_startup_trials` son enteros positivos. La semilla del estudio por defecto es 0, los workers por defecto son 1, el inicio TPE por defecto usa 10 ensayos y el nombre del estudio por defecto es `tuning_id`.

Para cada candidato, SimOps ejecuta el producto de sistemas, escenarios y repeticiones y conserva cada observación por corrida. Los objetivos agregan por `mean` de forma predeterminada; se puede elegir `median`, `min`, `max` o `p95`. Una métrica debe estar observada y ser numérica en cada corrida; si falta, no es numérica o no cubre toda la matriz, el candidato queda `invalid` y no participa en el frente Pareto. Los fallos de infraestructura quedan como tales, sin asignarles un valor ficticio. Una métrica booleana, como `task.success`, se convierte a 0/1 antes de calcular la media, por lo que su media representa la proporción de éxitos.

Las restricciones usan `worst_case` por defecto: máximo para `<=` y mínimo para `>=`, por lo que un solo incumplimiento vuelve no factible al candidato. Se puede escoger explícitamente `mean`, `median`, `min`, `max` o `p95`; una métrica ausente o sin cobertura completa vuelve la evaluación inválida. Los resultados incluyen el frente de Pareto de los candidatos factibles; con varios objetivos no se escoge automáticamente un ganador único. Las restricciones guían la búsqueda y no constituyen una garantía de seguridad.

LHS no requiere dependencias adicionales. TPE usa Optuna; sin `storage_url`, el estudio persistente se guarda bajo `.simops/optuna/` junto al `--store` predeterminado (si cambias `--store`, la carpeta `optuna` se crea junto a esa base). Funciona con un worker. Con `storage_url` se utiliza la URL proporcionada. Varios workers requieren un almacén RDB compartido, como PostgreSQL o MySQL; SQLite solo se admite con un worker. Al invocar otra vez el mismo estudio TPE, `budget` cuenta los ensayos nuevos de esa invocación y el resultado conserva también el historial existente.

`tune` genera `tuning.json` y `tuning.md` bajo `.simops/tunings/<id-de-búsqueda>` (o bajo el `--result-dir` indicado). Los candidatos y sus estados, parámetros, objetivos, restricciones y motivos de invalidez/fallo quedan en el JSON; el Markdown resume el frente Pareto y muestra factibilidad y márgenes de restricción de todos los candidatos. El diario de campañas indicado por `--store` conserva las corridas usadas para evaluar candidatos. Trata la búsqueda como exploratoria y confirma finalistas con escenarios o semillas hold-out antes de afirmar que mejoran.

## Operación por MCP

Instala el extra MCP y configura un workspace. El servidor es local por `stdio`; los manifiestos que el agente puede usar deben estar en `workspace/manifests`:

```sh
python -m pip install -e ".[mcp]"
mkdir -p workspace/manifests
cp examples/demo-campaign.json workspace/manifests/
mkdir -p workspace/robot-profiles
cp examples/robot-profiles/turtlebot3-demo.json workspace/robot-profiles/
simops mcp --workspace ./workspace
```

El allowlist por defecto solo permite `demo`. Para usar el ejemplo Nav2, el operador debe permitirlo de forma explícita con `simops mcp --workspace ./workspace --allow-backend nav2-docker`. La tool MCP puede iniciar el Docker instalado en esa máquina. Instalar un plugin por sí solo no habilita su uso. MCP ofrece tools para listar manifiestos/backends, validar campañas y afinados, planificar campañas, iniciar y consultar ejecuciones, reanudar/cancelar campañas, renderizar informes e iniciar búsquedas. No expone herramientas de shell ni rutas arbitrarias. El límite de corridas, paralelismo, tiempo y presupuesto de afinado está documentado en [mcp.md](mcp.md).

## Funciones aún no disponibles

- El backend Nav2/TurtleBot3 solo implementa la ruta sandbox indicada; otros simuladores requieren un adapter específico.
- No hay comando CLI para cancelar corridas; la cancelación está disponible en MCP y es cooperativa.
- MCP entrega el resumen estructurado por escenario y configuración con `get_campaign_result`; no expone el contenido de artefactos ni el historial completo de cada intento.
- No hay informe PDF, gráficos ni comparación estadística entre configuraciones.


## Perfil de capacidades del robot

Describe la huella, el límite cinemático y las señales disponibles antes de iniciar el afinado. El perfil es JSON versionado y se conserva junto al manifiesto de tuning:

```sh
simops profile validate examples/robot-profiles/turtlebot3-demo.json
```

En un manifiesto, `"robot_profile"` apunta a un perfil relativo a ese archivo. SimOps comprueba que las cotas de `controller.vx_max` y `controller.wz_max` respeten los límites declarados. El backend debe implementar la traducción de parámetros a la configuración real y registrar los valores efectivos. Si el robot o simulador requieren más señales, crea un backend instalable con el contrato descrito en `docs/backend-authoring.md`; el núcleo acepta adapters con entry point `simops.backends`.

## Restricciones por corrida

Una restricción numérica es de peor caso en todas las corridas candidatas por defecto. Usa `aggregation: "mean"` solo en criterios que sean tasas poblacionales y cuyo umbral admita fallos individuales. Los objetivos aceptan `mean`, `median`, `min`, `max` y `p95`. Las semillas y escenarios de validación final deben estar separados del screening y nunca deben elegirse después de ver los resultados.
