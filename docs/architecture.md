# Arquitectura inicial

## Límite del sistema

El núcleo organiza experimentos y resultados. No modela física, no entiende ROS topics, no requiere Gazebo y no envía directamente comandos al hardware. Un adapter traduce entre el contrato del núcleo y el entorno bajo prueba.

## Componentes

- **Spec/validator**: manifiestos declarativos de campaña, escenarios, configuraciones, repeticiones, seeds, métrica y límites.
- **Planner**: expande matriz experimental en corridas estables con IDs deterministas.
- **Campaign service**: estado, persistencia, reintentos, presupuesto, concurrencia, cancelación y reanudación.
- **Backend adapter**: prepara, lanza, observa, finaliza y recoge artefactos de un entorno.
- **Metric plugins**: extraen medidas de telemetría y artefactos, con versión y validez.
- **Analysis engine**: valida criterios, calcula grupos e incertidumbre, identifica anomalías y separa exploración/confirmación.
- **Artifact store**: blobs locales al inicio; interfaz extensible a object storage.
- **Report renderers**: Markdown y HTML derivados del resultado canónico.
- **CLI/API**: interfaz de persona; MCP es una integración sobre la misma API de aplicación.

## Estado de implementación

Están implementados el planner determinista, parser/validador JSON, runner local con SQLite, artefactos SHA-256, informes JSON/Markdown/HTML, CLI, LHS integrado con campañas y TPE/Optuna opcional. El backend sintético `demo` prueba el núcleo; `nav2-docker` conecta el mismo runner con Nav2/TurtleBot3 sobre un mapa sandbox real.

El adapter `nav2-docker` usa una imagen fijada por digest, lanza una navegación por contenedor y recoge acción, odometría, láser, comandos y logs. Cubre solo el mapa/ruta de demostración; el usuario debe definir escenarios y validación para otros sistemas. `demo` no prueba física, Gazebo ni ROS. TPE necesita la extra Optuna. El MCP stdio existe como extra opcional; por defecto solo permite `demo`, lee manifiestos desde un workspace dedicado y aplica cuotas. Otros simuladores y stacks requieren adapters propios.

## Ports/adapters propuestos

1. `ExecutionBackend`: ubicación y presupuesto (local, Docker, SSH, Slurm u otro scheduler).
2. `ExperimentBackend`: preparación y ejecución de una corrida del sistema bajo prueba.
3. `ObservationProvider`: señales estructuradas, archivos, logs, bags o telemetría remota.
4. `ScenarioProvider`: enumera/crea/valida escenarios por backend.
5. `MetricPlugin`: deriva `MetricValue` desde corrida, señales y artefactos.
6. `SearchStrategy`: ejecuta una estrategia de ajuste con un evaluador agnóstico al backend; están disponibles LHS y TPE/Optuna.
7. `ArtifactStore`: guarda/importa archivos y checksums.
8. `ReportRenderer`: toma el modelo de análisis ya calculado y produce formato.

Un adapter de mayor nivel puede implementar varios ports si el primer producto lo necesita. Cada interfaz queda sustituible para evitar acoplamiento del core.

## Estados y fallo

- Corrida: `planned → queued → running → completed | failed_system | failed_infrastructure | cancelled | interrupted`.
- Resultado del SUT: `success | failure | expected_abort | unknown | not_applicable`.
- Estado de cada métrica es independiente: una corrida completa puede contener datos métricos ausentes; una corrida de infraestructura puede conservar métricas parciales.
- La ejecución debe ser idempotente por `run_id` y persistir transición/evento antes de marcar el trabajo completo.

## Superficie MCP

Lecturas: `list_backends`, `inspect_backend`, `get_campaign`, `get_run`, `get_metric_catalog`, `get_artifact`, `get_report`.

Escrituras: `validate_campaign`, `plan_campaign`, `start_campaign`, `pause_campaign`, `resume_campaign`, `cancel_campaign`, `render_report`.

Las tools de escritura aceptan identificadores o nombres de manifiesto dentro del workspace, registran la solicitud y verifican política de workspace, cuota, concurrencia y timeout. No se expone una herramienta genérica `run_shell`. El MCP local por stdio y sus límites están implementados; un endpoint HTTP o destino de hardware real no se configura ni se habilita por defecto.

## Primer vertical slice

Manifiesto simple → backend simulado de prueba → ejecución única → métricas genéricas → carpeta de artefactos local → JSON de resultado → informe Markdown. Después se integra un backend específico del simulador o robot, conservando los contratos y el núcleo común.
