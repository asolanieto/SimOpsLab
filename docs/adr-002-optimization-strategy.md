# ADR-002 — Parameter tuning strategy

- Status: accepted for the first implementation; comparative evaluation is still needed.
- Date: 2026-11-19.

## Context

Simulation campaigns can be expensive and noisy, often span multiple seeds and scenarios, and include criteria such as collision, arrival, and clearance that must remain independent constraints. A staged search and reproducible screening design are useful baselines. The core needs interchangeable strategies for continuous, discrete, and categorical parameters.

## Alternatives

### A. Grid or staged search as the only strategy

- Pros: easy to explain and reproduce; works for a few parameters and small value lists.
- Cons: scales exponentially; one-at-a-time search can miss interactions.

### B. LHS screening followed by adaptive TPE

- Pros: LHS provides reproducible coverage; TPE reuses trial history, supports mixed parameter types, and handles multiple objectives and constraints through Optuna.
- Cons: requires startup trials, an optional dependency, persistent study storage, and sound treatment of noise. Constraints are not formal safety guarantees.

### C. Gaussian-process BO / BoTorch from the start

- Pros: efficient for expensive, low-dimensional continuous problems; supports constrained multi-objective BO.
- Cons: heavier installation and compute; less suitable as the only method for categorical or larger mixed spaces; higher product complexity.

### D. Hyperband/racing for early stopping

- Pros: can save budget by stopping candidates that look poor at low fidelity.
- Cons: works only if early measurements predict full-run rankings. We have not shown that early success or collision signals predict final navigation outcomes.

## Decision criteria

- Keep the core free of external scientific dependencies.
- Compare against LHS/random search under the same evaluation budget.
- Do not turn safety into a compensable term in a weighted score.
- Distinguish infrastructure errors, functional failures, and invalid measurements.
- Record seeds, aggregation, parameters, search space, and optimizer version.
- Do not target real hardware with TPE in this initial implementation.

## Decision

Implement LHS as the dependency-free baseline and TPE/Optuna as an optional extra. Constraints use residuals where values `<= 0` are feasible. Reports return the Pareto front of feasible candidates; the optimizer does not pick one winner when several objectives are present.

The first integration uses an evaluator callback that runs campaigns and returns aggregated metrics. TPE supports Optuna storage with heartbeat; SQLite is for one worker, while parallel workers require shared RDB storage. Do not enable pruning or real-hardware tuning until evidence and controls justify them.

## Consequences

- No evidence yet shows that TPE beats reference strategies; compare them under the same budget and protocol.
- A runner is needed to connect evaluation to campaigns and preserve each individual run.
- GP BO/BoTorch, Morris/Sobol sensitivity, and racing are deferred until the first integration is evaluated.
- Release checks cover noise, constraints, Pareto results, persistence, and interruptions.
