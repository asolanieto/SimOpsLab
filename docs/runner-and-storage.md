# Ejecución local y almacenamiento

## Recorrido

```text
manifiesto JSON → planner → validación de adapter → SQLite → worker local
                → adapter → resultado + métricas + artefactos → análisis JSON → Markdown/HTML
```

Instalación mínima del núcleo: `python -m pip install -e .`. `demo` es un benchmark sintético para probar la instalación y los formatos; `nav2-docker` es un adapter de ejemplo que requiere construir la imagen y tener Docker accesible.

```sh
simops validate examples/demo-campaign.json
simops plan examples/demo-campaign.json
simops run examples/demo-campaign.json
simops status demo-navigation-smoke
simops resume demo-navigation-smoke
simops report demo-navigation-smoke
```

La base predeterminada es `.simops/campaigns.sqlite3`; los informes van bajo `.simops/reports/`. `--store` y `--report-dir` permiten usar otras ubicaciones.

## Diario y reanudación

SQLite conserva:

- Manifiesto resuelto y huella SHA-256, backend y versión.
- Especificación de cada corrida, último estado y resultado.
- Un registro por intento, con marcas de tiempo y resultado terminal.
- Eventos append-only de campaña y corrida.

La transacción que termina un intento actualiza su proyección de estado y añade el evento correspondiente. Repetir una orden con la misma huella omite corridas ya terminales. Si el proceso se encuentra con intentos `running` de una ejecución anterior, los registra como `interrupted` y aplica el límite de reintentos de infraestructura.

Una huella diferente para un `campaign_id` existente se rechaza: cambiar escenarios, parámetros o versión de backend requiere un ID nuevo. Los IDs por corrida se vuelven a calcular al ejecutar para detectar mutación de un plan después de haber asignado sus IDs.

Antes de recuperar o ejecutar, el runner toma un bloqueo del sistema operativo asociado a la base SQLite y al `campaign_id`. Las llamadas locales concurrentes a la misma campaña se serializan; el bloqueo se libera automáticamente si el proceso termina. No coordina bases distintas ni hosts remotos.

## Intentos, presupuesto y cancelación

- El fallo del sistema bajo prueba se conserva separado del estado operativo; por ejemplo, `completed` junto con `system_outcome=failure`.
- Las excepciones del adapter son fallos de infraestructura y solo esos fallos se reintentan automáticamente.
- La fecha límite de campaña impide empezar más corridas; no interrumpe por la fuerza una llamada bloqueante.
- SIGINT y las tools MCP solicitan cancelación cooperativa. Cada adapter recibe evento de cancelación, deadline monotónico, carpeta de trabajo por intento y almacén de artefactos.
- En una caída alrededor de la llamada externa puede haber ejecución repetida al reanudar. SimOps no promete “exactamente una vez”; un adapter de trabajo remoto debe reconocer `run_id` e intento o detectar y limpiar procesos huérfanos.
- `max_parallel > 1` solo se acepta si el adapter declara `thread_safe=True`; todos los runs usan el mismo objeto de adapter.

## Artefactos

El adapter puede guardar bytes usando `context.artifacts.put(...)`. El almacén calcula SHA-256, escribe a un path content-addressed mediante un rename atómico y devuelve un `ArtifactRef`. La lectura vuelve a verificar el hash. Los blobs viven bajo `.simops/artifacts/`; el workspace de cada intento está bajo `.simops/work/`.

El runner conserva referencias, pero no inventa el significado de los archivos. Los plugins de métrica/adapters deben nombrar la fuente, unidad, versión y estado de cada medida. Los artefactos no se copian a la base SQLite.

## API de adapter

El paquete de adapter publica un entry point Python:

```toml
[project.entry-points."simops.backends"]
mi_backend = "mi_paquete.backend:Backend"
```

La clase sin argumentos implementa `backend_id`, `backend_version`, `thread_safe`, `validate(run)` y `execute(run, context)`. El host llama `validate` antes de registrar la campaña. El código del plugin es confiable por instalación; el LLM no puede cargar un módulo arbitrario desde el manifiesto.
