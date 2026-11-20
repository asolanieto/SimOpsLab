# Architecture

## System boundary

The core organizes experiments and results. It does not model physics, understand ROS topics, require Gazebo, or send commands to hardware. An adapter translates between the core contract and the system under test.

## Components

- **Specification and validation:** declarative campaign, scenario, configuration, repetition, seed, metric, and limit definitions.
- **Planner:** expands the experiment matrix into stable runs with deterministic IDs.
- **Campaign service:** state, persistence, retries, budget, concurrency, cancellation, and resumption.
- **Backend adapter:** prepares, launches, observes, finalizes, and collects artifacts from an environment.
- **Metric plugins:** derive versioned, validity-aware measurements from telemetry and artifacts.
- **Analysis engine:** validates criteria, summarizes groups, represents uncertainty, identifies anomalies, and separates screening from confirmation.
- **Artifact store:** local blobs initially, behind an extensible interface.
- **Report renderers:** Markdown and HTML derived from the canonical analysis result.
- **CLI/API:** human interface; MCP is another client of the same application API.

## Implementation status

Implemented components include the deterministic planner, JSON parser/validator, local SQLite runner, SHA-256 artifacts, JSON/Markdown/HTML reports, CLI, LHS campaign tuning, optional TPE/Optuna, and local MCP server. The synthetic `demo` backend exercises the core; `nav2-docker` connects the same runner to Nav2/TurtleBot3 on a sandbox map.

The `nav2-docker` adapter uses an image pinned by digest, runs one navigation per container, and collects action state, odometry, laser scans, commands, and logs. It covers only the bundled demo map/route; users must define scenarios and validation for other systems. `demo` does not test physics, Gazebo, or ROS. TPE requires the Optuna extra. MCP is an optional stdio extra; it defaults to `demo`, reads manifests from a dedicated workspace, and enforces quotas. Other simulators and stacks need their own adapters.

## Ports and adapters

1. `ExecutionBackend`: location and budget (local, Docker, SSH, Slurm, or another scheduler).
2. `ExperimentBackend`: prepare and execute one run of the system under test.
3. `ObservationProvider`: structured signals, files, logs, bags, or remote telemetry.
4. `ScenarioProvider`: enumerate, create, and validate backend scenarios.
5. `MetricPlugin`: derive `MetricValue` from runs, signals, and artifacts.
6. `SearchStrategy`: tune through a backend-agnostic evaluator; LHS and TPE/Optuna are available.
7. `ArtifactStore`: save/import files and checksums.
8. `ReportRenderer`: render an already computed analysis model.

A higher-level adapter can implement several ports when useful. Interfaces remain replaceable to avoid coupling the core to one stack.

## States and failures

- Run: `planned → queued → running → completed | failed_system | failed_infrastructure | cancelled | interrupted`.
- System outcome: `success | failure | expected_abort | unknown | not_applicable`.
- Each metric has an independent state. A completed run may contain missing metrics; an infrastructure failure may preserve partial metrics.
- Execution is idempotent by `run_id`; persist a transition and event before marking the job complete.

## MCP surface

Read tools: `list_backends`, `list_manifests`, `get_campaign_status`, `get_campaign_result`, and `get_tuning_result`.

Write tools: `validate_campaign`, `plan_campaign`, `start_campaign`, `resume_campaign`, `cancel_campaign`, `render_report`, `validate_tuning`, and `start_tuning`.

Tools accept IDs or manifest names inside the workspace and enforce workspace policy, quotas, concurrency, and timeouts. There is no generic `run_shell` tool. Local stdio MCP is implemented; HTTP and hardware access are not enabled by default.

## First vertical slice

Simple manifest → test/simulation backend → one run → generic metrics → local artifacts → JSON result → Markdown report. Add simulator- or robot-specific adapters later while preserving the core contracts.
