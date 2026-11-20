# Diseño de evaluación y generación de informes

## Principios

1. **Resultado canónico**: cada corrida produce un registro estructurado versionado. El informe no calcula una segunda versión de las métricas a escondidas.
2. **Separar sistema e infraestructura**: una navegación que no llega es fallo del sistema; simulador caído, adapter sin respuesta, datos corruptos o presupuesto agotado son fallo operativo/infraestructura.
3. **Desconocido no es cero**: toda métrica guarda estado (`observed`, `not_applicable`, `missing`, `invalid`) y motivo.
4. **Referencia declarada**: ground truth, sensor externo, estimación propia o referencia analítica se identifican por corrida. Se prohíbe presentar el error contra la misma señal evaluada como error independiente.
5. **No ocultar población**: presentar intentos planificados, completos, válidos, excluidos y motivo; el denominador aparece junto a cada proporción.
6. **Separar exploración y confirmación**: parámetros se seleccionan en escenarios/semillas de ajuste y se confirman en hold-out fijado antes de ver resultados.
7. **Preservar crudos**: guardar logs y señales con retención configurada. Los agregados no sustituyen el dato de origen.

## Ciclo de datos

`Campaña declarativa → corridas planificadas → adapter ejecuta → artefactos y telemetría → plugins calculan métricas → validador calcula estados/exclusiones → analizador compara grupos → JSON canónico → renderizadores Markdown/HTML`

Cada registro contiene como mínimo:

- Identificadores de campaña, corrida, escenario, sistema, configuración y repetición.
- Estado operativo de corrida y resultado funcional del sistema, en campos independientes.
- Seed, variables del escenario, valores solicitados y efectivos, versiones de código/simulador/adapter/metric plugin.
- Huellas de contenedor/paquete, host y recursos relevantes, commit o estado sucio cuando se conozca.
- Relojes, referencia, política de sincronización y criterio de éxito.
- Métricas con unidad, versión, estado, motivo de ausencia y cobertura.
- Artefactos con ruta/URI, mime type, tamaño, checksum y esquema.
- Intentos, reintentos, interrupciones, avisos y eventos de ejecución.

## Protocolo estadístico

### Descripción por grupo

- Para proporciones de llegada, colisión, cancelación, violación de criterio y fallos: mostrar (k/n), intervalo de confianza del 95% (Wilson por defecto para proporciones pequeñas/moderadas) y número excluido con motivo.
- Para continuas: mostrar (n), mediana, Q1, Q3, media/desviación solo cuando se necesiten; percentiles 5/95 para colas si están predefinidos.
- Tiempo de llegada y eficiencia condicionados a llegar se marcan explícitamente como “entre éxitos”. Al lado mostrar tasa de éxito para reducir sesgo de superviviente.
- Para seguridad: mostrar eventos por corrida y por unidad de exposición (tiempo/distancia) cuando el dominio lo permita; una tasa media no sustituye el conteo de severidad.
- Informar datos inválidos, telemetría ausente, cola truncada y calidad de medición.

### Comparación de configuraciones

- Comparar primero resultados primarios definidos a priori; evitar convertir todo en una sola nota.
- Si escenarios y semillas están emparejados, calcular diferencias pareadas. Si hay bloqueo por escenario, conservar el emparejamiento y reportar intervalo del efecto pareado; no tratar toda corrida como iid.
- Bootstrap con semilla explícita es una opción para intervalos de diferencia; remuestrear la unidad experimental correcta (escenario/semilla), no mensajes.
- Para múltiples métricas o configuraciones, declarar corrección de multiplicidad o marcar comparación como exploratoria.
- Dar diferencia absoluta, efecto relativo si aplica, IC 95%, n por lado, unidad y criterio de “diferencia relevante”.
- Bajo n, mostrar “evidencia insuficiente” en vez de “igual”; el umbral no debe esconder la amplitud del intervalo.
- Tratar condiciones duras de seguridad como restricciones, no compensarlas con tiempo o eficiencia en un coste medio.
- El óptimo seleccionado debe repetirse en un conjunto de validación distinto; la elección de métricas, umbrales y pesos se versiona.

### Infraestructura y exclusiones

- Reintentos de infraestructura tienen registros propios; conservar intento original y motivo.
- No borrar fallos de infraestructura del informe: excluir del denominador funcional, reportar su número y tasa aparte.
- Fallo del stack/SUT con simulador sano sí pertenece al resultado funcional.
- Si los sensores/telemetría crítica faltan, el criterio queda desconocido, no aprobado.
- Marcar ejecuciones con RTF degradado, tiempo sim inconsistente, condiciones externas o corte de sesión; política de incluir/excluir debe fijarse por protocolo.
- Cancelar no equivale a fallo: representar cancelación esperada y seguridad de parada por separado.

## Estructura recomendada del informe

### 1. Portada/alcance

Nombre del experimento, fecha, objetivo, sistema/backends, commit/versiones, autor/política de ejecución, criterios primarios y alcance del conjunto de datos.

### 2. Resumen ejecutivo

- Corridas planificadas/completadas/excluidas y por qué.
- Éxito funcional y seguridad con (k/n) e IC.
- Diferencias primarias, efecto e IC.
- Recomendación condicionada por operación.
- Dos o tres hallazgos, incertidumbres y limitaciones.

### 3. Configuración y reproducibilidad

Matriz de factores y escenarios, rangos, semillas, orden aleatorio, parámetros efectivos, software, hardware, versiones y hashes de artefactos.

### 4. Protocolo y validez

Criterio de éxito, señal de referencia, métricas pre-registradas, unidad experimental, análisis planeado y tratamiento de fallos/faltantes.

### 5. Resultados

- Tabla por configuración/escenario.
- Llegada y seguridad primero.
- Tiempo/eficiencia condicionados a éxitos.
- Localización, control/suavidad, fiabilidad del stack y recursos.
- Matriz de escenarios, distribución y calidad de datos.
- Trazas representativas con selección explicada, no solo las “más bonitas”.

### 6. Diagnósticos y artefactos

Eventos destacados, causas observables, trazas/bags/logs, corridas omitidas y enlaces locales/exportables.

### 7. Conclusiones y límites

Afirmaciones limitadas a condiciones probadas; siguiente experimento recomendado y motivos.

### 8. Apéndices

Manifiesto, catálogo/versión de métricas, fórmulas, estadística, diccionario del esquema, archivos fuente y dependencias.

## Infografías

Se pueden generar visualizaciones HTML interactivas, pero cada panel debe mostrar n, denominador, intervalo, unidad, filtro y leyenda. La tabla accesible y el archivo JSON deben poder responder la misma pregunta. PDF se deja como renderizador posterior, no como formato de datos.

Los tres HTML actuales tienen contenido valioso, pero el código común observado genera JSON/Markdown corto y gráficas individuales, no estos informes de campaña. La nueva plataforma deberá recrear una campaña histórica desde sus datos y producir una página comparable sin editar números a mano.
