"""Stable JSON encoders for campaign manifests and persisted run records."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .contracts import (
    ArtifactRef,
    CampaignSpec,
    MetricState,
    MetricValue,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
)


def to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: to_json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def pretty_json(value: Any) -> str:
    return json.dumps(
        to_json_value(value),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def campaign_spec_from_dict(data: dict[str, Any]) -> CampaignSpec:
    runs = tuple(
        RunSpec(
            run_id=item["run_id"],
            campaign_id=item["campaign_id"],
            scenario_id=item["scenario_id"],
            system_id=item["system_id"],
            configuration_id=item["configuration_id"],
            repetition=int(item["repetition"]),
            seed=item.get("seed"),
            configuration=item.get("configuration", {}),
            scenario_parameters=item.get("scenario_parameters", {}),
            metadata=item.get("metadata", {}),
        )
        for item in data["runs"]
    )
    return CampaignSpec(
        campaign_id=data["campaign_id"],
        title=data["title"],
        runs=runs,
        max_parallel=int(data.get("max_parallel", 1)),
        max_infrastructure_retries=int(data.get("max_infrastructure_retries", 0)),
        wall_time_budget_s=data.get("wall_time_budget_s"),
        metadata=data.get("metadata", {}),
    )


def run_result_from_dict(data: dict[str, Any]) -> RunResult:
    metrics = tuple(
        MetricValue(
            metric_id=item["metric_id"],
            value=item.get("value"),
            unit=item.get("unit"),
            state=MetricState(item["state"]),
            definition_version=item["definition_version"],
            reason=item.get("reason"),
            sample_count=item.get("sample_count"),
            metadata=item.get("metadata", {}),
        )
        for item in data.get("metrics", [])
    )
    artifacts = tuple(ArtifactRef(**item) for item in data.get("artifacts", []))
    return RunResult(
        run_id=data["run_id"],
        status=RunStatus(data["status"]),
        system_outcome=SystemOutcome(data["system_outcome"]),
        metrics=metrics,
        artifacts=artifacts,
        started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
        finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
        provenance=data.get("provenance", {}),
        warnings=tuple(data.get("warnings", [])),
        failure_reason=data.get("failure_reason"),
        schema_version=data.get("schema_version", "0.1.0"),
    )
