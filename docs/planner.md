# Planner de matrices

El primer bloque ejecutable es una función Python sin dependencias externas:

~~~python
from simops import (
    CampaignMatrix,
    ConfigurationDefinition,
    ScenarioDefinition,
    plan_campaign,
)

plan = plan_campaign(
    CampaignMatrix(
        campaign_id="nav-smoke",
        title="Smoke test",
        systems=("controller-a", "controller-b"),
        scenarios=(ScenarioDefinition("open"), ScenarioDefinition("obstacle")),
        configurations=(ConfigurationDefinition("baseline", {"gain": 1.0}),),
        repetitions=3,
        seeds=(11, 22, 33),
    )
)
~~~

El planner expande la combinación sistema × escenario × configuración × repetición en IDs estables derivados de la identidad y valores efectivos de cada corrida. Así, cambiar un parámetro manteniendo su etiqueta cambia los IDs.

Los seeds se emparejan por índice de repetición entre escenarios, sistemas y configuraciones. Si no se suministran, el backend controla la aleatoriedad y el manifiesto deberá registrar la semilla efectiva al ejecutar. El planner valida IDs duplicados/vacíos, número de repeticiones, seeds, paralelismo, reintentos y presupuesto de tiempo.

Este código solo crea el plan. No valida todavía esquemas de parámetros del backend, ejecuta simuladores, persiste transiciones ni produce el informe. El ejemplo YAML de examples/campaign-sketch.yaml es ilustrativo y no tiene parser.
