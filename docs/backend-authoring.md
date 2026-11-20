# Add a backend for your robot or simulator

SimOps separates campaign orchestration from simulator access. Each backend provides a versioned identity, preflight validation, isolated execution of one run, and a `RunResult` with typed metrics and artifacts. ROS is not required.

## Minimal interface

Implement `ExperimentBackend` from `simops.backends`:

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

`RunSpec` contains configuration, scenario, repetition, and requested seed. `ExecutionContext` provides a per-attempt workspace, artifact storage, deadline, and cooperative cancellation. If your simulator does not accept the seed, record that in `provenance`; do not claim it was applied.

## Instrumentation that makes tuning useful

1. Separate functional outcome from infrastructure failure.
2. For each metric, emit a stable ID, versioned definition, unit, state (`observed`, `missing`, `invalid`, or `not_applicable`), source, coverage, and reason.
3. Keep independent reference signals when measuring localization or tracking error.
4. Count contacts from simulator contact data when evaluating collision; a short lidar ray is not a substitute. Compute footprint clearance from synchronized geometry.
5. Keep wall and simulation time separate; report clock and signal coverage.
6. Record effective configuration and robot/map/plugin/simulator versions or digests in `provenance`; archive rosbags, MCAP, and traces by content hash.
7. Set `thread_safe=False` if processes share a world, port, GPU, or configuration.

Tuning invalidates candidates with missing required metrics. Constraints use worst-case aggregation across runs unless the manifest declares another estimator. Final selection needs held-out scenarios and seeds.

Register the backend with the Python `simops.backends` entry point; see `pyproject.toml` for the Nav2 example. MCP exposes no shell: the server invokes only allowed backends and manifests from its authorized workspace.

Robot profiles document limits and sensors but do not implement them. Map profile values to effective simulator parameters and validate tuning ranges against the robot envelope.
