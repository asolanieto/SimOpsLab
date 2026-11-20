# SimOps Lab user manual

This guide covers the local SimOps Lab interface. The runner stores campaigns in SQLite, saves artifacts with SHA-256, and produces JSON, Markdown, and HTML reports. `demo` exercises the workflow without a simulator. `nav2-docker` is a Nav2/TurtleBot3 demonstration adapter for Gazebo Sim on one bundled map and route; other simulators connect through backend plugins.

## Requirements and installation

- Python 3.11 or later.
- The core and CLI do not require ROS, Gazebo, or optional dependencies.
- The Nav2 example requires Docker Engine with an accessible daemon, Linux `amd64`/x86_64, access to GHCR and Ubuntu Archive during image build, and several GB of free disk space.

From the repository root:

```sh
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
simops --help
simops backends
```

The editable install creates the `simops` command and lets the virtual environment discover installed backends. The database and reports are created relative to the current directory unless another location is provided.

To build the Nav2 demonstration image, run this once. The Dockerfile uses Nav2 Lyrical 1.5.3 pinned by digest and installs a pinned runtime dependency omitted from the upstream image:

```sh
docker build -f examples/nav2-turtlebot3/Dockerfile \
  -t simops-lab/nav2-turtlebot3:lyrical-1.5.3-gm1.3.46 .
```

## Quick start with the synthetic backend

```sh
simops profile validate examples/robot-profiles/turtlebot3-demo.json
simops validate examples/demo-campaign.json
simops plan examples/demo-campaign.json
simops run examples/demo-campaign.json
simops status demo-navigation-smoke
simops report demo-navigation-smoke
simops tune examples/demo-tuning.json
```

The synthetic example explores parameters, persistence, and reports. It does not model Nav2 physics or robot performance. Results from `demo` are not evidence about a robot.

## Workflow

1. Write a JSON manifest.
2. Use `simops backends` to inspect installed adapters.
3. Run `simops validate MANIFEST.json` to validate the matrix and backend acceptance.
4. Run `simops plan MANIFEST.json` to inspect the planned runs.
5. Run `simops run MANIFEST.json` to store the campaign and execute it.
6. Inspect `simops status CAMPAIGN_ID`; resume incomplete work with `simops resume CAMPAIGN_ID`.
7. Use `simops report CAMPAIGN_ID` to regenerate reports from stored data.
8. Optionally define and run parameter search with `simops tune TUNING.json`.

`plan` expands the matrix but does not validate the backend or persist the campaign. `validate` loads the backend and calls its validation for every run but does not start or persist execution.

## Campaign manifest v0.1.0

The loader accepts JSON with `schema_version`, `backend`, and `campaign`; unknown keys are rejected. Configuration and parameter values are JSON objects. The illustrative YAML planner sketch is not parsed by SimOps.

```json
{
  "schema_version": "0.1.0",
  "backend": "demo",
  "campaign": {
    "campaign_id": "demo-navigation-01",
    "title": "Synthetic navigation check",
    "systems": ["controller-a"],
    "scenarios": [
      {"scenario_id": "easy", "parameters": {"difficulty": 0.2, "distance_m": 8.0}},
      {"scenario_id": "hard", "parameters": {"difficulty": 0.7, "distance_m": 12.0}}
    ],
    "configurations": [
      {"configuration_id": "baseline", "values": {"max_speed_mps": 0.45, "controller_gain": 1.0, "inflation_radius_m": 0.45}},
      {"configuration_id": "cautious", "values": {"max_speed_mps": 0.35, "controller_gain": 1.2, "inflation_radius_m": 0.55}}
    ],
    "repetitions": 3,
    "seeds": [11, 22, 33],
    "max_parallel": 1,
    "max_infrastructure_retries": 1,
    "wall_time_budget_s": 600,
    "metadata": {"purpose": "tutorial"}
  }
}
```

The matrix is `systems × scenarios × configurations × repetitions`; the example plans 12 runs. Run IDs are derived deterministically from the run identity and parameters.

Manifest fields:

- `schema_version`: currently exactly `"0.1.0"`.
- `backend`: installed backend name, such as `demo`.
- `campaign_id`, `title`: non-empty strings. The ID identifies the campaign in the local database.
- `systems`: non-empty list of unique, non-empty IDs.
- `scenarios`: non-empty list of objects with `scenario_id` and optional object `parameters` (defaults to `{}`).
- `configurations`: non-empty list with `configuration_id` and optional object `values` (defaults to `{}`).
- `repetitions`: integer of at least 1.
- `seeds`: optional list of unique integers, one per repetition, in the same order. If omitted, each run has `seed: null` and the backend controls randomness.
- `max_parallel`: integer of at least 1, default 1. A backend must declare `thread_safe` to allow values above 1.
- `max_infrastructure_retries`: additional retries for infrastructure failures; non-negative integer, default 0.
- `wall_time_budget_s`: optional finite number greater than zero. It prevents new runs from starting after the budget expires; it does not forcibly end a running backend call.
- `metadata`: optional JSON object, default `{}`.

The planner checks for empty or duplicate IDs and finite JSON values. A backend can add domain-specific validation.

## CLI behavior and persistence

Useful commands:

```sh
simops backends
simops validate CAMPAIGN.json
simops plan CAMPAIGN.json --json
simops run CAMPAIGN.json
simops status demo-navigation-01
simops resume demo-navigation-01
simops report demo-navigation-01
simops tune examples/demo-tuning.json
simops validate examples/nav2-turtlebot3/campaign.json
simops run examples/nav2-turtlebot3/campaign.json
simops tune examples/nav2-turtlebot3/tuning.json
```

`run`, `resume`, `status`, `report`, and `tune` accept `--store PATH`; the default is `.simops/campaigns.sqlite3`. `run`, `resume`, and `report` accept `--report-dir PATH`; the default is `.simops/reports`. Reports are written under a campaign-specific directory. `run` and `resume` create reports when they finish; `report` regenerates them without rerunning simulations. `tune` accepts `--result-dir PATH`; the default is `.simops/tunings`.

Running the same manifest with the same ID reuses terminal results and works on incomplete runs. Reusing an ID with a different manifest, backend, or backend version is rejected; use a new ID for a different campaign.

`status` returns JSON with campaign/backend identity, manifest fingerprint, per-run state and attempt counts, infrastructure failure count, event count, and latest event. The full journal remains in SQLite; the CLI does not currently list every event or every attempt result.

On process interruption, `resume` marks runs left in `running` as interrupted and decides whether they can be retried. It uses the stored specification, so the original manifest is not required. The backend must remain installed at the stored `backend_version`; a version change requires a new campaign ID.

The runner takes an OS lock per SQLite database and campaign ID while coordinating `run` or `resume`. Local processes cannot execute the same campaign simultaneously; a second process waits up to 30 seconds. The database does not coordinate different hosts.

Ctrl+C during `run` or `resume` requests cooperative cancellation through `context.cancellation_requested`; new runs are deferred. There is no CLI `cancel` command or forced termination of an active run.

## Nav2/TurtleBot3 Docker example

`examples/nav2-turtlebot3/campaign.json` runs the bundled Nav2 sandbox map with TurtleBot3 Waffle. `tuning.json` screens three LHS candidates across two routes. Each candidate runs headlessly in its own container; candidates run sequentially to isolate DDS and Gazebo. The adapter combines the selected values with the default Nav2 YAML and stores logs, overrides, and measurements as artifacts.

Tunable parameters in this adapter:

- `controller.vx_max`: MPPI maximum linear speed, 0.1–0.8 m/s.
- `controller.wz_max`: MPPI maximum angular speed, 0.2–2.5 rad/s.
- `controller.temperature`: MPPI temperature, 0.05–2.0.
- `costmap.inflation_radius_m`: local and global costmap inflation radius, 0.25–1.0 m.

The default route starts at `(-2.0, -0.5)` and targets `(0.0, -0.5)` in the sandbox map. Configure `start_x`, `start_y`, `start_yaw`, `goal_x`, `goal_y`, `goal_yaw`, and `timeout_s` (10–600 s). The backend records action state, wall/simulation time, odometry path, minimum laser range, command peaks/rate, saturation fraction, angular sign changes, RMS angular acceleration, odometry sample count, and time to the first zero command after success. See the [metric catalogue](metrics-catalog.md) for definitions.

The adapter does not measure Gazebo contacts, footprint clearance, ground truth, or localization error, so it cannot establish safety. The bundled world is deterministic and the SimOps `seed` field does not configure a Gazebo seed; do not treat repeats as independent randomized trials.

```sh
simops validate examples/nav2-turtlebot3/campaign.json
simops run examples/nav2-turtlebot3/campaign.json
simops tune examples/nav2-turtlebot3/tuning.json
```

To use TPE instead of LHS, install Optuna and use `tuning-tpe.json`:

```sh
python -m pip install -e ".[optimize]"
simops tune examples/nav2-turtlebot3/tuning-tpe.json
```

The LHS budget counts candidates; each example candidate expands to four navigation runs. Inspect `tuning.md` and `tuning.json`, compare success and metrics with the baseline, and confirm promising candidates with additional scenarios and conditions. A result from this route does not establish safety or generality across maps or robots.

## Install a backend plugin

Third-party backends are discovered through Python entry points in the `simops.backends` group. Declare one in the adapter package's `pyproject.toml`:

```toml
[project.entry-points."simops.backends"]
my_simulator = "my_package.backend:Backend"
```

Install the package in the same environment as SimOps. `simops backends` should list `my_simulator`; manifests must use that exact name. Duplicate entry-point names cause loading to fail.

The backend object provides:

- `backend_id`: the same name as the entry point.
- `backend_version`: version identifying the implementation.
- `thread_safe`: concurrency is allowed only when this is true.
- `validate(run)`: returns error messages; an empty sequence accepts the run.
- `execute(run, context)`: executes one run and returns `RunResult`.

The entry point may target a class (instantiated without arguments) or an existing object. `run` is a `RunSpec` with `run_id`, system, scenario, configuration, repetition, seed, and parameters. `context` is an `ExecutionContext` with attempt number, work directory, artifact store, optional monotonic deadline, and cooperative cancellation signal. Store bytes with `context.artifacts.put(name, content, mime_type, schema_version)`; it returns an `ArtifactRef` with SHA-256 URI, hash, and size.

The runner verifies matching `run_id`, terminal status, metric consistency, and non-negative artifact sizes. Exceptions from `execute` are infrastructure failures. SimOps adds the real backend ID and version to result provenance.

## Run states and retries

Operational run state is separate from functional system outcome:

- Run states: `planned`, `queued`, `running`, `completed`, `failed_system`, `failed_infrastructure`, `cancelled`, and `interrupted`. The local runner generally moves from planned to executing and then terminal; `queued` is defined in the contract but is not persisted as a queue phase.
- Functional outcomes: `success`, `failure`, `expected_abort`, `unknown`, or `not_applicable`. A run can be operationally `completed` with `system_outcome=failure`.
- Campaign states: `running`, `paused`, `failed`, `completed_with_system_failures`, or `completed`. `paused` means runs remain, for example after cancellation or budget exhaustion. `failed` means infrastructure failures/interruption remain without retries. Functional failures are reflected in `completed_with_system_failures`.

Each attempt is stored in SQLite. Infrastructure failures and interruptions can retry up to `max_infrastructure_retries` in addition to the first attempt. Functional failures are not retried automatically. On resume, completed, system-failed, and cancelled runs are terminal; infrastructure-failed or interrupted runs resume only if retries remain. An expired budget prevents new runs; the backend receives a deadline to check during execution.

## Metrics and reports

Metrics are emitted by the backend in `RunResult`; the CLI does not calculate simulator measurements. Each `MetricValue` contains `metric_id`, value, optional unit, `definition_version`, and state. Supported states are `observed`, `not_applicable`, `missing`, and `invalid`. An observed value requires data; other states use `null` and a reason. Missing or invalid data is never treated as zero.

Reports are `analysis.json`, `report.md`, and `report.html`, generated from one analysis model and grouped by system, scenario, and configuration. They show planned/result runs, state/outcome counts, and metric summaries:

- Numeric: observed/planned count, missing count, mean, median, quartiles, minimum, and maximum.
- Boolean: true count and proportion among observed values.
- Other values: type and distinct observed values.
- All summaries preserve units, metric-definition versions, non-observed states, and reasons.
- Success shows known outcomes and a 95% Wilson interval; unknown/not-applicable outcomes and infrastructure-failed/interrupted runs are excluded from that denominator.

JSON is the structured source. Reports state that conclusions apply only to the supplied campaign and recommend separate scenarios or seeds for configuration selection and holdout confirmation. The current renderer does not include charts, PDF, or statistical comparison between configurations. It also does not show every attempt in report tables; inspect `status` and retain SQLite for operational history.

## Synthetic `demo` backend and limits

`demo` is deterministic synthetic data with pseudo-random variation from the supplied seed (or run ID). It emits `task.success`, `task.duration_s`, `safety.collision_count`, `navigation.path_length_m`, and `safety.min_clearance_m`. It accepts `max_speed_mps` 0.1–1.5, `controller_gain` 0.2–2.5, and `inflation_radius_m` 0.05–1.0. Scenarios accept `difficulty` 0–1 and positive `distance_m`; defaults apply when omitted.

These values come from formulas. `demo` does not start a simulator, model physics, run ROS, or describe robot performance. Use it to learn the CLI, validate formats, and generate an example report only.

## Parameter tuning

`simops tune` proposes candidates, runs the declared campaign matrix for each, and compares specified metrics. See [examples/demo-tuning.json](../examples/demo-tuning.json). To use TPE, install the optional dependency:

```sh
python -m pip install -e ".[optimize]"
simops tune examples/nav2-turtlebot3/tuning-tpe.json
```

A tuning manifest contains `schema_version: "0.1.0"`, `backend`, and `tuning`. The `tuning` object supports:

- `tuning_id`, `title`, and `strategy` (`lhs` or `tpe`; default `lhs`).
- Positive integer `budget`: new trials requested per invocation. TPE results can also include earlier study trials. LHS uses `seed`; rerunning the same manifest can propose the same parameters and reuse completed campaigns.
- Optional `base_configuration`; each candidate overlays values with matching names.
- `parameters` with kind `float`, `integer`, or `categorical`. Numeric parameters require `lower` and `upper`, and may specify `step` or log sampling. Categorical parameters declare `choices`.
- One or more `objectives` with `metric_id` and direction `minimize` or `maximize`.
- Optional `constraints` with `constraint_id`, description, `metric_id`, operator `<=` or `>=`, and a finite numeric threshold.
- `campaign` with `systems`, `scenarios`, and `repetitions`, plus optional seeds, concurrency, retries, wall-time budget, and metadata. Use the same scenarios/seeds for every candidate.
- Optional `seed`, `workers`, `n_startup_trials`, `study_name`, and `storage_url`. Defaults: study seed 0, one worker, 10 TPE startup trials, and `study_name=tuning_id`.

Every candidate expands the systems × scenarios × repetitions matrix; each run result is retained. Objectives use `mean` by default and support `median`, `min`, `max`, and `p95`. A metric must be observed, numeric, and cover every run; otherwise the candidate is invalid and excluded from the Pareto front. Infrastructure failures remain visible and receive no fabricated objective value. Boolean metrics such as `task.success` convert to 0/1 for aggregation.

Constraints use `worst_case` by default: maximum for `<=` and minimum for `>=`, so one violation makes the candidate infeasible. Explicit aggregations `mean`, `median`, `min`, `max`, and `p95` are also available. Missing or incomplete metrics invalidate an evaluation. With multiple objectives, SimOps returns the feasible Pareto front instead of selecting one winner. Constraints guide search; they do not certify safety.

LHS needs no extra dependency. TPE uses Optuna; without `storage_url`, its study persists under `.simops/optuna/` next to the default `--store`. One worker is supported with SQLite. Multiple workers require shared RDB storage such as PostgreSQL or MySQL. On a repeated TPE study, `budget` counts new trials for that invocation while the result includes prior history.

`tune` writes `tuning.json` and `tuning.md` under `.simops/tunings/<tuning-id>` or the provided `--result-dir`. JSON retains candidate states, parameters, objectives, constraints, and failure reasons; Markdown summarizes the Pareto front and constraint margins. The campaign journal stores runs used to evaluate candidates. Treat search as exploratory and confirm finalists on held-out scenarios or seeds.

## Robot capability profiles

Declare the footprint, kinematic limits, and available signals before tuning. Profiles are versioned JSON:

```sh
simops profile validate examples/robot-profiles/turtlebot3-demo.json
```

In a tuning manifest, `robot_profile` points to a profile relative to that manifest. SimOps checks that upper bounds for `controller.vx_max` and `controller.wz_max` fit the declared envelope. The backend must map those parameters into the actual configuration and record effective values. Profile declarations must come from manufacturer data or measurement; they do not replace physical calibration or certified safety criteria.

## MCP operation

Install the MCP extra and configure a workspace. Agent-accessible manifests belong under `workspace/manifests`:

```sh
python -m pip install -e ".[mcp]"
mkdir -p workspace/manifests
cp examples/demo-campaign.json workspace/manifests/
mkdir -p workspace/robot-profiles
cp examples/robot-profiles/turtlebot3-demo.json workspace/robot-profiles/
simops mcp --workspace ./workspace
```

Only `demo` is allowed by default. To use Nav2, the operator must explicitly enable it with `--allow-backend nav2-docker`. MCP can start Docker installed on that host. Installing a plugin does not enable it. The tool list includes manifest/backend inspection, validation, planning, campaign execution/status/results, resumption/cancellation, report generation, and tuning. There is no shell tool or arbitrary path access. See [mcp.md](mcp.md) for quotas and boundaries.

`get_campaign_result` returns structured metrics grouped by scenario and configuration. `render_report` writes JSON, Markdown, and HTML files locally and returns workspace-relative paths. MCP does not expose artifact contents or the full per-attempt event history.

## Current limitations

- The Nav2/TurtleBot3 adapter covers only the bundled sandbox route; other simulators need their own adapter.
- CLI cancellation is not available; MCP cancellation is cooperative.
- The renderer has no PDF or charts and does not yet produce a statistical comparison between configurations.
- Profile bounds validate configured values; the backend must also verify effective values and observed command limits.
- The included Nav2 run does not provide contact events, ground truth, footprint clearance, localization error, ROS diagnostics, or resource telemetry.
