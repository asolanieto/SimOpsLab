# Instrucciones para agentes

Este repositorio contiene el nuevo producto derivado del análisis de TFM_Rover.

## Al comenzar

1. Lee `README.md`, `PLAN.md` y las páginas relevantes de `docs/`.
2. Trata `docs/audit-existing-system.md` como una auditoría estática del estado observado el 19-11-2026; confirma las cifras y las fuentes antes de usarlas en una publicación.
3. Mantén separadas las mediciones verificadas, las inferencias y las hipótesis de diseño.

## Límites del producto

- El núcleo no importa ROS, Gazebo, EasyNav, Nav2 ni el protocolo MCP.
- Las particularidades del RAT viven en adaptadores y perfiles de dominio.
- No presentes compatibilidad genérica hasta haber ejecutado el mismo contrato con dos backends distintos.
- Un dato ausente o inválido no se representa como cero ni como éxito.
- Conserva procedencia, versión y unidad para cada resultado.
- Las infografías históricas se usan como referencia visual; el nuevo informe debe regenerarse desde datos estructurados.

## Cambios y coordinación

- No edites TFM_Rover como parte del desarrollo de este repo; úsalo como fuente de lectura y mantén sus modificaciones locales intactas.
- No añadas secretos, rutas locales absolutas, credenciales ni claves SSH.
- Las decisiones de arquitectura se registran en ADRs de este repositorio.
- No configures ni publiques un remoto sin petición expresa del usuario.
- El nombre SimOps Lab, el esquema v0.1 y las interfaces iniciales son provisionales hasta que se validen con el adapter piloto.
