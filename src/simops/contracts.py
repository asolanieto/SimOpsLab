"""Version 0.1 domain contracts.

These standard-library data classes deliberately know nothing about ROS, Gazebo,
EasyNav, a particular simulator, or an LLM transport.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class RunStatus(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED_SYSTEM = "failed_system"
    FAILED_INFRASTRUCTURE = "failed_infrastructure"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class SystemOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    EXPECTED_ABORT = "expected_abort"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class MetricState(StrEnum):
    OBSERVED = "observed"
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class MetricValue:
    """One metric result, including its measurement status and definition version."""

    metric_id: str
    value: JSONValue
    unit: str | None
    state: MetricState
    definition_version: str
    reason: str | None = None
    sample_count: int | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Reference to immutable run data stored outside the result summary."""

    name: str
    uri: str
    media_type: str
    sha256: str | None = None
    size_bytes: int | None = None
    schema_version: str | None = None


@dataclass(frozen=True, slots=True)
class RunSpec:
    """Fully resolved specification for one experimental run."""

    run_id: str
    campaign_id: str
    scenario_id: str
    system_id: str
    configuration_id: str
    repetition: int
    seed: int | None = None
    configuration: Mapping[str, JSONValue] = field(default_factory=dict)
    scenario_parameters: Mapping[str, JSONValue] = field(default_factory=dict)
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CampaignSpec:
    """Resolved campaign envelope. Matrix expansion belongs to the planner."""

    campaign_id: str
    title: str
    runs: tuple[RunSpec, ...]
    max_parallel: int = 1
    max_infrastructure_retries: int = 0
    wall_time_budget_s: float | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunResult:
    """Persistable outcome; operational status and functional outcome stay separate."""

    run_id: str
    status: RunStatus
    system_outcome: SystemOutcome
    metrics: tuple[MetricValue, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    provenance: Mapping[str, JSONValue] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    failure_reason: str | None = None
    schema_version: str = "0.1.0"


def validate_metric_value(metric: MetricValue) -> None:
    """Raise ValueError for contradictory or incomplete metric states."""
    if not metric.metric_id.strip():
        raise ValueError("metric_id must not be empty")
    if not metric.definition_version.strip():
        raise ValueError("definition_version must not be empty")
    if not isinstance(metric.state, MetricState):
        raise ValueError("state must be a MetricState")
    if metric.unit is not None and (not isinstance(metric.unit, str) or not metric.unit.strip()):
        raise ValueError("unit must be a non-empty string or None")
    if metric.sample_count is not None and (
        isinstance(metric.sample_count, bool)
        or not isinstance(metric.sample_count, int)
        or metric.sample_count < 0
    ):
        raise ValueError("sample_count must be a non-negative integer or None")
    if metric.state is MetricState.OBSERVED and metric.value is None:
        raise ValueError("an observed metric must have a value")
    if metric.state is not MetricState.OBSERVED and metric.value is not None:
        raise ValueError("a non-observed metric must use value=None")
    if metric.state is not MetricState.OBSERVED and not metric.reason:
        raise ValueError("a non-observed metric must explain why")
    if metric.state is MetricState.OBSERVED:
        _validate_json_value(metric.value, "metric.value")
    _validate_json_value(dict(metric.metadata), "metric.metadata")


def _validate_json_value(value: object, label: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must contain only finite numbers")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, label)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{label} object keys must be strings")
        for item in value.values():
            _validate_json_value(item, label)
        return
    raise ValueError(f"{label} contains a non-JSON value of type {type(value).__name__}")
