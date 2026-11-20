"""JSON campaign manifest loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .planner import (
    CampaignMatrix,
    ConfigurationDefinition,
    ScenarioDefinition,
    plan_campaign,
)


@dataclass(frozen=True, slots=True)
class LoadedCampaign:
    backend_id: str
    campaign: Any


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _reject_unknown(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown field(s): {', '.join(unknown)}")


def load_campaign_manifest(path: str | Path) -> LoadedCampaign:
    """Load a declarative matrix from JSON and expand it into stable run IDs."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read campaign manifest {source}: {exc}") from exc
    root = _mapping(raw, "manifest")
    _reject_unknown(root, {"schema_version", "backend", "campaign"}, "manifest")
    if root.get("schema_version") != "0.1.0":
        raise ValueError("schema_version must be '0.1.0'")
    backend_id = _identifier(root.get("backend"), "backend")
    campaign = _mapping(root.get("campaign"), "campaign")
    _reject_unknown(
        campaign,
        {
            "campaign_id", "title", "systems", "scenarios", "configurations", "repetitions",
            "seeds", "max_parallel", "max_infrastructure_retries", "wall_time_budget_s",
            "metadata",
        },
        "campaign",
    )

    scenario_entries = _list_of_mappings(campaign.get("scenarios"), "scenarios")
    for item in scenario_entries:
        _reject_unknown(item, {"scenario_id", "parameters"}, "scenario")
    configuration_entries = _list_of_mappings(campaign.get("configurations"), "configurations")
    for item in configuration_entries:
        _reject_unknown(item, {"configuration_id", "values"}, "configuration")

    scenarios = tuple(
        ScenarioDefinition(
            scenario_id=_identifier(item.get("scenario_id"), "scenario_id"),
            parameters=_mapping(item.get("parameters", {}), "scenario parameters"),
        )
        for item in scenario_entries
    )
    configurations = tuple(
        ConfigurationDefinition(
            configuration_id=_identifier(
                item.get("configuration_id"), "configuration_id"
            ),
            values=_mapping(item.get("values", {}), "configuration values"),
        )
        for item in configuration_entries
    )
    systems = campaign.get("systems")
    if not isinstance(systems, list):
        raise ValueError("campaign.systems must be a JSON array")
    if any(not isinstance(system, str) for system in systems):
        raise ValueError("campaign.systems entries must be strings")
    repetitions = campaign.get("repetitions")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int):
        raise ValueError("campaign.repetitions must be an integer")
    seeds_value = campaign.get("seeds", [])
    if not isinstance(seeds_value, list) or any(
        isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds_value
    ):
        raise ValueError("campaign.seeds must be an array of integers")
    max_parallel = campaign.get("max_parallel", 1)
    retries = campaign.get("max_infrastructure_retries", 0)
    for value, label in ((max_parallel, "max_parallel"), (retries, "max_infrastructure_retries")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"campaign.{label} must be an integer")
    wall_time = campaign.get("wall_time_budget_s")
    if wall_time is not None and (
        isinstance(wall_time, bool) or not isinstance(wall_time, (int, float))
    ):
        raise ValueError("campaign.wall_time_budget_s must be numeric")
    metadata = _mapping(campaign.get("metadata", {}), "campaign metadata")

    planned = plan_campaign(
        CampaignMatrix(
            campaign_id=_identifier(campaign.get("campaign_id"), "campaign_id"),
            title=_identifier(campaign.get("title"), "title"),
            systems=tuple(systems),
            scenarios=scenarios,
            configurations=configurations,
            repetitions=repetitions,
            seeds=tuple(seeds_value),
            max_parallel=max_parallel,
            max_infrastructure_retries=retries,
            wall_time_budget_s=float(wall_time) if wall_time is not None else None,
            metadata=metadata,
        )
    )
    return LoadedCampaign(backend_id=backend_id, campaign=planned)


def _list_of_mappings(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"campaign.{label} must be a JSON array")
    return [_mapping(item, f"{label} entry") for item in value]


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value} is not valid in a manifest")
