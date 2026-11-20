# Product roadmap

This repository can be inspected and run locally. The core, SQLite runner, SHA-256 artifacts, recovery, reports, LHS/TPE, and MCP server are connected. Tested adapters are the synthetic `demo` backend and a bounded Nav2/TurtleBot3 Docker route. The Nav2 adapter is a vertical slice, not evidence of universal portability.

## Current capability map

| Area | Implemented | Remaining work |
|---|---|---|
| Experiments | Strict JSON manifests, matrix planning, deterministic IDs, retries, cooperative cancellation, local resume | Version the schema formally; persist effective values read back from the simulator |
| Storage | Local SQLite campaigns/states/attempts/events; SHA-256 local blobs | Storage abstraction and retention; do not use SQLite as a distributed worker database |
| Search | Deterministic LHS and optional TPE/Optuna over real campaigns; constraints and Pareto results | Holdout confirmation, paired scenarios/seeds, sensitivity, and decision records |
| Reports | Canonical JSON and Markdown/HTML summaries, missingness, Wilson success intervals | Paired comparisons, bootstrap by experimental unit, charts, and downloadable tables |
| MCP | Local stdio, tuning preflight, bounded workspace, quotas, `demo` allowlist by default | Test with third-party MCP hosts and review adapters before enabling Docker |
| Navigation | Nav2 Lyrical/TurtleBot3 on a sandbox map and route | Add obstacle maps/scenarios; test cancellation, repeatability, and raw logs |
| Adapters | Nav2/TurtleBot3 example and generic plugin interface | Add a second robot/simulator with comparable safety and ground-truth measures |

## P0 — Release confidence

1. Run real LHS and TPE campaigns in Nav2/TurtleBot3 and generate reports. These runs demonstrate integration; they are not a benchmark or proof of improvement.
2. Verify an external user can install, validate, run, and tune the example from the manual without reading code. Fix failed steps and repeat.
3. Keep CI covering clean installation, `demo`, resumption, MCP workspace policy, and manifest validation. Keep Nav2 opt-in if CI cannot provide stable Docker/Gazebo.
4. Maintain Apache-2.0 and review dependencies, images, and data licenses before distributing additional assets.

## P1 — Demonstrate portability and results

1. Implement a small independent backend without ROS/Gazebo. Run the same contract: validate → plan → execute → persist → report → tune.
2. Add another navigation robot/simulator backend with reproducible metrics and examples, subject to code/data permissions.
3. Compare metrics with their source implementation and document clock, ground truth, contact, limit, and exclusion differences. Do not port a metric if its semantics cannot be preserved.
4. Confirm finalists on held-out scenarios, with more repetitions and paired design. Report uncertainty and failures, not just the selected candidate.

## P2 — Improve analysis and operations

1. Expose an adapter metric catalogue with ID, formula, unit, source, validity, coverage, and applicability.
2. Add metric layers: outcome/success, duration/efficiency, trajectory/control/safety, localization, sensors/ROS, CPU/memory/GPU, artifacts, and data quality.
3. Add paired comparison and bootstrap by scenario/seed; support robust intervals and sensitivity analysis. Do not treat telemetry messages as independent samples.
4. Add optional profiles for manipulators, aerial vehicles, and other domains without requiring the core to define navigation metrics.
5. Only after requirements are validated, evaluate remote schedulers, distributed workers, object storage, and per-backend credentials.

## Optimization policy

- Use TPE/Optuna when simulations are expensive and proposals should use earlier results; persist the study and seed.
- Keep hard safety limits separate from time/efficiency objectives. A candidate missing a required metric is not feasible.
- Aggregate over declared repetitions, scenarios, and seeds; report variation and failures. Preserve pairing when runs are paired.
- Separate search data from holdout data. Do not select and evaluate the “winner” on the same runs.
- Consider Gaussian-process BO for a few continuous dimensions when assumptions/noise justify it; Morris/Sobol for sensitivity when budget permits; use racing/pruning only after early fidelity predicts final ranking.
- Do not connect optimizers to real hardware in this version. Simulation constraints/results are not safety guarantees.

## Release condition

Publish a stable release only after CI passes, the manual works from a clean clone, and P0 items are closed. Announcements must say the tested backends are `demo` and Nav2/TurtleBot3 on one sandbox map, link installation and limitations, and avoid unmeasured portability/improvement claims. A second robot adapter and a second independent backend remain separate milestones.
