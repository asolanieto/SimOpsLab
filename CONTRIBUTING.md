# Contributing

Thanks for helping improve SimOps Lab. Before changing code:

1. Open an issue describing the behavior, backend, simulator version, and reproduction.
2. Keep simulator-specific code in an adapter; keep the core domain-neutral.
3. Include source, units, validity states, coverage, provenance, and known limitations for every new metric.
4. Add or update tests for changed behavior. Never convert missing safety data to zero.
5. Run the documented unit suite and include the exact command and result in the pull request.
6. Do not commit simulation artifacts, private robot data, credentials, or local `.simops` workspaces.

Contributions are licensed under Apache-2.0. By submitting a contribution, you agree that it may be distributed under that license.
