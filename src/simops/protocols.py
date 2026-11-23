"""Replaceable boundaries for execution, measurement, storage and rendering."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol

from .contracts import ArtifactRef, CampaignSpec, MetricValue, RunResult, RunSpec
from .optimization import OptimizationResult, TuningEvaluator, TuningSpec


class MetricPlugin(Protocol):
    """Derives versioned measurements from a run and its raw artifacts."""

    plugin_id: str
    definition_version: str

    def compute(
        self,
        run: RunSpec,
        result: RunResult,
        artifacts: Iterable[ArtifactRef],
    ) -> Sequence[MetricValue]: ...


class ArtifactStore(Protocol):
    """Stores immutable artifacts and resolves them by reference."""

    def put(
        self,
        name: str,
        content: bytes,
        media_type: str,
        schema_version: str | None = None,
    ) -> ArtifactRef: ...

    def get(self, reference: ArtifactRef) -> bytes: ...


class CampaignStore(Protocol):
    """Persists campaign plans and append-only run state transitions."""

    def register_campaign(self, spec: CampaignSpec, backend_id: str, backend_version: str) -> str: ...

    def run_states(self, campaign_id: str) -> Mapping[str, Mapping[str, object]]: ...

    def results(self, campaign_id: str) -> Sequence[RunResult]: ...

    def events(self, campaign_id: str) -> Sequence[Mapping[str, object]]: ...


class SearchStrategy(Protocol):
    """Runs a bounded tuning study through a backend-neutral evaluator callback."""

    strategy_id: str

    def optimize(
        self,
        spec: TuningSpec,
        evaluate: TuningEvaluator,
        budget: int,
    ) -> OptimizationResult: ...


class ReportRenderer(Protocol):
    """Renders a previously calculated report model without recomputing metrics."""

    format_id: str

    def render(self, report_model: Mapping[str, object]) -> bytes: ...
