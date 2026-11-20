# ADR-001 — Keep the campaign core independent of MCP

- Status: accepted as an initial design decision; revisit as the application API evolves.
- Date: 2026-11-19.

## Context

MCP servers can expose control and observation for Gazebo/ROS. This project also covers resumable campaigns, evaluation, optimization, and reporting. Domain logic should not depend on an agent interface.

## Decision

The core and application API must work without an LLM or the MCP SDK. The MCP server is an adapter that maps typed tools to existing application operations.

## Consequences

- CLI and MCP share validation, persistence, policy, and application logic.
- Campaigns and report renderers can be tested without an LLM session.
- Other clients can integrate with the application API later.
- MCP transport alone is not treated as a substantive research contribution.
