# MCP local de SimOps

El server MCP es un adaptador fino sobre las mismas operaciones que usa el CLI. Usa el SDK oficial de Python por transporte `stdio`; no abre un puerto de red.

## Instalación e inicio

```sh
python -m pip install -e ".[mcp]"
mkdir -p workspace/manifests
cp examples/demo-campaign.json workspace/manifests/
simops mcp --workspace ./workspace
```

Configura el host MCP para iniciar ese comando en un proceso local. El workspace contiene `manifests/`, perfiles de robot bajo `robot-profiles/` y `.simops/`; campañas, artefactos, estudios TPE e informes quedan bajo `.simops/`. Los perfiles deben resolver dentro del workspace, nunca fuera.

Si el operador instaló un adapter fiable, debe habilitarlo explícitamente:

```sh
simops mcp --workspace ./workspace --allow-backend demo --allow-backend nav2-docker
```

La lista predeterminada solo incluye `demo`. Instalar un plugin de backend no basta para que el LLM pueda seleccionarlo.

## Herramientas

| Tool MCP | Función |
|---|---|
| `list_backends` | Lista adapters instalados y permitidos por el operador. |
| `list_manifests` | Lista nombres JSON en el directorio de manifiestos. |
| `validate_campaign` | Valida un manifiesto sin empezar corridas ni guardarlo. |
| `plan_campaign` | Expande y devuelve el plan de ejecuciones. |
| `start_campaign` | Registra la huella y ejecuta en segundo plano. |
| `resume_campaign` | Reanuda intentos pendientes de una campaña del mismo workspace. |
| `get_campaign_status` | Devuelve estado de campaña, corridas, intentos y último evento. |
| `cancel_campaign` | Solicita cancelación cooperativa del job activo. |
| `render_report` | Genera JSON, Markdown y HTML desde resultados guardados. |
| `validate_tuning` | Comprueba perfil, parámetros extremos, presupuesto, escenarios y criterios de un tuning antes de ejecutarlo. |
| `start_tuning` | Ejecuta el manifiesto de afinado con LHS o TPE permitidos. |
| `get_tuning_result` | Devuelve el resultado guardado o estado del afinado. |

## Límites del workspace

- Las tools reciben un nombre de archivo simple terminado en `.json`, no una ruta arbitraria. Se rechazan rutas con directorios y symlinks; la búsqueda se limita a `<workspace>/manifests`.
- Por defecto se permiten hasta 500 corridas por campaña, 8 corridas paralelas, una hora de pared, 50 candidatos por invocación de afinado y 5.000 corridas totales por afinado.
- No hay tool para shell, Python arbitrario, acceso a archivos externos, SSH ni selección de hardware real.
- El runner usa SQLite local. Un MCP instalado en una estación de trabajo debe compartir el mismo workspace para ver y reanudar una campaña.
- SIGINT y la tool de cancelación envían una señal cooperativa; un adapter en curso debe consultar su `ExecutionContext` y limpiar el proceso del simulador.
- Los plugins de backend son código Python de confianza. El operador solo debe instalar y permitir adapters revisados; el allowlist MCP no puede aislar un plugin malicioso.
- Stdio confía en el host local que lanza el proceso. El server no está configurado para exposición HTTP remota.

Las tools son asíncronas y el inicio de una campaña/afinador retorna un ID; el agente consulta después su estado. Para afinados de larga duración, el manifiesto determina presupuesto, réplicas y objetivos; el informe advierte que los finalistas necesitan confirmación hold-out.
