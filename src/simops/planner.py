"""Deterministic expansion of a declarative campaign matrix."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .contracts import CampaignSpec, JSONValue, RunSpec


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    scenario_id: str
    parameters: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigurationDefinition:
    configuration_id: str
    values: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CampaignMatrix:
    campaign_id: str
    title: str
    systems: tuple[str, ...]
    scenarios: tuple[ScenarioDefinition, ...]
    configurations: tuple[ConfigurationDefinition, ...]
    repetitions: int
    seeds: tuple[int, ...] = ()
    max_parallel: int = 1
    max_infrastructure_retries: int = 0
    wall_time_budget_s: float | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


class PlanningError(ValueError):
    """Raised when a campaign matrix is ambiguous or cannot be expanded."""


def _require_unique_nonempty(values: Sequence[str], label: str) -> None:
    if not values or any(not value.strip() for value in values):
        raise PlanningError(f"{label} must contain non-empty identifiers")
    if len(set(values)) != len(values):
        raise PlanningError(f"{label} contains duplicate identifiers")


def _run_id(identity: Mapping[str, JSONValue]) -> str:
    try:
        canonical = json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PlanningError("run identity must contain only finite JSON-compatible values") from exc
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"run-{digest}"


def run_id_for(run: RunSpec) -> str:
    """Recompute a run's identity to detect post-plan mutation of nested mappings."""
    identity: dict[str, JSONValue] = {
        "campaign_id": run.campaign_id,
        "system_id": run.system_id,
        "scenario_id": run.scenario_id,
        "configuration_id": run.configuration_id,
        "repetition": run.repetition,
        "seed": run.seed,
        "configuration": dict(run.configuration),
        "scenario_parameters": dict(run.scenario_parameters),
    }
    return _run_id(identity)


def plan_campaign(matrix: CampaignMatrix) -> CampaignSpec:
    """Expand systems × scenarios × configurations × repetitions deterministically.

    If seeds are supplied, exactly one seed is required per repetition. With no seeds,
    repetition indices still distinguish runs but the backend chooses its own randomness.
    """
    if not matrix.campaign_id.strip():
        raise PlanningError("campaign_id must not be empty")
    if not matrix.title.strip():
        raise PlanningError("title must not be empty")
    _require_unique_nonempty(matrix.systems, "systems")
    _require_unique_nonempty(
        [scenario.scenario_id for scenario in matrix.scenarios],
        "scenarios",
    )
    _require_unique_nonempty(
        [configuration.configuration_id for configuration in matrix.configurations],
        "configurations",
    )
    if matrix.repetitions < 1:
        raise PlanningError("repetitions must be at least 1")
    if matrix.seeds and len(matrix.seeds) != matrix.repetitions:
        raise PlanningError("provide exactly one seed per repetition or omit seeds")
    if matrix.seeds and len(set(matrix.seeds)) != len(matrix.seeds):
        raise PlanningError("seeds must be unique")
    if matrix.max_parallel < 1:
        raise PlanningError("max_parallel must be at least 1")
    if matrix.max_infrastructure_retries < 0:
        raise PlanningError("max_infrastructure_retries must not be negative")
    if matrix.wall_time_budget_s is not None and (
        not math.isfinite(matrix.wall_time_budget_s) or matrix.wall_time_budget_s <= 0
    ):
        raise PlanningError("wall_time_budget_s must be finite and positive when provided")

    runs: list[RunSpec] = []
    for system_id in matrix.systems:
        for scenario in matrix.scenarios:
            for configuration in matrix.configurations:
                for repetition in range(matrix.repetitions):
                    seed = matrix.seeds[repetition] if matrix.seeds else None
                    identity: dict[str, JSONValue] = {
                        "campaign_id": matrix.campaign_id,
                        "system_id": system_id,
                        "scenario_id": scenario.scenario_id,
                        "configuration_id": configuration.configuration_id,
                        "repetition": repetition,
                        "seed": seed,
                        "configuration": dict(configuration.values),
                        "scenario_parameters": dict(scenario.parameters),
                    }
                    runs.append(
                        RunSpec(
                            run_id=_run_id(identity),
                            campaign_id=matrix.campaign_id,
                            scenario_id=scenario.scenario_id,
                            system_id=system_id,
                            configuration_id=configuration.configuration_id,
                            repetition=repetition,
                            seed=seed,
                            configuration=dict(configuration.values),
                            scenario_parameters=dict(scenario.parameters),
                        )
                    )

    return CampaignSpec(
        campaign_id=matrix.campaign_id,
        title=matrix.title,
        runs=tuple(runs),
        max_parallel=matrix.max_parallel,
        max_infrastructure_retries=matrix.max_infrastructure_retries,
        wall_time_budget_s=matrix.wall_time_budget_s,
        metadata=dict(matrix.metadata),
    )
