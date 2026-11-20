# ADR-003 — Runner local y persistencia reanudable

- Estado: aceptada para el primer producto ejecutable.
- Fecha: 2026-11-19.

## Decisión

- Mantener `CampaignSpec` y los IDs deterministas del planner como identidad de la campaña.
- Ejecutar adapters Python instalados mediante entry points `simops.backends`; el núcleo no invoca shell ni importa ROS/Gazebo.
- Empezar con SQLite local, WAL y timeout de bloqueo. Guardar campaña, ejecuciones, intentos y eventos; actualizar el estado de intento y anexar su evento en una transacción.
- Fijar cada campaña a la huella del manifiesto expandido más `backend_id` y `backend_version`. Una diferencia requiere otro `campaign_id`.
- Reintentar solo fallos de infraestructura e interrupciones, dentro del límite declarado. Las corridas completas y fallidas funcionalmente no se repiten al reanudar.
- Guardar artefactos en rutas locales content-addressed por SHA-256; pasar al backend un workspace distinto por corrida/intento.
- Persistir informes JSON, Markdown y HTML desde el mismo modelo de análisis.

## Garantías y límites

La ejecución es *al menos una vez* ante caídas alrededor de un efecto externo. Una base local no puede demostrar si un simulador remoto ejecutó una tarea cuando el proceso muere después de lanzar el trabajo y antes de persistir su resultado. Los adapters deben usar `run_id`/`attempt_number` como clave idempotente y limpiar procesos huérfanos cuando el entorno lo permita.

El límite de pared impide iniciar nuevas corridas cuando se agota el presupuesto. No puede matar a la fuerza una llamada bloqueante al backend. La cancelación se transmite por `ExecutionContext` y es cooperativa. SQLite sirve para un coordinador local; no es una base distribuida para workers en varias máquinas.

## Consecuencias

- Se puede instalar el núcleo sin ROS, Gazebo u Optuna.
- `max_parallel > 1` requiere que el adapter declare explícitamente `thread_safe`.
- La base SQLite y los blobs locales son sencillos de respaldar, inspeccionar y mover junto al proyecto.
- Los adaptadores remotos, leases distribuidos, almacenamiento de objetos y limpieza de procesos huérfanos quedan como evolución posterior.
