# Plan de trabajo

## Objetivo

Convertir las herramientas de campañas de TFM_Rover en una plataforma que otras personas puedan conectar a sus propios simuladores, sistemas bajo prueba y métodos de evaluación. Debe permitir que una persona o un LLM configure una campaña, ejecute/reanude/cancele trabajos, inspeccione resultados y genere informes reproducibles.

MCP será una superficie de control sobre operaciones tipadas. El producto principal es el ciclo portable de experimentación, no el servidor MCP aislado.

## Criterios de éxito del proyecto

1. El núcleo se instala y opera sin ROS, Gazebo ni EasyNav.
2. Los datos de ejecución usan contratos versionados, con unidades, procedencia, estado de validez y motivo de ausencia.
3. Una misma especificación de campaña puede ejecutarse en al menos dos backends diferentes.
4. Una campaña se puede reanudar sin repetir resultados ya completos ni confundir fallo del sistema con fallo de infraestructura.
5. La salida JSON es canónica; Markdown y HTML se renderizan desde ese contrato y concuerdan.
6. El análisis declara población, exclusiones, n por grupo, semillas, método, intervalo de confianza y limitaciones.
7. Un agente MCP solo accede a acciones autorizadas por la política del espacio de trabajo.
8. La portabilidad se demuestra con una prueba de migración documentada desde el caso piloto, no solo con una arquitectura dibujada.

## Líneas de trabajo

| Línea | Trabajo | Resultado verificable |
|---|---|---|
| A. Descubrimiento y posición | Inventariar producto/código/papers; mapear capacidades y diferencias | Matriz de campo actualizada y afirmación de contribución acotada |
| B. Dominio y contratos | Definir campaña, escenario, prueba, corrida, evento, métrica, artefacto, procedencia | Esquemas versionados y documentación de compatibilidad |
| C. Adaptadores | Separar ejecución, simulador, sistema bajo prueba, adquisición de datos y escenarios | Adapter RAT/EasyNav inicial y un backend independiente |
| D. Evaluación | Definiciones versionadas de métricas, agregación, reglas, datos faltantes y estadísticas | Módulos puros y ficha reproducible por métrica |
| E. Campañas y optimización | Planificación declarativa, semillas, concurrencia, límites, reintentos, idempotencia, búsqueda | Runner reanudable y estrategias intercambiables |
| F. MCP y operación | Recursos legibles, herramientas acotadas, estado de campaña, límites y cancelación | Servidor MCP delgado sobre la API de aplicación |
| G. Informes | Contrato de análisis canónico; renderizadores Markdown/HTML y exportación de datos | Informe autogenerado con detalle, gráficos, advertencias y anexos |
| H. Validación | Repetir piloto, introducir fallos controlados, medir coste y reproducibilidad | Informe de validación y decisiones de release |

## Fases

### 0. Base de producto (actual)

- Crear repositorio independiente.
- Documentar investigación, auditoría, métricas y diseño de evaluación.
- Definir contratos Python sin dependencias ROS.
- Acordar el nombre, licencia y política de distribución antes de publicarlo.

### 1. Núcleo ejecutable

- Validador de manifiestos declarativos.
- Planificador de matriz escenario × configuración × semilla.
- Máquina de estados de campaña y corrida con persistencia append-only.
- Interfaz de adapter para ejecución, datos y reset; almacenamiento local inicial.
- CLI para inspeccionar y operar una campaña sin un LLM.
- Pruebas de contrato en adapters simulados. Esta fase no se considerará lista hasta verificar el código y los casos de fallo.

### 2. Adapter de referencia

- Portar una trayectoria vertical: preparar entorno, iniciar la simulación, ejecutar un objetivo, recoger métricas/artefactos y apagar limpiamente.
- Extraer la primera capa de datos RAT/EasyNav de ROS/Gazebo.
- Comparar corrida por corrida con TFM_Rover; registrar cualquier diferencia antes de declarar equivalencia.
- Mantener desactivada la ejecución en hardware real.

### 3. Métricas y reportes

- Reubicar métricas puras donde no importen ROS.
- Versionar definiciones y declararlas en un catálogo.
- Crear análisis por grupo, escenario, semilla y configuración.
- Generar JSON, Markdown y HTML a partir de una única estructura de resultados.
- Probar casos con telemetría faltante, ejecución interrumpida e infraestructura fallida.

### 4. MCP

- Añadir herramientas de consulta, validación, ejecución, estado, análisis, informe y cancelación.
- Separar lectura y escritura; operaciones que consumen recursos quedan limitadas por presupuesto y política.
- No exponer shell arbitraria ni destinos de hardware como valores por defecto.
- Registrar quién solicitó cada acción, manifiesto efectivo y resultado.

### 5. Portabilidad y escalado

- Añadir segundo backend en otra plataforma o dominio.
- Probar workers locales y remotos, capacidad y cuotas.
- Mantener opción de base local; almacenamiento y colas remotas son plugins, no requisito del núcleo.
- Usar LHS como screening reproducible y TPE/Optuna como optimizador opcional con restricciones y objetivos explícitos. El acoplamiento con ejecuciones se valida al implementar el runner.
- Documentar coste, paralelismo, recuperación y reproducibilidad.

### 6. Evaluación de contribución y distribución

- Repetir y comparar contra herramientas existentes en los casos que cubren.
- Medir facilidad de adaptación, esfuerzo de integración, reproducibilidad, cobertura y carga del operador.
- Publicar benchmark, especificaciones, datos de ejemplo y limitaciones.
- Revisar licencias de los repositorios y dependencias antes de incorporar código.

## Riesgos que influyen en el plan

- “Genérico” puede terminar siendo solo una capa de configuración sobre un único simulador; por eso el segundo backend es un criterio de éxito.
- El inventario de métricas es específico de navegación móvil. El núcleo debe tolerar perfiles de dominio distintos, sin imponer navegación.
- La verdad de terreno, el concepto de éxito y la instrumentación varían por caso; deben declararse mediante plugins/contratos.
- La concurrencia de campañas puede degradar la simulación y sesgar duración y temporización. El runner debe vigilar fidelidad/recursos y registrar cuándo descarta una corrida.
- Los resultados que sobreviven a éxito pueden sesgar las métricas de tiempo y calidad. Informes separan la probabilidad de éxito de métricas condicionadas al éxito.
- Una LLM puede proponer una evaluación defectuosa. Las métricas y límites críticos deben ser revisables y versionados fuera del modelo.
- Hay un hueco entre las infografías HTML manuales y el analizador reproducible actual; un informe bonito no debe ocultar el denominador ni las exclusiones.
