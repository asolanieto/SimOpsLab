# Product plan

## Objective

Build a reusable platform that lets people connect their simulators, systems under test, and evaluation methods. A person or LLM should be able to define a campaign, run/resume/cancel work, inspect results, and create reproducible reports.

MCP is a typed control surface over the product operations. The product is the portable experiment workflow, not the MCP server by itself.

## Success criteria

1. The core installs and runs without ROS or Gazebo.
2. Run data uses versioned contracts with units, provenance, validity state, and a reason for missing data.
3. The same campaign specification runs against at least two independent backends.
4. A campaign resumes without repeating terminal runs or confusing system failure with infrastructure failure.
5. JSON is canonical; Markdown and HTML reports render from that model and agree with it.
6. Analysis states the population, exclusions, group sizes, seeds, method, confidence interval, and limitations.
7. An MCP agent can only perform actions allowed by workspace policy.
8. Portability is demonstrated by a documented integration exercise, not architecture alone.

## Workstreams

| Workstream | Work | Verifiable result |
|---|---|---|
| A. Discovery and positioning | Review existing products, code, and research; map capabilities and gaps | Current landscape matrix and scoped contribution claim |
| B. Domain and contracts | Define campaigns, scenarios, runs, events, metrics, artifacts, and provenance | Versioned schemas and compatibility documentation |
| C. Adapters | Separate execution, simulator, system under test, data acquisition, and scenarios | Reference adapter plus an independent backend |
| D. Evaluation | Version metrics, aggregation, criteria, missing-data handling, and statistics | Reproducible metric definitions and pure analysis modules |
| E. Campaigns and optimization | Declarative planning, seeds, concurrency, limits, retries, idempotence, and search | Resumable runner and interchangeable strategies |
| F. MCP and operations | Bounded tools, campaign state, quotas, and cancellation | Thin MCP server over the application API |
| G. Reports | Canonical analysis contract and Markdown/HTML renderers | Generated report with details, warnings, and appendices |
| H. Validation | Repeat representative workloads, inject failures, measure cost and reproducibility | Validation evidence and release decisions |

## Phases

### 0. Product foundation — implemented

- Create an independent repository.
- Document the architecture, metric model, and evaluation approach.
- Define Python contracts without ROS dependencies.
- Select a permissive license and public contribution policy.

### 1. Executable core — implemented

- Validate declarative manifests.
- Plan scenario × configuration × seed matrices.
- Persist campaign and run state with append-only events.
- Provide an adapter interface and local artifact storage.
- Support campaign inspection and operation without an LLM.
- Cover failure cases with contract and runtime tests.

### 2. Reference adapter — demonstration implemented

- Prepare an environment, start a simulator, execute a goal, collect metrics/artifacts, and shut down cleanly.
- Provide a pinned Nav2/TurtleBot3 Docker demonstration.
- Keep real-hardware execution disabled by default.
- Add a second adapter before claiming demonstrated portability.

### 3. Metrics and reports — core implemented, domain coverage incomplete

- Keep metric calculations independent of ROS where possible.
- Version metric definitions and expose a catalogue.
- Analyze by group, scenario, seed, and configuration.
- Generate JSON, Markdown, and HTML from one result model.
- Test missing telemetry, interrupted runs, and infrastructure failures.
- Add contact, ground-truth, footprint-clearance, and resource instrumentation where the backend supports it.

### 4. MCP — initial local server implemented

- Provide query, validation, execution, status, analysis, report, and cancellation tools.
- Separate reads from writes and bound resource-consuming operations by policy.
- Do not expose arbitrary shell or real-hardware targets by default.
- Record the effective manifest and result for every operation.

### 5. Portability and scale — in progress

- Add an independent backend on another platform or domain.
- Measure worker capacity, concurrency, and quotas.
- Keep local storage as a supported option; remote queues and object storage should remain optional integrations.
- Use LHS for reproducible screening and optional TPE/Optuna for adaptive search with explicit objectives and constraints.
- Document cost, parallelism, recovery, and reproducibility.

### 6. Validation and distribution — in progress

- Compare methods under the same evaluation budget where relevant.
- Measure adaptation effort, integration effort, reproducibility, coverage, and operator burden.
- Publish reproducible examples and limitations.
- Review licenses of dependencies, container images, and data before adding distributed assets.

## Risks that shape the plan

- “Generic” can become a configuration layer for one simulator; the independent backend is therefore a success criterion.
- The current metric inventory is strongest for mobile navigation. The core must allow domain-specific profiles without imposing navigation on every system.
- Ground truth, mission success, and instrumentation differ by use case; declare them through plugins and contracts.
- Concurrent campaigns can degrade simulation fidelity and bias timing. Monitor resources and record excluded runs.
- Metrics conditioned on successful runs can introduce survivor bias. Reports must show success rate alongside those metrics.
- An LLM can propose a defective evaluation. Critical metrics and limits must be reviewable and versioned outside the model.
- Reports must keep denominators and exclusions visible; presentation must not obscure the underlying evidence.
