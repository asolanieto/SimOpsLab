# ADR-001 — Mantener el núcleo de campañas independiente de MCP

- Estado: aceptada como decisión de diseño inicial; se revisará al implementar el API.
- Fecha: 2026-11-19.

## Contexto

Hay servidores MCP que exponen control y observación de Gazebo/ROS. El objetivo de este repo también incluye campañas reanudables, evaluación, optimización y reportes; no queremos que la lógica de dominio dependa de una interfaz de agente.

## Decisión

El core y la API de aplicación serán utilizables sin un LLM y sin el SDK MCP. El servidor MCP se añade como adaptador que traduce herramientas tipadas a operaciones de aplicación existentes.

## Consecuencias

- Una CLI y el MCP comparten lógica, permisos, persistencia y validación.
- Se pueden probar campañas y renderizadores sin crear una sesión LLM.
- La plataforma puede integrar otros clientes en el futuro.
- El transporte MCP no se trata como una innovación sustantiva por sí misma.
