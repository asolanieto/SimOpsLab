# ADR-003 — Local runner and resumable persistence

- Status: accepted for the first executable product.
- Date: 2026-11-19.

## Decision

- Use `CampaignSpec` and deterministic planner IDs as campaign identity.
- Run installed Python adapters through the `simops.backends` entry point; the core does not invoke a shell or import ROS/Gazebo.
- Start with local SQLite, WAL, and a lock timeout. Store campaigns, runs, attempts, and events; update an attempt and append its event in one transaction.
- Bind each campaign to the expanded-manifest fingerprint plus `backend_id` and `backend_version`. A difference requires a new `campaign_id`.
- Retry only infrastructure failures and interruptions, within the declared limit. Completed runs and functional failures are not repeated on resume.
- Store artifacts in local SHA-256 content-addressed paths; give each run/attempt a separate adapter workspace.
- Persist JSON, Markdown, and HTML reports from the same analysis model.

## Guarantees and limits

Execution is *at least once* around external side effects. A local database cannot prove whether a remote simulator completed a task if the process dies after launch but before the result is stored. Adapters should use `run_id`/`attempt_number` as idempotency keys and clean up orphan processes when possible.

The wall-time budget prevents starting new runs after it expires. It cannot forcibly stop a blocking backend call. Cancellation is cooperative through `ExecutionContext`. SQLite supports a local coordinator; it is not a distributed database for workers across machines.

## Consequences

- The core installs without ROS, Gazebo, or Optuna.
- `max_parallel > 1` requires an adapter to declare `thread_safe` explicitly.
- SQLite and local blobs are straightforward to back up, inspect, and move with a project.
- Remote adapters, distributed leases, object storage, and orphan-process cleanup remain future work.
