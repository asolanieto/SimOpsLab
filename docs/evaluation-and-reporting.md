# Evaluation and reporting design

## Principles

1. **Canonical result:** each run produces a versioned structured record. A report must not silently calculate a second version of a metric.
2. **Separate system and infrastructure:** a navigation system that fails to reach a goal is a system failure; a crashed simulator, unresponsive adapter, corrupt data, or exhausted infrastructure budget is an operational failure.
3. **Unknown is not zero:** each metric carries a state (`observed`, `not_applicable`, `missing`, or `invalid`) and a reason.
4. **Declare the reference:** identify ground truth, external sensor, self-estimate, or analytical reference per run. Never present error against the evaluated signal itself as an independent error measure.
5. **Expose the population:** show planned, completed, valid, and excluded attempts with reasons. Put denominators next to every proportion.
6. **Separate exploration and confirmation:** select parameters on tuning scenarios/seeds and confirm on holdout fixed before examining results.
7. **Preserve raw data:** store logs and signals under a configured retention policy. Aggregates do not replace source data.

## Data flow

`Declarative campaign → planned runs → adapter execution → artifacts/telemetry → metric plugins → validation/exclusions → group analysis → canonical JSON → Markdown/HTML renderers`

Every record should contain at least:

- Campaign, run, scenario, system, configuration, and repetition IDs.
- Operational run state and functional system outcome as separate fields.
- Seed, scenario variables, requested/effective values, and code/simulator/adapter/metric-plugin versions.
- Container/package digests, host and relevant resources, commit or dirty-tree state when known.
- Clocks, reference signal, synchronization policy, and success criterion.
- Metrics with unit, definition version, state, missing reason, and coverage.
- Artifacts with path/URI, MIME type, size, checksum, and schema.
- Attempts, retries, interruptions, warnings, and execution events.

## Statistical protocol

### Group summaries

- For success, collision, cancellation, criterion violation, and failure proportions, show `(k/n)`, a 95% interval (Wilson by default for small/moderate samples), and excluded counts/reasons.
- For continuous values, show `n`, median, Q1, Q3, and mean/standard deviation only when useful. Predeclare tail percentiles such as p5/p95.
- Mark time/efficiency conditioned on success as “among successful runs” and show success rate alongside it to reduce survivor bias.
- For safety, show event counts per run and per exposure unit (time/distance) when appropriate. A mean rate does not replace severity counts.
- Report invalid data, missing telemetry, truncated tails, and measurement quality.

### Configuration comparisons

- Compare preregistered primary outcomes first; avoid combining everything into one score.
- When scenarios/seeds are paired, preserve pairing and report paired effect intervals. Do not treat scenario-blocked runs as iid.
- Bootstrap with an explicit seed is an option for difference intervals. Resample the experimental unit (scenario/seed), not telemetry messages.
- For multiple metrics/configurations, declare multiplicity handling or label comparisons exploratory.
- Report absolute difference, relative effect when meaningful, 95% interval, `n` per side, unit, and a minimally relevant difference criterion.
- With small `n`, report insufficient evidence rather than equality; do not let thresholds conceal interval width.
- Keep hard safety conditions as constraints; do not compensate for them with time or efficiency in an average cost.
- Rerun selected candidates on separate validation data. Version metric choices, thresholds, and weights.

### Infrastructure and exclusions

- Preserve infrastructure retries and original attempt reason.
- Do not erase infrastructure failures. Exclude them from functional denominators but report their number/rate separately.
- A system-under-test failure with a healthy simulator belongs in the functional result.
- If critical sensors/telemetry are missing, the criterion is unknown, not passed.
- Mark degraded real-time factor, inconsistent simulation clock, external conditions, and interrupted sessions. Fix inclusion/exclusion policy before the run.
- Cancellation is not failure; represent expected cancellation and stop safety separately.

## Recommended report structure

### 1. Scope

Experiment name/date, objective, system/backend, versions/commit, execution policy, primary criteria, and dataset scope.

### 2. Executive summary

- Planned/completed/excluded runs and reasons.
- Functional success and safety with `(k/n)` and intervals.
- Primary effects and intervals.
- Conditional operational recommendation.
- Key findings, uncertainty, and limitations.

### 3. Configuration and reproducibility

Factor/scenario matrix, ranges, seeds, randomization order, effective parameters, software/hardware versions, and artifact hashes.

### 4. Protocol and validity

Success criterion, reference signal, preregistered metrics, experimental unit, analysis plan, and failure/missing-data policy.

### 5. Results

- Table by configuration/scenario.
- Mission success and safety first.
- Time/efficiency conditioned on success.
- Localization, control/smoothness, stack reliability, and resources.
- Scenario matrix, distributions, and data quality.
- Representative traces with an explained selection method.

### 6. Diagnostics and artifacts

Notable events, observable causes, traces/bags/logs, omitted runs, and local/exportable links.

### 7. Conclusions and limitations

Limit claims to tested conditions; state the next experiment and why.

### 8. Appendices

Manifest, metric catalogue/version, formulas, statistics, schema dictionary, source files, and dependencies.

## Visualizations

Interactive HTML visualizations are useful, but each panel should show `n`, denominator, interval, unit, filters, and legend. Accessible tables and JSON should answer the same question. PDF is a later renderer, not a data format.
