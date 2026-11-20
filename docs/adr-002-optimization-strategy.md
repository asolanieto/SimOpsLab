# ADR-002 — Estrategia de afinado de parámetros

- Estado: aceptada para la primera implementación, pendiente de evaluación comparativa.
- Fecha: 2026-11-19.

## Contexto

Las campañas de simulación pueden ser costosas y ruidosas, con varias semillas y escenarios; criterios como colisión, llegada y holgura deben quedar como restricciones independientes. Una búsqueda por fases y un diseño de screening reproducible sirven como baselines. El núcleo necesita estrategias genéricas e intercambiables para parámetros continuos, discretos y categóricos.

## Alternativas

### A. Grid o búsqueda por fases como estrategia única
- Pros: sencilla de explicar y reproducir; buena para pocos parámetros y listas pequeñas.
- Contras: escala exponencial y la búsqueda OAT puede perder interacciones.

### B. LHS de screening + TPE para el ajuste adaptativo
- Pros: LHS ofrece cobertura reproducible como baseline; TPE reutiliza historial, admite parámetros mixtos y se integra con objetivos múltiples/constraints mediante Optuna.
- Contras: necesita trials iniciales, dependencia opcional, estudio persistente y agregación correcta de ruido; las constraints no son garantía formal de seguridad.

### C. Gaussian-process BO / BoTorch desde el inicio
- Pros: eficiente para problemas caros y continuos; permite BO multiobjetivo y restricciones.
- Contras: instalación y cómputo más pesados; menos adecuado como única opción para parámetros categóricos o espacios mayores; mayor complejidad de producto.

### D. Hyperband/racing como mecanismo de parada
- Pros: puede ahorrar presupuesto al cortar candidatos que se ven malos con poca fidelidad.
- Contras: solo funciona bien si ranking/medidas tempranas predicen el resultado completo. Hoy no se ha demostrado que éxito o colisión en navegación queden bien predichos antes del final.

## Criterios de decisión

- Mantener core sin dependencias científicas externas.
- Comparar con LHS/búsqueda aleatoria bajo el mismo presupuesto de evaluaciones.
- No convertir seguridad en un término compensable de una función ponderada.
- Separar error de infraestructura, fallo funcional y medición inválida.
- Registrar semillas, agregación, parámetros, espacio de búsqueda y versión del optimizador.
- No usar hardware real como destino del TPE de esta primera versión.

## Decisión

Implementar LHS como baseline nativo sin dependencias y TPE/Optuna como extra opcional. Las constraints se expresan como residuos donde valor <= 0 es factible. El reporte devuelve el frente de Pareto entre candidatos factibles; el optimizador no escoge un ganador único si el problema tiene varios objetivos.

La primera integración toma un callback evaluador que ejecuta las corridas y devuelve métricas ya agregadas. TPE soporta almacenamiento Optuna con heartbeat; SQLite queda para un worker y el paralelismo requiere RDB compartido. No habilitar pruning ni optimización sobre hardware real hasta tener evidencia y controles adecuados.

## Consecuencias

- El resultado no demuestra aún que TPE supere estrategias de referencia. Hace falta una comparación con el mismo presupuesto y protocolo.
- Se requiere un runner para conectar la función evaluadora a campañas y preservar cada ejecución individual.
- Se pospone GP BO/BoTorch, sensibilidad Morris/Sobol y racing hasta probar la primera integración.
- Se añaden puertas de release para validar ruido, constraints, Pareto, persistencia e interrupciones.
