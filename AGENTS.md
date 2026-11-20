# Agent instructions

## Before making changes

1. Read `README.md`, `PLAN.md`, and the relevant pages in `docs/`.
2. Separate verified measurements from inferences and design hypotheses.
3. Confirm source data and methods before reusing any reported result.

## Product boundaries

- The core must remain independent of ROS, Gazebo, Nav2, and MCP.
- Simulator- and robot-specific behavior belongs in adapters and capability profiles.
- Do not claim universal portability until the same contract has been exercised with multiple independent backends.
- Missing or invalid data must never be represented as zero or success.
- Preserve provenance, version, unit, validity, and coverage for every measurement.
- Generate reports from structured data; do not hand-edit measured values into a report.

## Changes and coordination

- Keep development logs, private robot data, credentials, local workspaces, and generated simulation artifacts out of the public repository.
- Do not edit other projects as part of work on this repository.
- Do not add secrets, absolute local paths, SSH credentials, or private maps.
- Record architectural decisions in an ADR.
- The project name, schema version, and initial interfaces may evolve as adapters are validated.
