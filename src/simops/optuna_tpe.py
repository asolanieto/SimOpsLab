"""Optional constrained multi-objective TPE optimizer powered by Optuna."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import JSONScalar
from .optimization import (
    CandidateResult,
    EvaluationStatus,
    OptimizationResult,
    ParameterKind,
    ParameterSpec,
    TuningEvaluator,
    TuningSpec,
    pareto_front,
    validate_evaluation,
)


class TrialEvaluationError(RuntimeError):
    """A trial could not produce a valid system observation."""


def _signature(spec: TuningSpec) -> str:
    payload = {
        "parameters": [
            {
                "name": p.name,
                "kind": p.kind.value,
                "lower": p.lower,
                "upper": p.upper,
                "choices": list(p.choices),
                "step": p.step,
                "log": p.log,
            }
            for p in spec.parameters
        ],
        "objectives": [
            {"metric_id": o.metric_id, "direction": o.direction.value}
            for o in spec.objectives
        ],
        "constraints": [
            {"constraint_id": c.constraint_id, "description": c.description}
            for c in spec.constraints
        ],
        "sampler": "optuna-tpe-v1",
        "seed": spec.seed,
        "startup_trials": spec.n_startup_trials,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _suggest(trial: Any, parameter: ParameterSpec) -> JSONScalar:
    if parameter.kind is ParameterKind.CATEGORICAL:
        return trial.suggest_categorical(parameter.name, list(parameter.choices))
    if parameter.kind is ParameterKind.INTEGER:
        return trial.suggest_int(
            parameter.name,
            int(parameter.lower),
            int(parameter.upper),
            step=int(parameter.step) if parameter.step is not None else 1,
            log=parameter.log,
        )
    return trial.suggest_float(
        parameter.name,
        float(parameter.lower),
        float(parameter.upper),
        step=float(parameter.step) if parameter.step is not None else None,
        log=parameter.log,
    )


class OptunaTPESearch:
    """TPE for expensive mixed spaces, multi-objective metrics and explicit constraints.

    Constraint residuals use the convention value <= 0 means feasible. This guides
    TPE candidate selection; it is not a safety guarantee for simulation or hardware.
    """

    strategy_id = "optuna-tpe-v1"

    def optimize(
        self,
        spec: TuningSpec,
        evaluate: TuningEvaluator,
        budget: int,
    ) -> OptimizationResult:
        spec.validate()
        if budget < 1:
            raise ValueError("budget must be at least 1")
        try:
            import optuna
        except ImportError as exc:
            raise RuntimeError(
                "Optuna is optional; install the package with the optimize extra"
            ) from exc

        directions = [objective.direction.value for objective in spec.objectives]
        sampler = optuna.samplers.TPESampler(
            seed=spec.seed,
            n_startup_trials=spec.n_startup_trials,
            multivariate=len(directions) == 1,
            constant_liar=spec.workers > 1,
        )
        options: dict[str, Any] = {
            "study_name": spec.study_name,
            "sampler": sampler,
            "load_if_exists": spec.storage_url is not None,
        }
        storage = None
        if spec.storage_url is not None:
            if spec.workers > 1 and spec.storage_url.startswith("sqlite:"):
                raise ValueError("parallel TPE needs a shared RDB backend; SQLite is single-worker only")
            engine_kwargs: dict[str, Any] = {}
            if spec.storage_url.startswith("sqlite:"):
                from sqlalchemy.pool import NullPool

                engine_kwargs["poolclass"] = NullPool
            storage = optuna.storages.RDBStorage(
                url=spec.storage_url,
                engine_kwargs=engine_kwargs or None,
                heartbeat_interval=60,
                grace_period=180,
            )
            options["storage"] = storage
        if len(directions) == 1:
            options["direction"] = directions[0]
        else:
            options["directions"] = directions
        study = optuna.create_study(**options)

        signature = _signature(spec)
        old_signature = study.user_attrs.get("simops_signature")
        if old_signature is not None and old_signature != signature:
            raise ValueError(
                "stored study signature does not match this tuning space/objective definition"
            )
        if old_signature is None:
            study.set_user_attr("simops_signature", signature)

        def objective(trial: Any) -> float | tuple[float, ...]:
            parameters = {
                parameter.name: _suggest(trial, parameter)
                for parameter in spec.parameters
            }
            trial.set_user_attr("simops_parameters", parameters)
            try:
                evaluation = evaluate(parameters)
            except Exception as exc:
                reason = f"evaluator raised {type(exc).__name__}: {exc}"
                trial.set_user_attr(
                    "simops_evaluation_status",
                    EvaluationStatus.INFRASTRUCTURE_FAILURE.value,
                )
                trial.set_user_attr("simops_reason", reason)
                raise TrialEvaluationError(reason) from exc
            trial.set_user_attr("simops_evaluation_status", evaluation.status.value)
            if evaluation.reason:
                trial.set_user_attr("simops_reason", evaluation.reason)
            if evaluation.status is not EvaluationStatus.COMPLETE:
                raise TrialEvaluationError(evaluation.reason or evaluation.status.value)
            try:
                validate_evaluation(spec, evaluation)
            except ValueError as exc:
                trial.set_user_attr("simops_evaluation_status", EvaluationStatus.INVALID.value)
                trial.set_user_attr("simops_reason", str(exc))
                raise TrialEvaluationError(str(exc)) from exc

            for constraint in spec.constraints:
                trial.set_constraint(
                    constraint.constraint_id,
                    float(evaluation.constraints[constraint.constraint_id]),
                )
            trial.set_user_attr("simops_observation_metadata", dict(evaluation.metadata))
            values = tuple(
                float(evaluation.objectives[objective.metric_id])
                for objective in spec.objectives
            )
            return values[0] if len(values) == 1 else values

        try:
            study.optimize(
                objective,
                n_trials=budget,
                n_jobs=spec.workers,
                catch=(TrialEvaluationError,),
            )
            frozen_trials = study.trials
        finally:
            if storage is not None:
                storage.remove_session()

        candidates: list[CandidateResult] = []
        for frozen in frozen_trials:
            parameters = dict(frozen.params)
            constraints = dict(getattr(frozen, "constraints", {}) or {})
            objectives = {}
            if frozen.values is not None:
                objectives = {
                    objective.metric_id: float(value)
                    for objective, value in zip(spec.objectives, frozen.values, strict=True)
                }
            completed = frozen.state is optuna.trial.TrialState.COMPLETE
            all_constraints_present = all(
                item.constraint_id in constraints for item in spec.constraints
            )
            is_feasible = (
                all_constraints_present
                and all(
                    constraints[item.constraint_id] <= 0
                    for item in spec.constraints
                )
                if completed
                else None
            )
            candidates.append(
                CandidateResult(
                    candidate_id=f"optuna-{frozen.number:06d}",
                    parameters=parameters,
                    state=frozen.user_attrs.get(
                        "simops_evaluation_status",
                        frozen.state.name.lower(),
                    ),
                    objectives=objectives,
                    constraints=constraints,
                    feasible=is_feasible,
                    reason=frozen.user_attrs.get("simops_reason"),
                    metadata=frozen.user_attrs.get("simops_observation_metadata", {}),
                )
            )

        return OptimizationResult(
            strategy_id=self.strategy_id,
            candidates=tuple(candidates),
            pareto_front=pareto_front(candidates, spec),
        )
