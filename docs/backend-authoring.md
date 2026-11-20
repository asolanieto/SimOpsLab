# Crear un backend para tu robot o simulador

SimOps separa el motor de campañas del acceso al simulador. Cada backend implementa cuatro piezas: identidad versionada, validación previa, ejecución aislada de una corrida y `RunResult` con métricas tipadas y artefactos. No se requiere ROS.

## Interfaz mínima

Implementa `ExperimentBackend` de `simops.backends`:

```python
class MyBackend:
    backend_id = "my-robot-sim"
    backend_version = "0.1.0"
    thread_safe = False

    def validate(self, run: RunSpec) -> Sequence[str]:
        ...

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        ...
```

`RunSpec` incluye configuración, escenario, repetición y semilla solicitada. `ExecutionContext` ofrece un workspace por intento, almacenamiento de artefactos, deadline y cancelación cooperativa. Si tu simulador no acepta la semilla, decláralo en `provenance`; no informes reproducibilidad como si se hubiera aplicado.

## Instrumentación que hace útil el afinado

1. Separa outcome funcional de fallo de infraestructura.
2. Para cada métrica, emite ID estable, definición versionada, unidad, estado (`observed`, `missing`, `invalid` o `not_applicable`), fuente, cobertura y razón.
3. Conserva señales de referencia independientes cuando midas error de localización o seguimiento.
4. Cuenta contactos desde el simulador para evaluar colisión; un rayo lidar corto no los reemplaza. Calcula holgura de la huella con geometría sincronizada.
5. Conserva tiempo de pared y simulado por separado, y reporta cobertura/reloj.
6. Copia configuración efectiva y versiones/digest del robot, mapa, plugin y simulador a `provenance`; archiva rosbag/MCAP/trazas bajo hash.
7. Declara `thread_safe=False` si dos procesos podrían compartir el mismo mundo, puerto, GPU o configuración.

El afinado invalida candidatos con métricas requeridas ausentes. Sus restricciones son de peor caso entre corridas, salvo que el manifiesto declare otro estimador. La selección final requiere escenarios y semillas hold-out.

Registra el backend como entry point Python `simops.backends`; ve `pyproject.toml` para el ejemplo Nav2. MCP no expone shell: el servidor invoca únicamente backends permitidos y manifiestos dentro del workspace autorizado.

Los perfiles de robot documentan límites y sensores, pero no inventan una implementación. Conecta sus valores a parámetros efectivos del backend y valida los parámetros de tuning contra la envolvente del robot.
