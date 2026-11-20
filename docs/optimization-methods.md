# Parameter optimization methods

## Recommended workflow for SimOps

No optimizer wins in every setting. Navigation tuning involves expensive evaluations, noisy metrics, mixed parameter types, and safety criteria. Use a staged workflow:

1. **Reproducible baseline:** use Latin Hypercube Sampling (LHS) to cover parameter dimensions with a fixed budget. Keep random search and small sweeps as comparators; reserve grid search for tiny discrete spaces.
2. **Adaptive search:** use TPE (Tree-structured Parzen Estimator) as the initial method for mixed and discrete spaces. Consider Gaussian-process BO (GPSampler/BoTorch) later for small, mostly continuous spaces with expensive trials.
3. **Separate constraints:** collisions, success rate, minimum clearance, and other critical criteria must not be offset by an average score. Encode constraints as residuals, with values `<= 0` feasible.
4. **Replicate and select:** use paired seeds during screening; expand promising candidates across multiple seeds and scenarios. Keep the Pareto front of feasible candidates.
5. **Independent confirmation:** run finalists on holdout scenarios and seeds fixed before inspecting results, with more repetitions and a predeclared statistical protocol.
6. **Prune cautiously:** use Hyperband/racing only when a cheaper fidelity has rankings that predict full runs. Do not stop a navigation run by default; collision or final success may occur late.

LHS provides a reproducible, visible baseline. TPE proposes candidates from trial history and supports multiple objectives and constraints; constraints guide search but do not guarantee safety. TPE's first `n_startup_trials` are exploratory; a smaller budget never gets to propose from prior results. With `storage_url`, Optuna persists studies in an RDB backend with heartbeat. Parallel workers require shared RDB storage; SQLite is for a single worker. The core has no additional scientific dependencies; TPE is an optional extra.

## Method comparison

| Method | When to use it | Cost and limits | SimOps decision |
|---|---|---|---|
| Grid search | Exhaustive checks for a few discrete parameters | Exponential growth; wastes budget on less relevant dimensions | Consider as a small future strategy |
| Random/LHS | Reproducible screening, mixed types, baseline | Does not reuse prior results; discretization can repeat values | LHS is implemented natively |
| Staged/OAT search | Easy interpretation and small local changes | Can miss interactions; depends on order and aggregated cost | Keep as a comparator, not the only default |
| TPE/Optuna | Expensive evaluations, mixed float/integer/categorical parameters, resumable studies | Startup exploration; pin dependency version; sensitive to objective/noise | Optional implementation with multiple metrics and constraints |
| Gaussian-process BO | Few continuous dimensions and few evaluations | Model cost, heavier installation, fragile with discontinuities/mixed variables | Future BoTorch/GPSampler plugin |
| NSGA-II/III | Multi-objective problems with discontinuities and larger budgets | Usually needs more evaluations than BO for expensive tasks | Future comparator, not default |
| Hyperband / Successive Halving / racing | Runs can stop at stages/fidelities and partial scores are informative | Can discard the eventual best if early ranking is uncorrelated | Future seed/scenario allocation after validating fidelity |
| Morris / Sobol | Find influential parameters and interactions before search | Sobol can require many runs | Optional Morris pre-analysis; Sobol when budget permits |
| Safe BO | Experiments where some regions can harm equipment or people | Guarantees depend on model, noise, initial safe set, and assumptions | Not enabled on real hardware in this implementation |

## Implementation

- `src/simops/optimization.py`: parameter/objective/constraint specifications, observations, Pareto front, and native LHS strategy.
- `src/simops/optuna_tpe.py`: optional TPE plugin with Optuna storage/heartbeat/resumption, multiple objectives, and explicit constraints.
- `src/simops/tuning.py`: connects candidates to persisted runner campaigns, computes objectives/constraints across runs, and writes auditable summaries.
- Invalid infrastructure evaluations do not receive fabricated objective values; they remain failed trials visible in the summary.
- A functional system failure is a completed evaluation with measured values, for example mission failure or collision, and the corresponding constraints. It is not an infrastructure failure.
- The budget counts candidates. Each candidate expands to the same scenario/repetition matrix and stores runs in the shared SQLite journal. Candidates with missing objective metrics or infrastructure failures are invalid, without imputation.

## Integration example

~~~python
from simops import (
    ConstraintSpec,
    Direction,
    EvaluationStatus,
    LatinHypercubeSearch,
    ObjectiveSpec,
    ParameterKind,
    ParameterSpec,
    TuningEvaluation,
    TuningSpec,
)
from simops.optuna_tpe import OptunaTPESearch

spec = TuningSpec(
    parameters=(ParameterSpec("gain", ParameterKind.FLOAT, 0.1, 2.0),),
    objectives=(ObjectiveSpec("mission.time_s", Direction.MINIMIZE),),
    constraints=(ConstraintSpec("safety.collisions", "must equal zero"),),
    storage_url="sqlite:///tuning-study.db",  # use shared PostgreSQL for >1 worker
)

def evaluate(parameters):
    # Run scenario/seed replications and aggregate them here.
    return TuningEvaluation(
        status=EvaluationStatus.COMPLETE,
        objectives={"mission.time_s": 100.0},
        constraints={"safety.collisions": 0.0},
    )

lhs_result = LatinHypercubeSearch().optimize(spec, evaluate, budget=30)
tpe_result = OptunaTPESearch().optimize(spec, evaluate, budget=30)
~~~

A tuning manifest combines the search space with a real campaign. For example, `simops tune examples/nav2-turtlebot3/tuning.json` runs each LHS candidate with the Nav2 Docker adapter. `simops tune examples/demo-tuning.json` exercises the same workflow without downloading a simulator. Simulation cost is candidates × scenarios × systems × repetitions. Results are stored in SQLite and in `tuning.json`/`tuning.md`.

## Responsible use

The study optimizes the aggregates returned by the evaluator; telemetry messages are not treated as independent samples. For noisy results, the evaluator should repeat seeds and return a candidate-level estimate. Final validation reruns the full protocol on holdout data.

This TPE/BO workflow is for simulation. Do not connect it to real hardware without reviewed Safe BO extensions, an initial safe set, independent limits, and operational authorization.

## References

- Bergstra and Bengio, 2012, random search as a competitive baseline: [JMLR](https://www.jmlr.org/papers/v13/bergstra12a.html).
- Berkenkamp, Krause, and Schoellig, 2023, independent constraints for Safe BO in robotics: [open-access paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10485113/).
- Optuna 5.1 documentation for [TPE](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html), [GPSampler](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.GPSampler.html), [multi-objective optimization](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/002_multi_objective.html), and [pruners](https://optuna.readthedocs.io/en/stable/reference/pruners.html).
- BoTorch documentation for constrained multi-objective BO: [qNEHVI/qParEGO](https://botorch.org/docs/next/tutorials/constrained_multi_objective_bo).
- Hyperband: [paper](https://arxiv.org/abs/1603.06560); BOHB: [PMLR](https://proceedings.mlr.press/v80/falkner18a.html).

## Per-run aggregation and safety

Data is preserved by run and scenario. Numeric constraints use `worst_case` by default: maximum for `<=`, minimum for `>=`, before conversion to a feasibility residual. A single collision or mission failure therefore cannot disappear into the mean of many routes. For population rates, explicitly declare `aggregation: "mean"` and justify a threshold that permits individual failures. Missing, invalid, or incomplete coverage invalidates an evaluation and does not feed the optimizer.

Objectives support `mean`, `median`, `min`, `max`, and `p95`. Search summaries retain metrics and per-run values; reports show feasibility and each candidate's constraint margins. Holdout confirmation remains necessary before claiming improvement.
