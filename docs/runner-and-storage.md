# Local execution and storage

## Workflow

```text
JSON manifest → planner → adapter validation → SQLite → local worker
              → adapter → result + metrics + artifacts → JSON analysis → Markdown/HTML
```

Minimal core installation: `python -m pip install -e .`. `demo` is a synthetic backend for checking installation and output formats; `nav2-docker` is an example adapter that needs its image built and Docker available.

```sh
simops validate examples/demo-campaign.json
simops plan examples/demo-campaign.json
simops run examples/demo-campaign.json
simops status demo-navigation-smoke
simops resume demo-navigation-smoke
simops report demo-navigation-smoke
```

The default database is `.simops/campaigns.sqlite3`; reports go under `.simops/reports/`. `--store` and `--report-dir` select other paths.

## Journal and resumption

SQLite stores:

- Resolved manifest and SHA-256 fingerprint, backend, and version.
- Each run specification, latest state, and result.
- One record per attempt, with timestamps and terminal result.
- Append-only campaign and run events.

The transaction that completes an attempt updates its state projection and appends the matching event. Repeating a command with the same fingerprint skips terminal runs. If the process finds `running` attempts from an earlier process, it marks them `interrupted` and applies the infrastructure retry limit.

A different fingerprint for an existing `campaign_id` is rejected. Changing scenarios, parameters, or backend version requires a new ID. Run IDs are recomputed at execution time to detect mutation after planning.

Before recovery or execution, the runner locks the SQLite database and `campaign_id` using an OS lock. Concurrent local requests for one campaign are serialized; the lock is released if the process exits. This does not coordinate separate databases or remote hosts.

## Attempts, budget, and cancellation

- System-under-test failure is kept separate from operational run state, for example `completed` with `system_outcome=failure`.
- Adapter exceptions are infrastructure failures; only those are retried automatically.
- A campaign deadline prevents new runs from starting; it does not forcibly interrupt a blocking call.
- SIGINT and MCP tools request cooperative cancellation. Each adapter receives a cancellation event, monotonic deadline, per-attempt workspace, and artifact store.
- A crash around an external call may cause a run to be repeated on resume. SimOps does not promise exactly-once execution; remote adapters should recognize `run_id` and attempt number or clean up orphan processes.
- `max_parallel > 1` is accepted only when the adapter declares `thread_safe=True`; all runs share one adapter instance.

## Artifacts

An adapter can store bytes with `context.artifacts.put(...)`. The store computes SHA-256, writes to a content-addressed path through an atomic rename, and returns an `ArtifactRef`. Reads verify the hash again. Blobs live under `.simops/artifacts/`; each attempt workspace lives under `.simops/work/`.

The runner stores references but does not infer file meaning. Metric plugins/adapters must provide source, unit, version, and state. Artifacts are not stored in SQLite.

## Adapter entry point

The adapter package publishes a Python entry point:

```toml
[project.entry-points."simops.backends"]
my_backend = "my_package.backend:Backend"
```

The no-argument class implements `backend_id`, `backend_version`, `thread_safe`, `validate(run)`, and `execute(run, context)`. The host calls `validate` before registering the campaign. Installed plugin code is trusted; an LLM cannot load an arbitrary module from a manifest.
