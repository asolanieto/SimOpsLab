# Plan de producto y evolución

## Base ejecutable de v0.1

Esta base se puede inspeccionar y ejecutar localmente. El núcleo, runner SQLite, artefactos SHA-256, recuperación, informes, LHS/TPE y MCP están conectados. Los adapters probados son el backend sintético `demo` y una ruta Nav2/TurtleBot3 en Docker. El adaptador Nav2 es una integración vertical acotada, no una prueba de portabilidad universal.

| Área | Estado verificable | Siguiente mejora |
|---|---|---|
| Experimentos | Manifiesto JSON estricto, matriz, IDs deterministas, reintentos, cancelación cooperativa y reanudación local | Versionar esquema formalmente; guardar valores efectivos de configuración después de leerlos desde el simulador |
| Almacenamiento | SQLite local con campañas, estados, intentos y eventos; blob local con SHA-256 | Abstracción de almacenamiento y retención; evitar SQLite como base de workers distribuidos |
| Búsqueda | LHS determinista y TPE/Optuna opcional conectados a campañas reales; constraints y Pareto | Confirmación hold-out, pareado por escenario/semilla, sensibilidad y registro de decisión final |
| Informes | JSON canónico y vistas Markdown/HTML con agregados, faltantes e IC de Wilson para éxito | Comparaciones pareadas, bootstrap por unidad experimental, gráficos y tablas descargables |
| MCP | Servidor local `stdio`, inspección y validación previa de tuning, workspace acotado, cuotas y allowlist por defecto `demo` | Pruebas con host MCP de terceros y revisar adapters antes de habilitar Docker |
| Navegación | Nav2 Lyrical/TurtleBot3 en un mapa/ruta sandbox | Añadir mapa con obstáculo, variar escenarios y comprobar cancelación, repetición y registros brutos |
| Adapter de navegación | Nav2/TurtleBot3 en una ruta sandbox; interfaz genérica para plugins | Añadir un segundo robot/simulador con métricas de seguridad y ground truth comparables |
| Extensibilidad | API de plugin `simops.backends` y backend adicional Nav2 | Segundo backend de dominio ajeno a ROS/Gazebo para verificar portabilidad real |

## Orden de trabajo

### P0 — Mantener fiable la demo antes de cada release

1. Completar campañas reales LHS y TPE en Nav2/TurtleBot3, incluida la generación de informes. La prueba demuestra integración; no es resultado de benchmark ni una mejora probada.
2. Validar que la guía permite a una persona externa instalar, validar, ejecutar y ajustar el ejemplo sin leer el código. Corregir los pasos que fallen y repetir el ensayo.
3. Mantener CI con instalación limpia, backend `demo`, pruebas de reanudación, perfiles MCP y validación de manifiestos. Mantener la prueba de Nav2 como integración optativa si runner CI no ofrece Docker/Gazebo estable.
4. Mantener Apache-2.0 y revisar licencias de dependencias, imágenes y datos antes de distribuir nuevos artefactos.

### P1 — Validar portabilidad y resultados

1. Implementar un segundo backend pequeño que no importe ROS/Gazebo. Ejecutar el mismo contrato: validar → planificar → correr → persistir → reportar → afinar.
2. Publicar un backend de navegación adicional con métricas y ejemplos reproducibles, sujeto a permisos de código y datos.
3. Comparar métricas contra su implementación original y documentar diferencias de reloj, ground truth, contactos, límites y exclusiones. No portar una métrica si no se puede conservar su semántica.
4. Confirmar finalistas con escenarios retenidos, más repeticiones y diseño emparejado. Publicar incertidumbre y fallos, no solo el candidato ganador.

### P2 — Mejorar análisis y operación

1. Exponer un catálogo por adapter con identificador, fórmula, unidad, fuente, validez, cobertura y aplicabilidad.
2. Añadir métricas por capas: resultado/éxito, duración y eficiencia; trayectoria, control y seguridad; localización; sensores/ROS; CPU/memoria/GPU; artefactos y calidad de datos.
3. Añadir comparación pareada y bootstrap por escenario/semilla; permitir intervalos robustos y análisis de sensibilidad. No tratar mensajes de telemetría como muestras independientes.
4. Añadir perfiles opcionales para manipuladores, vehículos aéreos y otros dominios sin obligar al núcleo a definir métricas de navegación.
5. Solo después de validar requisitos, evaluar un scheduler remoto, workers distribuidos, object storage y credenciales por backend.

## Política de optimización

- Usar LHS como screening reproducible cuando se fija el presupuesto y se quiere cubrir el espacio antes de observar resultados.
- Usar TPE/Optuna cuando cada simulación cuesta tiempo y las propuestas deben aprovechar resultados previos; persistir estudio y semilla.
- Declarar límites duros de seguridad como restricciones separadas de los objetivos de tiempo/eficiencia. Un candidato que no mida una métrica requerida no es factible.
- Promediar por el conjunto de repeticiones, escenarios y semillas declarado; reportar dispersión y fallos. Si las corridas están emparejadas, preservar el emparejamiento.
- Separar conjunto de búsqueda y conjunto hold-out. No seleccionar y evaluar el “ganador” con los mismos resultados.
- Añadir GP-Bayesian Optimization cuando haya pocas variables continuas y los supuestos/ruido lo justifiquen; Morris/Sobol para sensibilidad con presupuesto suficiente; racing/pruning solo tras validar que una fidelidad temprana predice el ranking final.
- No conectar optimizadores a hardware real en esta versión. Las restricciones y los resultados de simulación no son garantía de seguridad.

## Condición de publicación

Publicar una versión estable solo después de ejecutar CI, probar la guía en un clon limpio y cerrar los límites P0. El anuncio debe decir que los backends comprobados son `demo` y Nav2/TurtleBot3 en un único mapa sandbox, enlazar instalación y límites, y evitar claims de generalidad o mejora no medidos. El adapter de otro robot y el segundo backend siguen siendo hitos distintos.
