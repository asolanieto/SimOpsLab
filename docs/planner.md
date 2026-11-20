# Campaign matrix planner

The first executable building block is a dependency-free Python function:

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

The planner expands system × scenario × configuration × repetition into stable IDs derived from the run identity and effective values. Changing a parameter while keeping its label changes the IDs.

Seeds are paired by repetition index across scenarios, systems, and configurations. If no seeds are supplied, the backend controls randomness and the manifest should record the effective seed at runtime. The planner validates duplicate/empty IDs, repetition count, seeds, parallelism, retries, and time budget.

This code only creates the plan. It does not validate backend parameter schemas, run simulators, persist transitions, or produce reports. `examples/campaign-sketch.yaml` is illustrative and has no parser.
