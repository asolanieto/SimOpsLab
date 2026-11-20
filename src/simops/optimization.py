"""Domain-neutral parameter tuning primitives and a reproducible LHS baseline."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from .contracts import JSONScalar, JSONValue


class ParameterKind(StrEnum):
    FLOAT = "float"
    INTEGER = "integer"
    CATEGORICAL = "categorical"


class Direction(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class EvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    kind: ParameterKind
    lower: float | int | None = None
    upper: float | int | None = None
    choices: tuple[JSONScalar, ...] = ()
    step: float | int | None = None
    log: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("parameter name must not be empty")
        if self.kind is ParameterKind.CATEGORICAL:
            if len(self.choices) < 2:
                raise ValueError(f"{self.name}: categorical parameters need at least two choices")
            if any(value is None for value in self.choices):
                raise ValueError(f"{self.name}: null is not a supported categorical value")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError(f"{self.name}: categorical choices must be unique")
            if any(isinstance(value, float) and not math.isfinite(value) for value in self.choices):
                raise ValueError(f"{self.name}: categorical numeric choices must be finite")
            if self.lower is not None or self.upper is not None or self.step is not None or self.log:
                raise ValueError(f"{self.name}: categorical parameters cannot set bounds, step, or log")
            return
        if self.choices:
            raise ValueError(f"{self.name}: numeric parameters cannot set choices")
        if self.lower is None or self.upper is None:
            raise ValueError(f"{self.name}: numeric parameters need lower and upper bounds")
        if not isinstance(self.lower, (int, float)) or isinstance(self.lower, bool):
            raise ValueError(f"{self.name}: lower bound must be numeric")
        if not isinstance(self.upper, (int, float)) or isinstance(self.upper, bool):
            raise ValueError(f"{self.name}: upper bound must be numeric")
        if not math.isfinite(float(self.lower)) or not math.isfinite(float(self.upper)):
            raise ValueError(f"{self.name}: bounds must be finite")
        if self.lower >= self.upper:
            raise ValueError(f"{self.name}: numeric parameters need lower < upper")
        if self.log and self.lower <= 0:
            raise ValueError(f"{self.name}: log parameters must have a positive lower bound")
        if self.step is not None and (
            not isinstance(self.step, (int, float))
            or isinstance(self.step, bool)
            or not math.isfinite(float(self.step))
            or self.step <= 0
        ):
            raise ValueError(f"{self.name}: step must be finite and positive")
        if self.step is not None:
            steps = (float(self.upper) - float(self.lower)) / float(self.step)
            if not math.isclose(steps, round(steps), rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"{self.name}: upper bound must lie on the configured step grid")
        if self.kind is ParameterKind.INTEGER:
            if not isinstance(self.lower, int) or isinstance(self.lower, bool):
                raise ValueError(f"{self.name}: integer lower bound must be an integer")
            if not isinstance(self.upper, int) or isinstance(self.upper, bool):
                raise ValueError(f"{self.name}: integer upper bound must be an integer")
            if self.step is not None and not isinstance(self.step, int):
                raise ValueError(f"{self.name}: integer step must be an integer")
        if self.log and self.step is not None:
            raise ValueError(f"{self.name}: logarithmic and stepped sampling cannot be combined")


@dataclass(frozen=True, slots=True)
class ObjectiveSpec:
    metric_id: str
    direction: Direction

    def validate(self) -> None:
        if not self.metric_id.strip():
            raise ValueError("objective metric_id must not be empty")
        if not isinstance(self.direction, Direction):
            raise ValueError(f"{self.metric_id}: direction must be a Direction")


@dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """Constraint value uses the convention margin <= 0 means feasible."""

    constraint_id: str
    description: str

    def validate(self) -> None:
        if not self.constraint_id.strip():
            raise ValueError("constraint_id must not be empty")
        if not self.description.strip():
            raise ValueError(f"{self.constraint_id}: constraint description must not be empty")


@dataclass(frozen=True, slots=True)
class TuningSpec:
    parameters: tuple[ParameterSpec, ...]
    objectives: tuple[ObjectiveSpec, ...]
    constraints: tuple[ConstraintSpec, ...] = ()
    seed: int = 0
    workers: int = 1
    n_startup_trials: int = 10
    study_name: str = "simops-tuning"
    storage_url: str | None = None

    def validate(self) -> None:
        if not self.parameters:
            raise ValueError("at least one tunable parameter is required")
        if not self.objectives:
            raise ValueError("at least one objective is required")
        for parameter in self.parameters:
            parameter.validate()
        for objective in self.objectives:
            objective.validate()
        for constraint in self.constraints:
            constraint.validate()
        _require_unique((p.name for p in self.parameters), "parameter names")
        _require_unique((o.metric_id for o in self.objectives), "objective metric IDs")
        _require_unique((c.constraint_id for c in self.constraints), "constraint IDs")
        if self.workers < 1:
            raise ValueError("workers must be at least 1")
        if self.n_startup_trials < 1:
            raise ValueError("n_startup_trials must be at least 1")
        if not self.study_name.strip():
            raise ValueError("study_name must not be empty")


@dataclass(frozen=True, slots=True)
class TuningEvaluation:
    status: EvaluationStatus
    objectives: Mapping[str, float] = field(default_factory=dict)
    constraints: Mapping[str, float] = field(default_factory=dict)
    reason: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateResult:
    candidate_id: str
    parameters: Mapping[str, JSONScalar]
    state: str
    objectives: Mapping[str, float] = field(default_factory=dict)
    constraints: Mapping[str, float] = field(default_factory=dict)
    feasible: bool | None = None
    reason: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    strategy_id: str
    candidates: tuple[CandidateResult, ...]
    pareto_front: tuple[CandidateResult, ...]


TuningEvaluator: TypeAlias = Callable[[Mapping[str, JSONScalar]], TuningEvaluation]


def _require_unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")


def validate_evaluation(spec: TuningSpec, evaluation: TuningEvaluation) -> None:
    """Validate an observation before it can influence the optimizer."""
    if evaluation.status is not EvaluationStatus.COMPLETE:
        if not evaluation.reason:
            raise ValueError("incomplete evaluations must include a reason")
        return
    expected_objectives = {objective.metric_id for objective in spec.objectives}
    expected_constraints = {constraint.constraint_id for constraint in spec.constraints}
    if set(evaluation.objectives) != expected_objectives:
        raise ValueError("completed evaluation must return every configured objective exactly once")
    if set(evaluation.constraints) != expected_constraints:
        raise ValueError("completed evaluation must return every configured constraint exactly once")
    values = tuple(evaluation.objectives.values()) + tuple(evaluation.constraints.values())
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("objective and constraint values must be finite numbers")


def feasible(candidate: CandidateResult, spec: TuningSpec) -> bool:
    if candidate.state != EvaluationStatus.COMPLETE.value:
        return False
    return all(
        key in candidate.constraints and candidate.constraints[key] <= 0
        for key in (constraint.constraint_id for constraint in spec.constraints)
    )


def pareto_front(
    candidates: Sequence[CandidateResult],
    spec: TuningSpec,
) -> tuple[CandidateResult, ...]:
    """Return non-dominated feasible candidates, respecting objective directions."""
    valid = [
        candidate
        for candidate in candidates
        if feasible(candidate, spec)
        and all(objective.metric_id in candidate.objectives for objective in spec.objectives)
    ]

    def dominates(left: CandidateResult, right: CandidateResult) -> bool:
        no_worse = True
        strictly_better = False
        for objective in spec.objectives:
            a = left.objectives[objective.metric_id]
            b = right.objectives[objective.metric_id]
            if objective.direction is Direction.MINIMIZE:
                no_worse &= a <= b
                strictly_better |= a < b
            else:
                no_worse &= a >= b
                strictly_better |= a > b
        return no_worse and strictly_better

    return tuple(
        candidate
        for candidate in valid
        if not any(
            other.candidate_id != candidate.candidate_id and dominates(other, candidate)
            for other in valid
        )
    )


def _from_unit_interval(parameter: ParameterSpec, value: float) -> JSONScalar:
    if parameter.kind is ParameterKind.CATEGORICAL:
        index = min(int(value * len(parameter.choices)), len(parameter.choices) - 1)
        return parameter.choices[index]
    lower = float(parameter.lower)
    upper = float(parameter.upper)
    if parameter.kind is ParameterKind.INTEGER and not parameter.log and parameter.step is None:
        bins = int(upper - lower) + 1
        index = min(int(value * bins), bins - 1)
        return int(lower) + index
    if parameter.log:
        sampled = math.exp(math.log(lower) + value * (math.log(upper) - math.log(lower)))
    elif parameter.step is not None:
        step = float(parameter.step)
        bins = max(1, math.floor((upper - lower) / step) + 1)
        index = min(int(value * bins), bins - 1)
        sampled = lower + index * step
    else:
        sampled = lower + value * (upper - lower)
    if parameter.kind is ParameterKind.INTEGER:
        return int(sampled)
    return float(sampled)


def latin_hypercube_sample(
    parameters: Sequence[ParameterSpec],
    count: int,
    seed: int,
) -> tuple[Mapping[str, JSONScalar], ...]:
    """Generate a seeded, marginally stratified design for mixed parameter spaces."""
    if count < 1:
        raise ValueError("count must be at least 1")
    if not parameters:
        raise ValueError("at least one parameter is required")
    for parameter in parameters:
        parameter.validate()
    _require_unique((parameter.name for parameter in parameters), "parameter names")

    rng = random.Random(seed)
    samples: list[dict[str, JSONScalar]] = [dict() for _ in range(count)]
    for parameter in parameters:
        strata = [(index + rng.random()) / count for index in range(count)]
        rng.shuffle(strata)
        for row, coordinate in zip(samples, strata, strict=True):
            row[parameter.name] = _from_unit_interval(parameter, coordinate)
    return tuple(samples)


class LatinHypercubeSearch:
    """Reproducible, dependency-free screening strategy and comparison baseline."""

    strategy_id = "latin-hypercube-v1"

    def optimize(
        self,
        spec: TuningSpec,
        evaluate: TuningEvaluator,
        budget: int,
    ) -> OptimizationResult:
        spec.validate()
        if budget < 1:
            raise ValueError("budget must be at least 1")
        candidates: list[CandidateResult] = []
        for index, parameters in enumerate(
            latin_hypercube_sample(spec.parameters, budget, spec.seed),
            start=1,
        ):
            try:
                evaluation = evaluate(parameters)
            except Exception as exc:
                candidates.append(
                    CandidateResult(
                        candidate_id=f"lhs-{index:04d}",
                        parameters=parameters,
                        state=EvaluationStatus.INFRASTRUCTURE_FAILURE.value,
                        feasible=False,
                        reason=f"evaluator raised {type(exc).__name__}: {exc}",
                    )
                )
                continue
            try:
                validate_evaluation(spec, evaluation)
                reason = evaluation.reason
                state = evaluation.status.value
            except ValueError as exc:
                reason = str(exc)
                state = EvaluationStatus.INVALID.value
            complete = state == EvaluationStatus.COMPLETE.value
            constraints = dict(evaluation.constraints) if complete else {}
            candidates.append(
                CandidateResult(
                    candidate_id=f"lhs-{index:04d}",
                    parameters=parameters,
                    state=state,
                    objectives=dict(evaluation.objectives) if complete else {},
                    constraints=constraints,
                    feasible=(
                        all(value <= 0 for value in constraints.values())
                        if complete
                        else False
                    ),
                    reason=reason,
                    metadata=dict(evaluation.metadata) if state == EvaluationStatus.COMPLETE.value else {},
                )
            )
        return OptimizationResult(
            strategy_id=self.strategy_id,
            candidates=tuple(candidates),
            pareto_front=pareto_front(candidates, spec),
        )
