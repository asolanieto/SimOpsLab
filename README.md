# SimOps Lab

**Convierte una simulación ejecutable en un ciclo reproducible de evaluación y ajuste.** SimOps Lab organiza campañas, aplica criterios por corrida, busca configuraciones candidatas y conserva la evidencia que permite explicar por qué una configuración pasa o falla. Un agente puede operar el flujo mediante MCP local, mientras la ejecución y los cálculos siguen siendo reproducibles fuera del LLM.

> Para robots móviles, el objetivo es ayudar a llevar un stack desde sus parámetros iniciales hasta una configuración validada para un robot, mapa y conjunto de escenarios definidos. SimOps no promete un óptimo matemático ni certifica seguridad: muestra qué se midió, bajo qué condiciones, qué restricciones se incumplieron y qué falta validar.

## Qué puedes hacer

| Capacidad | Disponible en el núcleo | Estado del ejemplo Nav2/TurtleBot3 |
|---|---|---|
| Definir campañas de robot × escenario × configuración × repetición × semilla | Manifiestos JSON y planner determinista | Ruta de navegación headless en Gazebo Sim |
| Ejecutar, reintentar, cancelar y reanudar | Runner concurrente, deadline, journal SQLite WAL | Un contenedor aislado por corrida |
| Preservar datos de forma verificable | Artefactos SHA-256, intentos, configuración, backend e imagen | Logs, override YAML y mediciones JSON |
| Medir resultados funcionales y operación | Métricas versionadas; dato observado, faltante, inválido o no aplicable | Acción NavigateToPose, duración de pared y sim, odometría y láser |
| Cuantificar control y ruta | Contrato genérico, resúmenes y cobertura por escenario | Eficiencia proxy, tasa de comandos, giros, saturación y aceleración angular RMS |
| Afinar parámetros | LHS sin dependencias y TPE/Optuna opcional; objetivos múltiples y Pareto | Tuning conectado a ejecuciones reales; límites verificables por perfil de robot |
| Evitar que una media esconda un fallo | Restricciones de peor caso por corrida por defecto | Restricciones de colisión, llegada y umbrales configurables |
| Inspeccionar resultados | JSON canónico, Markdown y HTML con cuantiles, intervalos de éxito y datos faltantes | Informes locales por campaña |
| Dejar que un agente opere el ciclo | MCP local por stdio, workspace acotado, allowlist y cuotas | Solo backend `demo` permitido por defecto |
| Adaptar a otro robot o dominio | Backend Python instalable por entry point; perfil de capacidades | El ejemplo Nav2 es específico de TurtleBot3 y no representa un adapter universal |

## Catálogo de evaluación

El esquema no fuerza una puntuación única. Puedes definir métricas y criterios de misión para el problema, conservar faltantes como faltantes y comparar cada escenario/configuración antes de agregar resultados.

- **Misión y navegación:** éxito, estado final, tiempo simulado/de pared, distancia, eficiencia, pose terminal, desviación y recuperaciones.
- **Seguridad:** contactos y colisiones, distancia de la huella, near-misses, TTC, velocidad/impulso de impacto.
- **Localización y sensores:** error XY/yaw con referencia independiente, deriva, frescura, pérdidas, jitter y latencia.
- **Control y movimiento:** límites y saturación, oscilación, maniobras, aceleración, jerk, suavidad y parada posterior a la misión.
- **Robustez:** distribución por escenario y semilla, peor caso, CVaR, sensibilidad, rendimiento fuera de muestra y hold-out.
- **Sistema y reproducibilidad:** diagnósticos, caídas, ciclos, CPU/memoria/GPU, reloj, cobertura de datos, parámetros efectivos y hashes de artefactos.

El [catálogo de métricas](docs/metrics-catalog.md) distingue las medidas emitidas por el ejemplo Nav2 de las extensiones que requieren instrumentación nueva. En el demo Nav2 el láser mínimo **no** se presenta como distancia segura, la odometría **no** se presenta como referencia de verdad independiente y la ausencia de contactos **no** se cuenta como cero colisiones.

## Afinado consciente del robot

1. Declara geometría, límites cinemáticos y sensores en un [perfil de robot](examples/robot-profiles/turtlebot3-demo.json).
2. Especifica parámetros permitidos, escenarios de screening, repeticiones, semillas y objetivos.
3. Declara restricciones de seguridad por corrida. Por defecto se usa el peor caso para que una media no oculte un fallo aislado.
4. Ejecuta LHS para cubrir el espacio; usa TPE si la búsqueda adaptativa resulta útil y puedes persistir el estudio.
5. Inspecciona el frente de Pareto y la matriz escenario/configuración.
6. Repite candidatos finalistas en escenarios/semillas reservados antes de afirmar mejora.

Las [reglas de afinado](docs/optimization-methods.md) y el [manual de usuario](docs/user-manual.md) incluyen ejemplos. Un perfil limita las cotas de `controller.vx_max` y `controller.wz_max`; el backend sigue siendo responsable de aplicar y leer de vuelta los valores efectivos.

## Empieza en minutos

```sh
python -m pip install -e .
simops profile validate examples/robot-profiles/turtlebot3-demo.json
simops validate examples/demo-campaign.json
simops run examples/demo-campaign.json
simops tune examples/demo-tuning.json
```

`demo` es sintético y sirve para aprender el flujo. Para ejecutar la integración real de muestra se necesita Docker:

```sh
docker build -f examples/nav2-turtlebot3/Dockerfile -t simops-lab/nav2-turtlebot3:lyrical-1.5.3-gm1.3.46 .
simops validate examples/nav2-turtlebot3/campaign.json
simops run examples/nav2-turtlebot3/campaign.json
```

Consulta el [manual](docs/user-manual.md) antes de configurar el experimento. Para MCP local instala `python -m pip install -e ".[mcp]"` y ejecuta `simops mcp --workspace ./workspace`; el servidor no tiene una herramienta de shell y por defecto solo permite el backend sintético. Instala TPE con `python -m pip install -e ".[optimize]"`.

## Construye soporte para tu stack

Crea un plugin con `validate()` y `execute()` que traduzca parámetros, inicie el simulador, recoja señales y emita `RunResult` con fuente, cobertura y límites conocidos. Regístralo bajo el entry point `simops.backends`. La guía [backend-authoring](docs/backend-authoring.md) describe instrumentación y aislamiento. SimOps no asume ROS, Gazebo ni una tarea de navegación en el núcleo.

## Estado del producto

La infraestructura base, la búsqueda LHS/TPE y una integración de demostración Nav2 están implementadas y tienen pruebas de unidad y smoke tests. La demostración actual **no** implementa todavía la instrumentación de contactos Gazebo, referencia de pose independiente, holgura geométrica, error de localización, diagnóstico ROS ni telemetría de recursos. Por ello, aún no es un optimizador universal listo para cualquier robot.

Aún faltan validación con más stacks y escenarios, métricas de seguridad independientes, una segunda implementación de backend y revisión externa del manual. La integración incluida es una demostración reproducible, no una certificación de seguridad ni una garantía de rendimiento para otros robots. El repositorio se distribuye bajo [Apache License 2.0](LICENSE). Las campañas de ejemplo no incluyen datos de las pruebas locales.


## Comunidad y contribuciones

Consulta el [changelog](CHANGELOG.md) y lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de proponer cambios. Para fallos de seguridad consulta [SECURITY.md](SECURITY.md); para preguntas y errores usa las plantillas de GitHub.
