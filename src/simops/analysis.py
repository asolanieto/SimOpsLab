"""Small dependency-free campaign summaries derived from persisted run outcomes."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from statistics import fmean, median
from typing import Any

from .contracts import (
    CampaignSpec,
    MetricState,
    MetricValue,
    RunResult,
    RunStatus,
    SystemOutcome,
)


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if trials <= 0:
        return None
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half_width = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials))
        / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _metric_summary(metrics: Iterable[MetricValue], planned_count: int) -> dict[str, Any]:
    materialized = tuple(metrics)
    observed = [metric for metric in materialized if metric.state is MetricState.OBSERVED]
    values = [metric.value for metric in observed]
    unit_values = sorted({metric.unit for metric in materialized if metric.unit is not None})
    versions = sorted({metric.definition_version for metric in materialized})
    reasons = Counter(
        metric.reason or metric.state.value
        for metric in materialized
        if metric.state is not MetricState.OBSERVED
    )
    result: dict[str, Any] = {
        "n_observed": len(observed),
        "n_planned": planned_count,
        "n_missing": max(0, planned_count - len(observed)),
        "non_observed_states": dict(Counter(
            metric.state.value for metric in materialized if metric.state is not MetricState.OBSERVED
        )),
        "reasons": dict(reasons),
        "units": unit_values,
        "definition_versions": versions,
    }
    if values and all(isinstance(value, bool) for value in values):
        true_count = sum(values)
        result.update(
            value_type="boolean",
            true_count=true_count,
            true_rate=true_count / len(values),
        )
    elif values and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        for value in values
    ):
        numbers = [float(value) for value in values]
        result.update(
            value_type="numeric",
            mean=fmean(numbers),
            median=median(numbers),
            q1=_quantile(numbers, 0.25),
            q3=_quantile(numbers, 0.75),
            minimum=min(numbers),
            maximum=max(numbers),
        )
    elif values:
        result["value_type"] = "mixed_or_non_numeric"
        result["distinct_values"] = sorted({str(value) for value in values})
    else:
        result["value_type"] = "unobserved"
    return result


def analyze_campaign(
    campaign: CampaignSpec,
    results: Iterable[RunResult],
    *,
    backend_id: str | None = None,
    backend_version: str | None = None,
) -> dict[str, Any]:
    """Return the canonical report model; renderers must not recompute statistics."""
    results_by_id = {result.run_id: result for result in results}
    planned_runs = campaign.runs
    run_groups: dict[tuple[str, str, str], list[tuple[Any, RunResult | None]]] = defaultdict(list)
    for run in planned_runs:
        result = results_by_id.get(run.run_id)
        run_groups[(run.system_id, run.scenario_id, run.configuration_id)].append((run, result))

    result_statuses = Counter(
        results_by_id[run.run_id].status.value if run.run_id in results_by_id else "not_started"
        for run in planned_runs
    )
    outcomes = Counter(
        results_by_id[run.run_id].system_outcome.value
        for run in planned_runs
        if run.run_id in results_by_id
    )
    group_summaries = []
    for (system_id, scenario_id, configuration_id), pairs in sorted(run_groups.items()):
        group_results = [result for _, result in pairs if result is not None]
        success_observations = [
            result.system_outcome
            for result in group_results
            if result.system_outcome
            not in (SystemOutcome.UNKNOWN, SystemOutcome.NOT_APPLICABLE)
            and result.status not in (RunStatus.FAILED_INFRASTRUCTURE, RunStatus.INTERRUPTED)
        ]
        successes = sum(outcome is SystemOutcome.SUCCESS for outcome in success_observations)
        interval = wilson_interval(successes, len(success_observations))
        metric_sets: dict[tuple[str, str, str | None], list[MetricValue]] = defaultdict(list)
        for result in group_results:
            for metric in result.metrics:
                metric_sets[(metric.metric_id, metric.definition_version, metric.unit)].append(metric)
        metrics = {
            f"{metric_id}@{version}": _metric_summary(values, len(pairs))
            for (metric_id, version, _unit), values in sorted(metric_sets.items())
        }
        group_summaries.append(
            {
                "system_id": system_id,
                "scenario_id": scenario_id,
                "configuration_id": configuration_id,
                "planned_runs": len(pairs),
                "result_runs": len(group_results),
                "success": {
                    "successes": successes,
                    "known_outcomes": len(success_observations),
                    "rate": successes / len(success_observations) if success_observations else None,
                    "wilson_95": list(interval) if interval is not None else None,
                },
                "metrics": metrics,
            }
        )

    return {
        "schema_version": "0.1.0",
        "campaign": {
            "campaign_id": campaign.campaign_id,
            "title": campaign.title,
            "backend_id": backend_id,
            "backend_version": backend_version,
            "planned_runs": len(planned_runs),
            "result_runs": len(results_by_id),
            "run_statuses": dict(result_statuses),
            "system_outcomes": dict(outcomes),
            "metadata": campaign.metadata,
        },
        "groups": group_summaries,
        "limitations": [
            "Statistics describe only the supplied campaign and do not establish general performance.",
            "Configuration selection and holdout confirmation must use separate scenarios or seeds.",
        ],
    }
