# ADR-004 — MCP local con límites por workspace

- Estado: aceptada para la primera integración MCP.
- Fecha: 2026-11-19.

## Decisión

- Exponer MCP por `stdio` y montar las mismas operaciones de aplicación que usa el CLI.
- El operador inicia el servidor con un workspace local y una lista de backends permitidos. Por defecto solo está permitido `demo`.
- El LLM identifica manifiestos por nombre de archivo dentro de `<workspace>/manifests`; no recibe herramientas para leer/escribir rutas arbitrarias ni para ejecutar comandos shell.
- Limitar tamaño de campaña, concurrencia, presupuesto por corrida y total de corridas en afinado.
- Ejecutar campañas y afinados en una tarea de fondo, con herramientas explícitas de estado/cancelación cooperativa.
- No ofrecer destino de hardware real por defecto. Para habilitar un adapter real el operador debe instalarlo y permitirlo en la línea de inicio del MCP.

## Consecuencias y límites

- El transporte inicial es local; no se configura endpoint HTTP ni autenticación remota.
- Los límites del servidor MCP son una barrera adicional. No sustituyen aislamiento de proceso, cuotas del host ni revisión del plugin de backend que el operador decide instalar.
- La cancelación de una corrida activa solo funciona si el adapter consulta el contexto y termina con limpieza.
- El servidor expone operaciones tipadas de planificación y campaña; nunca una tool genérica de shell.
