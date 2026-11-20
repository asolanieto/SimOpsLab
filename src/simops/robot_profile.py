"""Portable robot capability profile used to define safe tuning envelopes."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RobotProfile:
    profile_id: str
    name: str
    footprint_radius_m: float
    max_linear_speed_mps: float
    max_angular_speed_radps: float
    sensors: tuple[dict[str, Any], ...]
    reference_topics: dict[str, str]
    source_path: str


def load_robot_profile(path: str | Path) -> RobotProfile:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read robot profile {source}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != "0.1.0":
        raise ValueError("robot profile must be an object with schema_version '0.1.0'")
    if set(data) != {"schema_version", "profile_id", "name", "geometry", "motion_limits", "sensors", "reference_topics"}:
        raise ValueError("robot profile has missing or unknown top-level fields")
    geometry = _object(data["geometry"], "geometry")
    limits = _object(data["motion_limits"], "motion_limits")
    if set(geometry) != {"footprint_radius_m"}:
        raise ValueError("geometry must define footprint_radius_m")
    if set(limits) != {"max_linear_speed_mps", "max_angular_speed_radps"}:
        raise ValueError("motion_limits must define max_linear_speed_mps and max_angular_speed_radps")
    sensors = data["sensors"]
    if not isinstance(sensors, list) or not sensors:
        raise ValueError("sensors must be a non-empty array")
    for sensor in sensors:
        if not isinstance(sensor, dict) or set(sensor) != {"name", "topic", "message_type", "expected_hz", "required"}:
            raise ValueError("each sensor needs name, topic, message_type, expected_hz, and required")
        _name(sensor["name"], "sensor.name")
        _topic(sensor["topic"], "sensor.topic")
        _name(sensor["message_type"], "sensor.message_type")
        _positive_number(sensor["expected_hz"], "sensor.expected_hz")
        if not isinstance(sensor["required"], bool):
            raise ValueError("sensor.required must be boolean")
    topics = [sensor["topic"] for sensor in sensors]
    if len(topics) != len(set(topics)):
        raise ValueError("sensor topics must be unique")
    references = _object(data["reference_topics"], "reference_topics")
    allowed_references = {"ground_truth", "contacts", "clock", "diagnostics"}
    if set(references) - allowed_references:
        raise ValueError(f"reference_topics accepts only: {', '.join(sorted(allowed_references))}")
    for name, topic in references.items():
        _topic(topic, f"reference_topics.{name}")
    return RobotProfile(
        profile_id=_name(data["profile_id"], "profile_id"),
        name=_name(data["name"], "name"),
        footprint_radius_m=_positive_number(geometry["footprint_radius_m"], "geometry.footprint_radius_m"),
        max_linear_speed_mps=_positive_number(limits["max_linear_speed_mps"], "motion_limits.max_linear_speed_mps"),
        max_angular_speed_radps=_positive_number(limits["max_angular_speed_radps"], "motion_limits.max_angular_speed_radps"),
        sensors=tuple(sensors),
        reference_topics=dict(references),
        source_path=source.name,
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _topic(value: Any, label: str) -> str:
    name = _name(value, label)
    if name.startswith("~") or " " in name or "//" in name:
        raise ValueError(f"{label} must be a valid ROS topic name")
    normalized = name[1:] if name.startswith("/") else name
    if not normalized or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in normalized.split("/")):
        raise ValueError(f"{label} must be a valid ROS topic name")
    return name


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return float(value)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value} is not valid in a robot profile")
