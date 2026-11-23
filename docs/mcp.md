# Local MCP server

The MCP server is a thin adapter over the same operations as the CLI. It uses the official Python SDK over `stdio`; it does not open a network port.

Quick setup for Claude Code, Claude Desktop, Cursor and Codex without cloning is in the [README](../README.md#use-it-from-an-ai-agent-mcp).

## Install and start

```sh
python -m pip install -e ".[mcp]"
mkdir -p workspace/manifests
cp examples/demo-campaign.json workspace/manifests/
simops mcp --workspace ./workspace
```

Configure your MCP host to launch that command as a local process. The workspace contains `manifests/`, robot profiles under `robot-profiles/`, and `.simops/`; campaigns, artifacts, Optuna studies, and reports are stored under `.simops/`. Profiles must resolve inside the workspace.

If the operator installed a backend, it must be enabled explicitly:

```sh
simops mcp --workspace ./workspace --allow-backend demo --allow-backend nav2-docker
```

The default allowlist contains only `demo`. Installing a plugin does not allow the LLM to select it.

## Tools

| MCP tool | Function |
|---|---|
| `list_backends` | List installed adapters allowed by the operator. |
| `list_manifests` | List JSON manifest names in the workspace. |
| `validate_campaign` | Validate a manifest without running or saving campaign work. |
| `plan_campaign` | Expand and return the run plan. |
| `start_campaign` | Register the fingerprint and run in the background. |
| `resume_campaign` | Resume pending attempts for a campaign in the same workspace. |
| `get_campaign_status` | Return campaign/run/attempt states and recent activity. |
| `get_campaign_result` | Return canonical metrics grouped by system, scenario, and configuration. |
| `cancel_campaign` | Request cooperative cancellation of an active job. |
| `render_report` | Generate JSON, Markdown, and HTML reports from stored results. |
| `validate_tuning` | Check profile, parameter limits, budget, scenarios, and criteria before tuning. |
| `start_tuning` | Run an allowed LHS or TPE tuning manifest. |
| `get_tuning_result` | Return a saved tuning result or its current state. |

## Workspace boundaries

- Tools accept a simple `.json` filename, not an arbitrary path. Paths with directories and symlinks are rejected; lookup is restricted to `<workspace>/manifests`.
- Defaults allow up to 500 runs per campaign, 8 parallel runs, one hour of wall time, 50 candidates per tuning invocation, and 5,000 total runs per tuning.
- There is no shell, arbitrary Python, external file access, SSH, or real-hardware selection tool.
- The runner uses local SQLite. An MCP process must use the same workspace to inspect and resume campaigns.
- SIGINT and the cancellation tool send cooperative signals. An active adapter must check its `ExecutionContext` and clean up its simulator process.
- Backend plugins are trusted Python code. The MCP allowlist does not sandbox a malicious plugin; operators should install and enable only reviewed adapters.
- Stdio trusts the local host that launches the process. The server is not configured for remote HTTP exposure.

Campaigns and tuning are asynchronous: start tools return an ID and the agent checks status afterward. When a campaign finishes, `get_campaign_result` exposes structured metrics to the agent; `render_report` also generates local JSON, Markdown, and HTML files. Long-running tuning uses the manifest's budget, repetitions, and objectives; finalists should be confirmed on holdout scenarios or seeds.
