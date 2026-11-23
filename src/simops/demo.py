"""Deterministic, fast navigation-like backend for tutorials and CI smoke tests.

This backend is a synthetic benchmark. It is not a physics simulator and must not
be used to claim Nav2 or robot performance.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime

from .backends import ExecutionContext
from .contracts import (
    MetricState,
    MetricValue,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
)


def _number(values: dict[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


class DemoNavigationBackend:
    """Small synthetic task with noise, failures, safety and timing metrics."""

    backend_id = "demo"
    backend_version = "0.1.0"
    thread_safe = True

    def validate(self, run: RunSpec) -> Sequence[str]:
        errors = []
        try:
            speed = _number(dict(run.configuration), "max_speed_mps", 0.45)
            gain = _number(dict(run.configuration), "controller_gain", 1.0)
            inflation = _number(dict(run.configuration), "inflation_radius_m", 0.45)
            difficulty = _number(dict(run.scenario_parameters), "difficulty", 0.25)
            distance = _number(dict(run.scenario_parameters), "distance_m", 8.0)
            if not 0.1 <= speed <= 1.5:
                errors.append("configuration.max_speed_mps must be between 0.1 and 1.5")
            if not 0.2 <= gain <= 2.5:
                errors.append("configuration.controller_gain must be between 0.2 and 2.5")
            if not 0.05 <= inflation <= 1.0:
                errors.append("configuration.inflation_radius_m must be between 0.05 and 1.0")
            if not 0.0 <= difficulty <= 1.0:
                errors.append("scenario.difficulty must be between 0 and 1")
            if distance <= 0:
                errors.append("scenario.distance_m must be positive")
        except ValueError as exc:
            errors.append(str(exc))
        return tuple(errors)

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        if context.cancellation_requested or context.deadline_expired:
            now = datetime.now(UTC)
            return RunResult(
                run_id=run.run_id,
                status=RunStatus.CANCELLED,
                system_outcome=SystemOutcome.UNKNOWN,
                started_at=now,
                finished_at=now,
                failure_reason="cancel requested or campaign time budget expired before run start",
            )
        errors = self.validate(run)
        if errors:
            raise ValueError("; ".join(errors))
        started = datetime.now(UTC)
        configuration = dict(run.configuration)
        scenario = dict(run.scenario_parameters)
        speed = _number(configuration, "max_speed_mps", 0.45)
        gain = _number(configuration, "controller_gain", 1.0)
        inflation = _number(configuration, "inflation_radius_m", 0.45)
        difficulty = _number(scenario, "difficulty", 0.25)
        distance = _number(scenario, "distance_m", 8.0)

        effective_seed = run.seed
        if effective_seed is None:
            effective_seed = int.from_bytes(
                hashlib.sha256(run.run_id.encode("utf-8")).digest()[:8], "big"
            )
        rng = random.Random(effective_seed)
        overspeed_risk = max(0.0, speed - 0.58) * 0.85
        weak_gain_risk = max(0.0, 0.9 - gain) * 0.16
        clearance_risk = max(0.0, 0.36 - inflation) * 1.1
        risk = min(0.92, max(0.015, difficulty * 0.18 + overspeed_risk + weak_gain_risk + clearance_risk))
        success = rng.random() >= risk
        collision_chance = min(0.8, difficulty * 0.08 + overspeed_risk * 0.65 + clearance_risk * 0.4)
        collision_count = int(rng.random() < collision_chance)
        jitter = rng.uniform(-0.04, 0.04)
        duration = distance / speed * (1.0 + 0.20 * difficulty + jitter)
        if not success:
            duration = max(duration, distance / max(speed, 0.1) * 1.8)
        path_length = distance * (1.0 + 0.16 * difficulty + 0.05 * (1.0 - gain) + abs(jitter))
        clearance = max(0.0, inflation - 0.12 * difficulty - (0.16 if collision_count else 0.0))
        finished = datetime.now(UTC)

        metrics = (
            MetricValue("task.success", success, "bool", MetricState.OBSERVED, "1"),
            MetricValue("task.duration_s", duration, "s", MetricState.OBSERVED, "1"),
            MetricValue(
                "safety.collision_count", collision_count, "count", MetricState.OBSERVED, "1"
            ),
            MetricValue("navigation.path_length_m", path_length, "m", MetricState.OBSERVED, "1"),
            MetricValue(
                "safety.min_clearance_m", clearance, "m", MetricState.OBSERVED, "1"
            ),
        )
        return RunResult(
            run_id=run.run_id,
            status=RunStatus.COMPLETED,
            system_outcome=SystemOutcome.SUCCESS if success else SystemOutcome.FAILURE,
            metrics=metrics,
            started_at=started,
            finished_at=finished,
            provenance={
                "backend_id": self.backend_id,
                "backend_version": self.backend_version,
                "effective_seed": effective_seed,
                "synthetic": True,
            },
            warnings=("synthetic demo backend; results do not represent physical Nav2 behavior",),
        )
