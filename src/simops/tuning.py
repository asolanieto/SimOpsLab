"""Connect parameter search strategies to real stored campaign executions."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median
from typing import Any

from .backends import ExperimentBackend
from .contracts import (
    MetricState,
    RunStatus,
)
from .optimization import (
    ConstraintSpec,
    Direction,
    EvaluationStatus,
    LatinHypercubeSearch,
    ObjectiveSpec,
    OptimizationResult,
    ParameterKind,
    ParameterSpec,
    TuningEvaluation,
    TuningEvaluator,
    TuningSpec,
)
from .paths import path_component
from .planner import CampaignMatrix, ConfigurationDefinition, ScenarioDefinition, plan_campaign
from .robot_profile import RobotProfile, load_robot_profile
from .runner import CampaignRunner
from .serialization import canonical_json, pretty_json, to_json_value


@dataclass(frozen=True, slots=True)
class TuningManifest:
    tuning_id: str
    title: str
    backend_id: str
    robot_profile: RobotProfile | None
    strategy_id: str
    budget: int
    base_configuration: Mapping[str, Any]
    parameters: tuple[ParameterSpec, ...]
    objectives: tuple[ObjectiveSpec, ...]
    objective_aggregations: Mapping[str, str]
    constraints: tuple[dict[str, Any], ...]
    campaign_template: dict[str, Any]
    tuning_spec: TuningSpec


def load_tuning_manifest(
    path: str | Path, *, profile_root: str | Path | None = None
) -> TuningManifest:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read tuning manifest {source}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != "0.1.0":
        raise ValueError("tuning manifest must be an object with schema_version '0.1.0'")
    if set(raw) - {"schema_version", "backend", "robot_profile", "tuning"}:
        raise ValueError(f"unknown tuning manifest field(s): {', '.join(sorted(set(raw) - {'schema_version', 'backend', 'robot_profile', 'tuning'}))}")
    backend_id = _nonempty_string(raw.get("backend"), "backend")
    profile_path = raw.get("robot_profile")
    if profile_path is not None and not isinstance(profile_path, str):
        raise ValueError("robot_profile must be a path string")
    robot_profile = None
    if profile_path:
        resolved_profile = (source.parent / profile_path).resolve()
        if profile_root is not None:
            allowed_root = Path(profile_root).expanduser().resolve()
            if not resolved_profile.is_relative_to(allowed_root):
                raise ValueError("robot_profile must resolve inside the configured workspace")
        robot_profile = load_robot_profile(resolved_profile)
    config = raw.get("tuning")
    if not isinstance(config, dict):
        raise ValueError("tuning must be a JSON object")
    allowed = {
        "tuning_id", "title", "strategy", "budget", "seed", "workers", "n_startup_trials",
        "study_name", "storage_url", "base_configuration", "parameters", "objectives",
        "constraints", "campaign",
    }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"tuning contains unknown field(s): {', '.join(sorted(unknown))}")
    tuning_id = _nonempty_string(config.get("tuning_id"), "tuning.tuning_id")
    title = _nonempty_string(config.get("title"), "tuning.title")
    strategy_id = _nonempty_string(config.get("strategy", "lhs"), "tuning.strategy")
    if strategy_id not in {"lhs", "tpe"}:
        raise ValueError("tuning.strategy must be 'lhs' or 'tpe'")
    budget = config.get("budget")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError("tuning.budget must be a positive integer")
    base_configuration = _object(config.get("base_configuration", {}), "base_configuration")
    canonical_json(base_configuration)
    parameters = tuple(_parameter(item) for item in _object_array(config.get("parameters"), "parameters"))
    objective_data = _object_array(config.get("objectives"), "objectives")
    objectives = tuple(_objective(item) for item in objective_data)
    objective_aggregations = {item.metric_id: data.get("aggregation", "mean") for item, data in zip(objectives, objective_data)}
    if any(mode not in {"mean", "median", "min", "max", "p95"} for mode in objective_aggregations.values()):
        raise ValueError("objective.aggregation must be mean, median, min, max, or p95")
    constraints = tuple(_constraint(item) for item in _object_array(config.get("constraints", []), "constraints"))
    campaign_template = _object(config.get("campaign"), "tuning.campaign")
    template_allowed = {
        "systems", "scenarios", "repetitions", "seeds", "max_parallel",
        "max_infrastructure_retries", "wall_time_budget_s", "metadata",
    }
    template_unknown = set(campaign_template) - template_allowed
    if template_unknown:
        raise ValueError(f"tuning.campaign contains unknown field(s): {', '.join(sorted(template_unknown))}")
    _validate_campaign_template(campaign_template)
    if robot_profile is not None:
        _validate_profile_parameter_bounds(robot_profile, parameters, base_configuration)
    if not parameters:
        raise ValueError("tuning.parameters must not be empty")
    if not objectives:
        raise ValueError("tuning.objectives must not be empty")
    if len({item.name for item in parameters}) != len(parameters):
        raise ValueError("tuning parameter names must be unique")
    if len({item.metric_id for item in objectives}) != len(objectives):
        raise ValueError("tuning objective metric IDs must be unique")
    if len({item["constraint_id"] for item in constraints}) != len(constraints):
        raise ValueError("tuning constraint IDs must be unique")
    for parameter in parameters:
        parameter.validate()
    for objective in objectives:
        objective.validate()
    search_spec = TuningSpec(
        parameters=parameters,
        objectives=objectives,
        constraints=tuple(
            ConstraintSpec(item["constraint_id"], item["description"]) for item in constraints
        ),
        seed=_integer(config.get("seed", 0), "tuning.seed"),
        workers=_positive_integer(config.get("workers", 1), "tuning.workers"),
        n_startup_trials=_positive_integer(
            config.get("n_startup_trials", 10), "tuning.n_startup_trials"
        ),
        study_name=_nonempty_string(config.get("study_name", tuning_id), "tuning.study_name"),
        storage_url=config.get("storage_url"),
    )
    search_spec.validate()
    if search_spec.storage_url is not None and not isinstance(search_spec.storage_url, str):
        raise ValueError("tuning.storage_url must be a string")
    return TuningManifest(
        tuning_id=tuning_id,
        title=title,
        backend_id=backend_id,
        robot_profile=robot_profile,
        strategy_id=strategy_id,
        budget=budget,
        base_configuration=base_configuration,
        parameters=parameters,
        objectives=objectives,
        objective_aggregations=objective_aggregations,
        constraints=constraints,
        campaign_template=campaign_template,
        tuning_spec=search_spec,
    )


def run_tuning(
    manifest: TuningManifest,
    backend: ExperimentBackend,
    runner: CampaignRunner,
    *,
    result_directory: str | Path,
    default_storage_path: str | Path | None = None,
) -> OptimizationResult:
    if backend.backend_id != manifest.backend_id:
        raise ValueError(
            f"manifest requests backend {manifest.backend_id!r} but loaded {backend.backend_id!r}"
        )
    search_spec = manifest.tuning_spec
    experiment_fingerprint = _experiment_fingerprint(manifest, backend)
    if manifest.strategy_id == "tpe":
        storage_url = search_spec.storage_url
        if storage_url is None:
            if search_spec.workers > 1:
                raise ValueError("TPE with multiple workers requires an explicit shared RDB storage_url")
            if default_storage_path is None:
                raise ValueError("persistent storage path is required to run TPE")
            database_path = Path(default_storage_path).expanduser().resolve()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            storage_url = f"sqlite:///{database_path.as_posix()}"
        elif search_spec.workers > 1 and storage_url.startswith("sqlite:"):
            raise ValueError("parallel TPE needs a shared PostgreSQL/MySQL RDB storage_url")
        search_spec = TuningSpec(
            parameters=search_spec.parameters,
            objectives=search_spec.objectives,
            constraints=search_spec.constraints,
            seed=search_spec.seed,
            workers=search_spec.workers,
            n_startup_trials=search_spec.n_startup_trials,
            study_name=f"{search_spec.study_name}-{experiment_fingerprint}",
            storage_url=storage_url,
        )

    evaluator = _campaign_evaluator(manifest, backend, runner)
    if manifest.strategy_id == "lhs":
        strategy = LatinHypercubeSearch()
    else:
        from .optuna_tpe import OptunaTPESearch

        strategy = OptunaTPESearch()
    result = strategy.optimize(search_spec, evaluator, manifest.budget)
    output = Path(result_directory) / path_component(manifest.tuning_id)
    output.mkdir(parents=True, exist_ok=True)
    result_data = {
        "schema_version": "0.1.0",
        "tuning_id": manifest.tuning_id,
        "title": manifest.title,
        "strategy_id": result.strategy_id,
        "budget_added": manifest.budget,
        "backend_id": backend.backend_id,
        "backend_version": backend.backend_version,
        "candidate_count": len(result.candidates),
        "pareto_front": [to_json_value(item) for item in result.pareto_front],
        "candidates": [to_json_value(item) for item in result.candidates],
    }
    (output / "tuning.json").write_text(pretty_json(result_data), encoding="utf-8")
    (output / "tuning.md").write_text(_render_tuning_markdown(result_data), encoding="utf-8")
    return result


def _campaign_evaluator(
    manifest: TuningManifest,
    backend: ExperimentBackend,
    runner: CampaignRunner,
) -> TuningEvaluator:
    tuning_fingerprint = _experiment_fingerprint(manifest, backend)

    def evaluate(parameters: Mapping[str, Any]) -> TuningEvaluation:
        effective = dict(manifest.base_configuration)
        effective.update(parameters)
        parameter_hash = hashlib.sha256(canonical_json(effective).encode("utf-8")).hexdigest()[:12]
        candidate_id = f"candidate-{parameter_hash}"
        campaign_id = f"{manifest.tuning_id}-{tuning_fingerprint}-{parameter_hash}"
        template = manifest.campaign_template
        scenarios = tuple(
            ScenarioDefinition(item["scenario_id"], item.get("parameters", {}))
            for item in template["scenarios"]
        )
        campaign = plan_campaign(
            CampaignMatrix(
                campaign_id=campaign_id,
                title=f"{manifest.title}: {candidate_id}",
                systems=tuple(template["systems"]),
                scenarios=scenarios,
                configurations=(ConfigurationDefinition(candidate_id, effective),),
                repetitions=template["repetitions"],
                seeds=tuple(template.get("seeds", [])),
                max_parallel=template.get("max_parallel", 1),
                max_infrastructure_retries=template.get("max_infrastructure_retries", 0),
                wall_time_budget_s=template.get("wall_time_budget_s"),
                metadata={
                    **template.get("metadata", {}),
                    "tuning_id": manifest.tuning_id,
                    "candidate_id": candidate_id,
                    "parameters": effective,
                    "robot_profile": ({
                        "profile_id": manifest.robot_profile.profile_id,
                        "footprint_radius_m": manifest.robot_profile.footprint_radius_m,
                        "max_linear_speed_mps": manifest.robot_profile.max_linear_speed_mps,
                        "max_angular_speed_radps": manifest.robot_profile.max_angular_speed_radps,
                    } if manifest.robot_profile is not None else None),
                },
            )
        )
        results = runner.run_campaign(campaign, backend)
        states = runner.store.run_states(campaign_id)
        infra = sum(
            state["status"] in {RunStatus.FAILED_INFRASTRUCTURE.value, RunStatus.INTERRUPTED.value}
            for state in states.values()
        )
        if infra:
            return TuningEvaluation(
                status=EvaluationStatus.INFRASTRUCTURE_FAILURE,
                reason=f"{infra} planned run(s) ended in an infrastructure failure",
                metadata={"campaign_id": campaign_id, "run_count": len(results)},
            )

        run_metrics: dict[str, list[float]] = {}
        aggregate_metrics: dict[str, float] = {}
        requested_metrics = {item.metric_id for item in manifest.objectives}
        requested_metrics.update(item["metric_id"] for item in manifest.constraints)
        for metric_id in requested_metrics:
            values = []
            for result in results:
                metric = next(
                    (
                        item for item in result.metrics
                        if item.metric_id == metric_id and item.state is MetricState.OBSERVED
                    ),
                    None,
                )
                if metric is None or (
                    not isinstance(metric.value, (bool, int, float))
                    or isinstance(metric.value, float) and not math.isfinite(metric.value)
                ):
                    return TuningEvaluation(
                        status=EvaluationStatus.INVALID,
                        reason=f"metric {metric_id!r} is missing or non-numeric for run {result.run_id}",
                        metadata={"campaign_id": campaign_id},
                    )
                numeric = float(metric.value)
                if not math.isfinite(numeric):
                    return TuningEvaluation(
                        status=EvaluationStatus.INVALID,
                        reason=f"metric {metric_id!r} is non-finite for run {result.run_id}",
                        metadata={"campaign_id": campaign_id},
                    )
                values.append(numeric)
            if len(values) != len(campaign.runs):
                return TuningEvaluation(
                    status=EvaluationStatus.INVALID,
                    reason=f"metric {metric_id!r} does not cover every planned run",
                    metadata={"campaign_id": campaign_id},
                )
            run_metrics[metric_id] = values

        for objective in manifest.objectives:
            metric_id = objective.metric_id
            aggregate_metrics[metric_id] = _aggregate(run_metrics[metric_id], manifest.objective_aggregations[metric_id])

        objectives = {objective.metric_id: aggregate_metrics[objective.metric_id] for objective in manifest.objectives}
        constraints = {}
        for constraint in manifest.constraints:
            values = run_metrics[constraint["metric_id"]]
            value = _aggregate_constraint(values, constraint["aggregation"], constraint["operator"])
            aggregate_metrics[constraint["metric_id"]] = value
            threshold = constraint["threshold"]
            if constraint["operator"] == "<=":
                constraints[constraint["constraint_id"]] = value - threshold
            else:
                constraints[constraint["constraint_id"]] = threshold - value
        return TuningEvaluation(
            status=EvaluationStatus.COMPLETE,
            objectives=objectives,
            constraints=constraints,
            metadata={
                "campaign_id": campaign_id,
                "run_count": len(results),
                "aggregated_metrics": aggregate_metrics,
                "run_metrics": {key: list(values) for key, values in run_metrics.items()},
                "constraint_aggregations": {item["constraint_id"]: item["aggregation"] for item in manifest.constraints},
            },
        )

    return evaluate



def _validate_profile_parameter_bounds(
    profile: RobotProfile, parameters: tuple[ParameterSpec, ...], base: Mapping[str, Any]
) -> None:
    limits = {
        "controller.vx_max": profile.max_linear_speed_mps,
        "controller.wz_max": profile.max_angular_speed_radps,
    }
    for parameter in parameters:
        limit = limits.get(parameter.name)
        if limit is not None and parameter.kind is not ParameterKind.CATEGORICAL:
            if parameter.upper is not None and float(parameter.upper) > limit:
                raise ValueError(
                    f"parameter {parameter.name!r} upper bound {parameter.upper:g} exceeds "
                    f"robot profile {profile.profile_id!r} limit {limit:g}"
                )
    for name, limit in limits.items():
        value = base.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) > limit):
            raise ValueError(f"base_configuration.{name} exceeds robot profile {profile.profile_id!r} limit {limit:g}")


def _experiment_fingerprint(manifest: TuningManifest, backend: ExperimentBackend) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "manifest": manifest,
                "backend_id": backend.backend_id,
                "backend_version": backend.backend_version,
            }
        ).encode("utf-8")
    ).hexdigest()[:10]


def _render_tuning_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# {data['title']}",
        "",
        f"- Tuning ID: `{data['tuning_id']}`",
        f"- Strategy: `{data['strategy_id']}`",
        f"- Backend: `{data['backend_id']}@{data['backend_version']}`",
        f"- Candidates in stored study/result: {data['candidate_count']}",
        "",
        "## Feasible Pareto front",
        "",
    ]
    if not data["pareto_front"]:
        lines.append("No feasible candidate is available.")
    else:
        lines.extend(["| Candidate | Parameters | Objectives |", "|---|---|---|"])
        for candidate in data["pareto_front"]:
            lines.append(
                f"| `{candidate['candidate_id']}` | `{json.dumps(candidate['parameters'], sort_keys=True)}` "
                f"| `{json.dumps(candidate['objectives'], sort_keys=True)}` |"
            )
    lines.extend(["", "## Candidate diagnostics", "", "| Candidate | Feasible | Objectives | Constraint margins |", "|---|---:|---|---|"])
    for candidate in data["candidates"]:
        lines.append(
            f"| `{candidate['candidate_id']}` | {candidate.get('feasible')} "
            f"| `{json.dumps(candidate.get('objectives', {}), sort_keys=True)}` "
            f"| `{json.dumps(candidate.get('constraints', {}), sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "A tuning result is exploratory. Confirm selected candidates with the predeclared "
            "holdout scenarios/seeds before treating the result as an improvement.",
            "",
        ]
    )
    return "\n".join(lines)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _object_array(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return [_object(item, f"{label} entry") for item in value]


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    result = _integer(value, label)
    if result < 1:
        raise ValueError(f"{label} must be positive")
    return result


def _parameter(data: dict[str, Any]) -> ParameterSpec:
    allowed = {"name", "kind", "lower", "upper", "choices", "step", "log"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"parameter contains unknown field(s): {', '.join(sorted(unknown))}")
    try:
        kind = ParameterKind(data["kind"])
    except (KeyError, ValueError) as exc:
        raise ValueError("parameter.kind must be float, integer, or categorical") from exc
    choices = data.get("choices", [])
    if not isinstance(choices, list):
        raise ValueError("parameter.choices must be an array")
    log_value = data.get("log", False)
    if not isinstance(log_value, bool):
        raise ValueError("parameter.log must be a boolean")
    return ParameterSpec(
        name=_nonempty_string(data.get("name"), "parameter.name"),
        kind=kind,
        lower=data.get("lower"),
        upper=data.get("upper"),
        choices=tuple(choices),
        step=data.get("step"),
        log=log_value,
    )


def _objective(data: dict[str, Any]) -> ObjectiveSpec:
    try:
        direction = Direction(data["direction"])
    except (KeyError, ValueError) as exc:
        raise ValueError("objective.direction must be minimize or maximize") from exc
    unknown = set(data) - {"metric_id", "direction", "aggregation"}
    if unknown:
        raise ValueError(f"objective contains unknown field(s): {', '.join(sorted(unknown))}")
    return ObjectiveSpec(_nonempty_string(data.get("metric_id"), "objective.metric_id"), direction)


def _constraint(data: dict[str, Any]) -> dict[str, Any]:
    unknown = set(data) - {"constraint_id", "description", "metric_id", "operator", "threshold", "aggregation"}
    if unknown:
        raise ValueError(f"constraint contains unknown field(s): {', '.join(sorted(unknown))}")
    operator = data.get("operator")
    if operator not in {"<=", ">="}:
        raise ValueError("constraint.operator must be <= or >=")
    threshold = data.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)):
        raise ValueError("constraint.threshold must be a finite number")
    aggregation = data.get("aggregation", "worst_case")
    if aggregation not in {"worst_case", "mean", "median", "min", "max", "p95"}:
        raise ValueError("constraint.aggregation must be worst_case, mean, median, min, max, or p95")
    return {
        "constraint_id": _nonempty_string(data.get("constraint_id"), "constraint.constraint_id"),
        "description": _nonempty_string(data.get("description"), "constraint.description"),
        "metric_id": _nonempty_string(data.get("metric_id"), "constraint.metric_id"),
        "operator": operator,
        "threshold": float(threshold),
        "aggregation": aggregation,
    }


def _aggregate(values: list[float], mode: str) -> float:
    if mode == "mean":
        return fmean(values)
    if mode == "median":
        return median(values)
    if mode == "min":
        return min(values)
    if mode == "max":
        return max(values)
    ordered = sorted(values)
    position = 0.95 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _aggregate_constraint(values: list[float], mode: str, operator: str) -> float:
    if mode == "worst_case":
        return max(values) if operator == "<=" else min(values)
    return _aggregate(values, mode)


def _validate_campaign_template(template: dict[str, Any]) -> None:
    if not isinstance(template.get("systems"), list) or not template["systems"]:
        raise ValueError("tuning.campaign.systems must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in template["systems"]):
        raise ValueError("tuning.campaign.systems entries must be non-empty strings")
    if len(set(template["systems"])) != len(template["systems"]):
        raise ValueError("tuning.campaign.systems entries must be unique")
    if not isinstance(template.get("scenarios"), list) or not template["scenarios"]:
        raise ValueError("tuning.campaign.scenarios must be a non-empty array")
    for scenario in _object_array(template["scenarios"], "tuning.campaign.scenarios"):
        if set(scenario) - {"scenario_id", "parameters"}:
            raise ValueError("tuning campaign scenarios accept only scenario_id and parameters")
        _nonempty_string(scenario.get("scenario_id"), "scenario.scenario_id")
        _object(scenario.get("parameters", {}), "scenario.parameters")
        canonical_json(scenario.get("parameters", {}))
    scenario_ids = [item["scenario_id"] for item in template["scenarios"]]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("tuning.campaign.scenario_id values must be unique")
    repetitions = _positive_integer(template.get("repetitions"), "tuning.campaign.repetitions")
    seeds = template.get("seeds", [])
    if not isinstance(seeds, list) or any(isinstance(item, bool) or not isinstance(item, int) for item in seeds):
        raise ValueError("tuning.campaign.seeds must be an array of integers")
    if seeds and len(seeds) != repetitions:
        raise ValueError("tuning.campaign.seeds must match repetitions")
    if "metadata" in template:
        _object(template["metadata"], "tuning.campaign.metadata")
        canonical_json(template["metadata"])
    _positive_integer(template.get("max_parallel", 1), "tuning.campaign.max_parallel")
    retries = template.get("max_infrastructure_retries", 0)
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ValueError("tuning.campaign.max_infrastructure_retries must be a non-negative integer")
    wall_time = template.get("wall_time_budget_s")
    if wall_time is not None and (
        isinstance(wall_time, bool)
        or not isinstance(wall_time, (int, float))
        or not math.isfinite(float(wall_time))
        or wall_time <= 0
    ):
        raise ValueError("tuning.campaign.wall_time_budget_s must be finite and positive")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value} is not valid in a manifest")
