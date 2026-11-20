# Catálogo de magnitudes y cualidades

Este catálogo separa **mediciones implementadas en el ejemplo actual** de **extensiones candidatas**. Una métrica no se debe habilitar globalmente porque un adapter pueda calcularla: cada definición debe indicar fuente, unidad, método, validez, versión, aplicabilidad y posibles sesgos. La falta de dato no equivale a cero.

## Métricas de navegación que un adapter puede instrumentar

| Grupo | Magnitud/cualidad | Cómo se obtiene hoy | Aplicabilidad y límite |
|---|---|---|---|
| Resultado | Llegada | Distancia final ≤ 0,5 m; de ground truth o pose estimada | Umbral y referencia son específicos; sin ground truth se usa la propia estimación y no se puede reportar error de localización independiente |
| Resultado | Fin/estado de misión, envío de meta y cancelación | Estados de la API de misión y envío/reintentos de objetivo/cancelación | Semánticas nativas distintas se normalizan parcialmente; deben conservarse valor nativo y mapeo |
| Resultado | Tiempo de misión y distancia final | Reloj simulado `/clock`, pose final y meta | Tiempo simulado debe distinguirse del tiempo de pared; últimos 0,2–0,5 m quedan apenas dentro de la ventana de medición |
| Trayectoria | Longitud, velocidad media y eficiencia de ruta | Longitud de la secuencia de posiciones; velocidad = longitud/tiempo; eficiencia = línea recta/recorrido, recortada a 1 | Métrica recta/recorrido puede penalizar rodeos de seguridad legítimos |
| Seguridad | Colisiones, primer contacto, episodios, piezas y objetos | Eventos de contacto del simulador; consolidación de contactos en episodios | Depende del simulador y de la cobertura de telemetría; si está incompleta debe ser desconocida, nunca cero |
| Seguridad | Distancia mínima a obstáculo | Se deriva de la trayectoria real y obstáculos cuadrados estáticos descritos en el escenario | No mide huella completa/orientación, geometría arbitraria o obstáculo móvil |
| Localización | Error XY máximo, medio y RMSE | Comparación sincronizada entre `/ground_truth` y pose estimada | Requiere una referencia independiente, sincronía temporal y marco coherente |
| Localización | Error máximo de yaw | Diferencia angular envuelta entre yaw real/estimado | Depende de verdad de terreno y sincronización; solo máximo se usa hoy |
| Localización | Salto máximo entre estimaciones | Mayor distancia entre poses estimadas consecutivas | Sensible a intervalo de muestreo, jitter y errores de timestamp |
| Localización | Deriva al final de corte GNSS | Error XY en la última muestra dentro de ventana de pérdida de GNSS | Es una instantánea de extremos, no curva completa de degradación |
| Control | Máximo `|w|` y cambios de signo | `/cmd_vel`, alternancias solo sobre umbral | Frecuencia de mensajes puede cambiar los conteos; límite 0,05 en w es código específico |
| Control | Giros sobre sitio | Clasifica muestras con una relación declarada entre velocidad lineal y angular | Presupone umbrales y cinemática de la plataforma configurados por el adapter |
| Control | Fracción en saturación | Muestras con velocidad dentro de un porcentaje configurable del límite | Los límites varían por plataforma/modo; requiere declarar los límites y el tiempo expuesto |
| Control | Suavidad angular | RMS de `Δw/Δt` sobre mensajes de velocidad | El resultado cambia con muestreo, filtro y datos perdidos; no equivale a jerk de movimiento real |
| Atasco | Tiempo total y máximo sin avanzar | Segmentos en los que la posición no se aleja >0,2 m durante al menos 20 s | Umbrales fijos; puede confundir espera deliberada/obstáculo con atasco |
| Finalización | Parada tras éxito/cancelación y su modo | Latencia hasta comando nulo; clasifica comando nulo, silencio o no parar en ventana | Mide consigna observable, no velocidad física de frenado |
| Sistema/ROS | Hz, mensajes ausentes, antigüedad TF, GNSS, jitter/desfase, saltos | Diagnóstico periódico de topics/TF y procesos ROS | Conjunto de tópicos y checks está especializado en este robot |
| Sistema/ROS | WARN/ERROR y ticks fallidos | Cuenta de logs ROS y checks en ventana | Requiere mapear severidad y mensajes; los contadores no identifican causa por sí solos |
| Recursos | CPU media, RAM pico, Hz de `cmd_vel` | Proceso de la pila/monitor a intervalos periódicos | Métrica de CPU normalizada, intervalo de muestreo y alcance de proceso deben ir en metadatos |
| Experimento | Parámetros, ruido GNSS, cortes y semillas | Copias de YAML, argumentos efectivos y configuración de escenario | Guardar valor solicitado y valor efectivo leído al inicio evita deriva silenciosa |
| Observación | No visto/cerca/pasado/olvidado, replanning, desvío, parado, giro | Eventos del observador sobre mapas, rutas y geometría de obstáculos | Semántica específica; p. ej., “olvidado” no identifica causa y depende de la ventana sin marca |
| Artefactos | Trazas, series, rutas, eventos, bag, logs, imagen/GIF | CSV, JSON/JSONL, MCAP, PNG y registros | Cada archivo necesita hash, esquema, relojes, tamaño y vínculo con corrida/configuración |

SimOps define contratos para que cada backend implemente fuentes equivalentes sin trasladar nombres de topics o límites de un robot al núcleo.

## Métricas habilitadas en SimOps v0.1

El backend `demo` emite `task.success`, `task.duration_s`, `safety.collision_count`, `navigation.path_length_m` y `safety.min_clearance_m`; son valores sintéticos deterministas orientativos para probar el runtime, no resultados físicos ni de Nav2.

El backend `nav2-docker` registra estas observaciones para la ruta sandbox de TurtleBot3. El experimento de origen y la implementación del adapter fijan ventanas y unidades:

| ID | Fuente y cálculo actual | Interpretación y límite |
|---|---|---|
| `task.success` | Estado final `SUCCEEDED` de la acción ROS 2 `NavigateToPose` | Éxito de esa meta; no prueba calidad global del stack. |
| `task.duration_s` | Reloj de pared monótono desde el envío de la meta hasta resultado o timeout | Incluye el efecto de CPU/host; no es tiempo simulado ni solo tiempo de movimiento. |
| `navigation.path_length_m` | Suma euclidiana de posiciones consecutivas de `/odom` en `nav_msgs/Odometry` | Odometría del robot, no ground truth independiente; contiene el error de integración de odometría. |
| `safety.min_laser_range_m` | Mínimo de muestras finitas y dentro de rango de `/scan` (`sensor_msgs/LaserScan`) durante la corrida medida | Rango de rayo, no distancia de huella ni distancia libre garantizada; puede medir una pared estática y no cuenta colisiones. |
| `control.peak_linear_speed_mps` | Máximo absoluto de `linear.x` en `/cmd_vel` (`TwistStamped`) | Consigna del controlador, no velocidad física medida. |
| `control.peak_angular_speed_radps` | Máximo absoluto de `angular.z` en `/cmd_vel` (`TwistStamped`) | Consigna, no medición de actuador. |
| `telemetry.odom_samples` | Número de muestras `/odom` que recibió el nodo de medida | Conteo de cobertura, no una magnitud de rendimiento. |
| `mission.sim_duration_s` | Diferencia de `/clock` desde que se envía la meta hasta el último tick observado | Tiempo simulado; `null` si el simulador no publicó reloj. No sustituye al tiempo de pared. |
| `navigation.route_efficiency_proxy` | Distancia recta inicial-meta dividida por longitud odométrica | Proxy de eficiencia; no usa ruta global ni ground truth y puede superar 1 por ruido/deriva. |
| `control.command_samples`, `control.command_rate_hz` | Conteo y Hz calculado con timestamps de `/cmd_vel` | Hz observado entre primer y último timestamp, no frecuencia configurada. |
| `control.angular_sign_changes`, `control.spot_turn_samples` | Alternancias de signo sobre umbral y muestras con avance casi cero/rotación alta | Heurísticas exploratorias específicas de los umbrales del adapter, no equivalen a maniobras semánticas. |
| `control.saturation_fraction` | Fracción de mensajes con velocidad lineal o angular >=95% del límite configurado | Consigna; requiere límites correctos del perfil y no describe saturación del motor físico. |
| `control.rms_angular_acceleration_radps2` | RMS de diferencias angulares consecutivas divididas por delta de timestamp | Sensible a frecuencia, jitter y comandos faltantes; no es aceleración medida del robot. |
| `control.stop_after_success_latency_s` | Tiempo entre resultado exitoso y primer comando nulo observado durante flush | `missing` cuando no hay muestra nula en ventana. Consigna del controlador, no frenado físico. |

La demo no recoge aún contactos Gazebo, ground truth, error de localización, holgura de huella, seguimiento lateral, replanning, recuperaciones, atasco, diagnósticos ROS, CPU/memoria/GPU, latencia de sensores, jerk ni energía. No infiere colisión ni distancia segura desde el mínimo lidar. Esas medidas necesitan sensores, eventos y fórmulas explícitas; no se deben sustituir por `min_laser_range_m`. El mundo del ejemplo es determinista y el campo `seed` de SimOps no configura una semilla de Gazebo.

## Magnitudes candidatas para extender

Orden sugerido: primero las que refuerzan validez/seguridad y la interpretación del resultado; después instrumentación de dominio opcional.

| Área | Candidatas | Requisitos |
|---|---|---|
| Seguridad dinámica | Distancia de huella a obstáculo, tiempo a colisión (TTC), near-misses por severidad, energía/impulso de contacto, velocidad relativa al impacto, distancia de parada | Geometría/footprint, velocidad estimada y sincronización de eventos |
| Navegación | Error lateral RMS/p95, error de seguimiento, desviación de ruta, sobrepaso/overshoot, error de pose terminal, éxito dentro de tolerancia XY+yaw, replanificaciones, recuperaciones, ratio de vuelta/retroceso | Ruta de referencia y criterio de misión definidos |
| Movimiento | Aceleración lineal/angular, jerk, curvatura y variación, máximos y percentiles de velocidad, vibración/estabilidad | Odometría o ground truth con resolución suficiente; filtro documentado |
| Robustez | Éxito por perturbación, distribución de peor caso, CVaR, dispersión entre semillas, sensibilidad a parámetros, caída OOD y dominio de validez | Diseños factoriales/escenarios, semillas y conjuntos hold-out |
| Sensores | Frescura/edad de datos, pérdida y jitter de mensajes, cobertura temporal, latencia sensor→decisión→actuación, inconsistencia entre sensores, calidad de mapa | Relojes y referencias por adapter; métricas declarativas de señales |
| Operación del stack | Tiempo a primer comando, disponibilidad, reinicios/caídas, watchdog, latencia/jitter de ciclos, uso de GPU/VRAM, IO, red y energía | Telemetría de host y telemetría del proceso con atribución |
| Misión | Rechazos/abortos, subtareas logradas, eficiencia multicriterio, intervención humana, tiempo de recuperación | Estado de misión neutral de dominio; eventos de intervención |
| Manipulación (perfil opcional) | Éxito de agarre, tasa de deslizamiento, error de pose, fuerza/torque, colisión del brazo, tiempo de ciclo, coordinación | Estándar propio de tarea; el núcleo no debe forzar este perfil a ser navegación |
| Drones/vehículos (perfil opcional) | Desviación altitud/actitud, consumo/energía, geocercas, estabilidad, colisión, seguimiento de waypoint | Referencias y límites del vehículo específico |
| Calidad de datos | Huecos, reloj retrocedido, jitter de timestamps, muestras fuera de rango, integridad del bag, cobertura de señales | Cómputo independiente del resultado funcional |

## Reglas del catálogo de métricas

Cada ficha debe definir: identificador estable, nombre legible, descripción operacional, unidad, tipo, polaridad (menor/mayor/mejor u objetivo), aplicación, fórmula, señales/fuentes, frecuencia/filtro, tolerancias, requisitos de referencia, estado de validez, razón de no-aplicación, versión, política de agregación y límites conocidos.

Perfiles de dominio (navegación, manipulador, vuelo, general) podrán agrupar métricas, pero el esquema común no debe imponer métricas específicas. Las restricciones del afinado usan `aggregation: "worst_case"` por defecto y se validan sobre todas las corridas; así, una media favorable no oculta un fallo aislado. Para objetivos se puede declarar `mean`, `median`, `min`, `max` o `p95`; para restricciones se puede elegir de forma explícita una agregación menos estricta, documentando por qué. Un métrico ausente invalida esa evaluación; nunca se transforma en cero.

## Perfil de robot

`examples/robot-profiles/turtlebot3-demo.json` ilustra un perfil portable con geometría, límites de velocidad, sensores requeridos y topics de referencia. Se valida con `simops profile validate <archivo>`. Al asociarlo a un manifiesto de afinado (`"robot_profile": "../robot-profiles/mi-robot.json"`), el parser impide que los límites superiores de `controller.vx_max` y `controller.wz_max` excedan la envolvente declarada. Esas declaraciones deben venir del fabricante/medición y no sustituyen calibración física ni criterios de seguridad certificados.
