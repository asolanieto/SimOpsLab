"""Backend-neutral local campaign execution with resumable per-run attempts."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from threading import Event

from .backends import ExecutionContext, ExperimentBackend
from .contracts import (
    CampaignSpec,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
    validate_metric_value,
)
from .paths import path_component
from .planner import run_id_for
from .serialization import campaign_spec_from_dict, canonical_json
from .store import FilesystemArtifactStore, SQLiteCampaignStore, utc_now


class CampaignValidationError(ValueError):
    """The selected backend rejected one or more planned runs before execution."""

    def __init__(self, errors: Sequence[tuple[str, str]]) -> None:
        self.errors = tuple(errors)
        detail = "\n".join(f"{run_id}: {message}" for run_id, message in self.errors)
        super().__init__(f"campaign validation failed:\n{detail}")


class CampaignRunner:
    def __init__(
        self,
        store: SQLiteCampaignStore,
        *,
        artifact_root: str | Path | None = None,
        work_root: str | Path | None = None,
    ) -> None:
        self.store = store
        base = store.database_path.parent
        self.artifact_root = Path(artifact_root) if artifact_root else base / "artifacts"
        self.work_root = Path(work_root) if work_root else base / "work"

    @staticmethod
    def validate(campaign: CampaignSpec, backend: ExperimentBackend) -> None:
        errors: list[tuple[str, str]] = []
        if not isinstance(campaign.campaign_id, str) or not campaign.campaign_id.strip():
            errors.append(("campaign", "campaign_id must be a non-empty string"))
        if not isinstance(campaign.title, str) or not campaign.title.strip():
            errors.append(("campaign", "title must be a non-empty string"))
        if (
            isinstance(campaign.max_parallel, bool)
            or not isinstance(campaign.max_parallel, int)
            or campaign.max_parallel < 1
        ):
            errors.append(("campaign", "max_parallel must be an integer of at least 1"))
        if (
            isinstance(campaign.max_infrastructure_retries, bool)
            or not isinstance(campaign.max_infrastructure_retries, int)
            or campaign.max_infrastructure_retries < 0
        ):
            errors.append(("campaign", "max_infrastructure_retries must be non-negative"))
        if campaign.wall_time_budget_s is not None and (
            isinstance(campaign.wall_time_budget_s, bool)
            or not isinstance(campaign.wall_time_budget_s, (int, float))
            or not math.isfinite(campaign.wall_time_budget_s)
            or campaign.wall_time_budget_s <= 0
        ):
            errors.append(("campaign", "wall_time_budget_s must be finite and positive"))
        for attribute in ("backend_id", "backend_version", "thread_safe", "validate", "execute"):
            if not hasattr(backend, attribute):
                errors.append((campaign.campaign_id, f"backend is missing {attribute}"))
        if not isinstance(getattr(backend, "backend_id", None), str) or not getattr(backend, "backend_id", "").strip():
            errors.append((campaign.campaign_id, "backend_id must be a non-empty string"))
        if not isinstance(getattr(backend, "backend_version", None), str) or not getattr(backend, "backend_version", "").strip():
            errors.append((campaign.campaign_id, "backend_version must be a non-empty string"))
        thread_safe = getattr(backend, "thread_safe", None)
        if not isinstance(thread_safe, bool):
            errors.append((campaign.campaign_id, "backend.thread_safe must be a boolean"))
        if isinstance(campaign.max_parallel, int) and campaign.max_parallel > 1 and thread_safe is False:
            errors.append((campaign.campaign_id, "backend is not declared thread_safe; set max_parallel=1"))
        run_ids: set[str] = set()
        for run in campaign.runs:
            if not isinstance(run.run_id, str) or not run.run_id.strip():
                errors.append(("run", "run_id must be a non-empty string"))
            if run.run_id in run_ids:
                errors.append((run.run_id, "duplicate run_id"))
            run_ids.add(run.run_id)
            if run.campaign_id != campaign.campaign_id:
                errors.append((run.run_id, "campaign_id does not match the campaign"))
            for field_name in ("scenario_id", "system_id", "configuration_id"):
                value = getattr(run, field_name)
                if not isinstance(value, str) or not value.strip():
                    errors.append((run.run_id, f"{field_name} must be a non-empty string"))
            try:
                if run.run_id != run_id_for(run):
                    errors.append((run.run_id, "run fields changed after planning; re-plan the campaign"))
            except (TypeError, ValueError) as exc:
                errors.append((run.run_id, f"run identity is invalid: {exc}"))
            if isinstance(run.repetition, bool) or not isinstance(run.repetition, int) or run.repetition < 0:
                errors.append((run.run_id, "repetition must be a non-negative integer"))
            try:
                canonical_json(run)
            except (TypeError, ValueError) as exc:
                errors.append((run.run_id, f"run contains non-JSON values: {exc}"))
                continue
            try:
                messages = backend.validate(run)
            except Exception as exc:
                errors.append((run.run_id, f"backend validation raised {type(exc).__name__}: {exc}"))
                continue
            errors.extend((run.run_id, str(message)) for message in messages)
        if errors:
            raise CampaignValidationError(errors)

    def run_campaign(
        self,
        campaign: CampaignSpec,
        backend: ExperimentBackend,
        *,
        cancel_event: Event | None = None,
    ) -> tuple[RunResult, ...]:
        """Run a campaign with at most one local coordinator per store and campaign ID."""
        cancel_event = cancel_event or Event()
        with self.store.campaign_lock(campaign.campaign_id):
            return self._run_campaign_locked(campaign, backend, cancel_event=cancel_event)

    def _run_campaign_locked(
        self,
        campaign: CampaignSpec,
        backend: ExperimentBackend,
        *,
        cancel_event: Event,
    ) -> tuple[RunResult, ...]:
        """Run unfinished work, preserving completed results and every retry attempt."""
        if not campaign.runs:
            raise ValueError("campaign has no planned runs")
        campaign = campaign_spec_from_dict(json.loads(canonical_json(campaign)))
        self.validate(campaign, backend)
        self.store.register_campaign(campaign, backend.backend_id, backend.backend_version)
        recovered = self.store.recover_interrupted(campaign.campaign_id)
        if recovered:
            self.store.record_event(
                campaign.campaign_id,
                "resume_recovered_interrupted",
                {"count": recovered},
            )
        initial_states = self.store.run_states(campaign.campaign_id)
        deadline = (
            time.monotonic() + campaign.wall_time_budget_s
            if campaign.wall_time_budget_s is not None
            else None
        )
        candidates = []
        for run in campaign.runs:
            state = initial_states.get(run.run_id)
            if state is None:
                raise RuntimeError(f"planned run {run.run_id!r} is missing from campaign storage")
            if state["status"] in {
                RunStatus.COMPLETED.value,
                RunStatus.FAILED_SYSTEM.value,
                RunStatus.CANCELLED.value,
            }:
                continue
            if state["status"] in {RunStatus.FAILED_INFRASTRUCTURE.value, RunStatus.INTERRUPTED.value}:
                if state["infrastructure_failures"] > campaign.max_infrastructure_retries:
                    continue
            candidates.append(run)

        def execute(run: RunSpec) -> None:
            while True:
                if cancel_event.is_set():
                    self.store.record_event(
                        campaign.campaign_id,
                        "run_deferred_cancel_requested",
                        {"run_id": run.run_id},
                        run.run_id,
                    )
                    return
                if deadline is not None and time.monotonic() >= deadline:
                    self.store.record_event(
                        campaign.campaign_id,
                        "run_deferred_budget_exhausted",
                        {"run_id": run.run_id},
                        run.run_id,
                    )
                    return
                try:
                    attempt_number = self.store.start_attempt(run)
                except RuntimeError:
                    # A concurrent coordinator may have claimed this run since planning.
                    return
                started = utc_now()
                try:
                    artifact_store = FilesystemArtifactStore(
                        self.artifact_root / path_component(campaign.campaign_id)
                    )
                    workspace = (
                        self.work_root / path_component(campaign.campaign_id)
                        / path_component(run.run_id)
                        / f"attempt-{attempt_number:04d}"
                    )
                    workspace.mkdir(parents=True, exist_ok=True)
                    context = ExecutionContext(
                        attempt_number=attempt_number,
                        workspace=workspace,
                        artifacts=artifact_store,
                        deadline_monotonic=deadline,
                        cancel_event=cancel_event,
                    )
                    result = backend.execute(run, context)
                    result = self._validate_result(result, run, backend, started)
                except Exception as exc:
                    result = RunResult(
                        run_id=run.run_id,
                        status=RunStatus.FAILED_INFRASTRUCTURE,
                        system_outcome=SystemOutcome.UNKNOWN,
                        started_at=started,
                        finished_at=utc_now(),
                        provenance={
                            "backend_id": backend.backend_id,
                            "backend_version": backend.backend_version,
                        },
                        failure_reason=f"{type(exc).__name__}: {exc}",
                    )
                self.store.finish_attempt(result, attempt_number)
                if result.status not in {RunStatus.FAILED_INFRASTRUCTURE, RunStatus.INTERRUPTED}:
                    return
                state = self.store.run_states(campaign.campaign_id)[run.run_id]
                if state["infrastructure_failures"] > campaign.max_infrastructure_retries:
                    return

        self.store.set_campaign_status(campaign.campaign_id, "running")
        with ThreadPoolExecutor(max_workers=campaign.max_parallel) as pool:
            futures = [pool.submit(execute, run) for run in candidates]
            for future in as_completed(futures):
                future.result()

        states = self.store.run_states(campaign.campaign_id)
        values = [state["status"] for state in states.values()]
        if any(value in {"planned", "queued", "running"} for value in values):
            campaign_status = "paused"
        elif any(value in {"failed_infrastructure", "interrupted"} for value in values):
            campaign_status = "failed"
        elif any(value == "failed_system" for value in values):
            campaign_status = "completed_with_system_failures"
        else:
            campaign_status = "completed"
        self.store.set_campaign_status(campaign.campaign_id, campaign_status)
        return self.store.results(campaign.campaign_id)

    @staticmethod
    def _validate_result(
        result: RunResult,
        run: RunSpec,
        backend: ExperimentBackend,
        started: datetime,
    ) -> RunResult:
        if result.run_id != run.run_id:
            raise ValueError(f"backend returned run_id {result.run_id!r} for {run.run_id!r}")
        if not isinstance(result.status, RunStatus):
            raise ValueError("backend returned an invalid run status")
        if not isinstance(result.system_outcome, SystemOutcome):
            raise ValueError("backend returned an invalid system outcome")
        if result.status in {RunStatus.PLANNED, RunStatus.QUEUED, RunStatus.RUNNING}:
            raise ValueError("backend returned a non-terminal run status")
        seen: set[str] = set()
        for metric in result.metrics:
            validate_metric_value(metric)
            if metric.metric_id in seen:
                raise ValueError(f"duplicate metric_id {metric.metric_id!r}")
            seen.add(metric.metric_id)
            canonical_json(metric)
        canonical_json(result.provenance)
        for artifact in result.artifacts:
            if artifact.size_bytes is not None and artifact.size_bytes < 0:
                raise ValueError("artifact size_bytes cannot be negative")
        return replace(
            result,
            started_at=result.started_at or started,
            finished_at=result.finished_at or utc_now(),
            provenance={
                **dict(result.provenance),
                "backend_id": backend.backend_id,
                "backend_version": backend.backend_version,
            },
        )
