# ADR-004 — Local MCP with workspace boundaries

- Status: accepted for the first MCP integration.
- Date: 2026-11-19.

## Decision

- Expose MCP over `stdio` and reuse the same application operations as the CLI.
- The operator starts the server with a local workspace and an explicit backend allowlist. Only `demo` is allowed by default.
- The LLM identifies manifests by filename under `<workspace>/manifests`; it gets no arbitrary file read/write or shell tools.
- Bound campaign size, concurrency, per-run budgets, and total tuning runs.
- Run campaigns and tuning jobs in the background, with explicit status and cooperative cancellation tools.
- Do not offer a real-hardware target by default. The operator must install and explicitly allow any real adapter.

## Consequences and limits

- The initial transport is local; there is no HTTP endpoint or remote authentication.
- MCP limits are an additional guardrail, not a replacement for process isolation, host quotas, or review of installed backend plugins.
- Active-run cancellation works only when the adapter checks the context and cleans up.
- The server exposes typed planning and campaign operations, never a generic shell tool.
