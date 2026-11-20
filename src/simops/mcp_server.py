"""Local MCP server exposing bounded campaign operations over the application API."""

from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .analysis import analyze_campaign
from .backends import available_backends, load_backend
from .manifest import load_campaign_manifest
from .paths import path_component
from .planner import CampaignMatrix, ConfigurationDefinition, ScenarioDefinition, plan_campaign
from .reports import write_report
from .runner import CampaignRunner
from .serialization import pretty_json, to_json_value
from .store import SQLiteCampaignStore
from .tuning import load_tuning_manifest, run_tuning


class WorkspacePolicy:
    def __init__(
        self,
        *,
        allowed_backends: set[str],
        max_runs_per_campaign: int = 500,
        max_parallel: int = 8,
        max_wall_time_s: float = 3600.0,
        max_tuning_candidates: int = 50,
        max_total_tuning_runs: int = 5000,
    ) -> None:
        self.allowed_backends = allowed_backends
        self.max_runs_per_campaign = max_runs_per_campaign
        self.max_parallel = max_parallel
        self.max_wall_time_s = max_wall_time_s
        self.max_tuning_candidates = max_tuning_candidates
        self.max_total_tuning_runs = max_total_tuning_runs


class MCPController:
    """Bind a local workspace to typed MCP tools; no filesystem or shell tool is exposed."""

    def __init__(self, workspace: str | Path, policy: WorkspacePolicy) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.manifest_root = self.workspace / "manifests"
        self.manifest_root.mkdir(parents=True, exist_ok=True)
        self.state_root = self.workspace / ".simops"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.state_root / "campaigns.sqlite3"
        self.report_root = self.state_root / "reports"
        self.tuning_root = self.state_root / "tunings"
        self.policy = policy
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="simops-mcp")
        self._jobs: dict[tuple[str, str], tuple[Future[Any], threading.Event]] = {}

    def manifest_path(self, name: str) -> Path:
        if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("manifest_name must be a file name inside the configured manifests directory")
        if not name.endswith(".json"):
            raise ValueError("manifest_name must end in .json")
        path = self.manifest_root / name
        if path.is_symlink():
            raise ValueError("manifest symlinks are not accepted")
        resolved = path.resolve(strict=True)
        if resolved.parent != self.manifest_root.resolve() or not resolved.is_file():
            raise ValueError("manifest must be a regular file directly inside the configured workspace")
        return resolved

    def validate_campaign(self, manifest_name: str) -> dict[str, Any]:
        loaded = load_campaign_manifest(self.manifest_path(manifest_name))
        backend = self._backend(loaded.backend_id)
        CampaignRunner.validate(loaded.campaign, backend)
        self._check_campaign_policy(loaded.backend_id, loaded.campaign)
        return {
            "valid": True,
            "campaign_id": loaded.campaign.campaign_id,
            "backend_id": backend.backend_id,
            "backend_version": backend.backend_version,
            "planned_runs": len(loaded.campaign.runs),
        }

    def plan_campaign(self, manifest_name: str) -> dict[str, Any]:
        loaded = load_campaign_manifest(self.manifest_path(manifest_name))
        self._backend(loaded.backend_id)
        self._check_campaign_policy(loaded.backend_id, loaded.campaign)
        return {
            "campaign_id": loaded.campaign.campaign_id,
            "title": loaded.campaign.title,
            "backend_id": loaded.backend_id,
            "planned_runs": len(loaded.campaign.runs),
            "runs": [to_json_value(item) for item in loaded.campaign.runs],
        }

    def start_campaign(self, manifest_name: str) -> dict[str, Any]:
        loaded = load_campaign_manifest(self.manifest_path(manifest_name))
        backend = self._backend(loaded.backend_id)
        CampaignRunner.validate(loaded.campaign, backend)
        self._check_campaign_policy(loaded.backend_id, loaded.campaign)
        SQLiteCampaignStore(self.store_path).register_campaign(
            loaded.campaign, backend.backend_id, backend.backend_version
        )
        return self._start_job(
            "campaign",
            loaded.campaign.campaign_id,
            lambda event: self._execute_campaign(loaded.campaign, backend, event),
        )

    def resume_campaign(self, campaign_id: str) -> dict[str, Any]:
        store = SQLiteCampaignStore(self.store_path)
        stored = store.get_campaign(campaign_id)
        if stored is None:
            raise ValueError(f"campaign {campaign_id!r} is unknown in this workspace")
        backend = self._backend(stored["backend_id"])
        if backend.backend_version != stored["backend_version"]:
            raise ValueError("backend version changed since this campaign was registered")
        self._check_campaign_policy(stored["backend_id"], stored["campaign"])
        return self._start_job(
            "campaign",
            campaign_id,
            lambda event: self._execute_campaign(stored["campaign"], backend, event),
        )

    def campaign_status(self, campaign_id: str) -> dict[str, Any]:
        store = SQLiteCampaignStore(self.store_path)
        campaign = store.get_campaign(campaign_id)
        if campaign is None:
            raise ValueError(f"campaign {campaign_id!r} is unknown in this workspace")
        states = store.run_states(campaign_id)
        events = store.events(campaign_id)
        with self._lock:
            active = self._jobs.get(("campaign", campaign_id))
        return {
            "campaign_id": campaign_id,
            "status": campaign["status"],
            "backend_id": campaign["backend_id"],
            "backend_version": campaign["backend_version"],
            "run_states": states,
            "active_in_process": bool(active and not active[0].done()),
            "last_event": events[-1] if events else None,
        }

    def cancel_campaign(self, campaign_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._jobs.get(("campaign", campaign_id))
        if item is None or item[0].done():
            return {"campaign_id": campaign_id, "accepted": False, "reason": "no active campaign job"}
        item[1].set()
        return {
            "campaign_id": campaign_id,
            "accepted": True,
            "message": "cooperative cancellation requested; active adapters must honor their context",
        }

    def render_report(self, campaign_id: str) -> dict[str, Any]:
        model = self.campaign_result(campaign_id)
        campaign = model["campaign"]
        paths = write_report(model, self.report_root / path_component(campaign_id))
        return {
            "campaign_id": campaign["campaign_id"],
            "files": [str(path.relative_to(self.workspace)) for path in paths],
        }

    def campaign_result(self, campaign_id: str) -> dict[str, Any]:
        store = SQLiteCampaignStore(self.store_path)
        campaign = store.get_campaign(campaign_id)
        if campaign is None:
            raise ValueError(f"campaign {campaign_id!r} is unknown in this workspace")
        return analyze_campaign(
            campaign["campaign"],
            store.results(campaign_id),
            backend_id=campaign["backend_id"],
            backend_version=campaign["backend_version"],
        )

    def validate_tuning(self, manifest_name: str) -> dict[str, Any]:
        manifest = load_tuning_manifest(self.manifest_path(manifest_name), profile_root=self.workspace)
        backend = self._backend(manifest.backend_id)
        self._check_tuning_policy(manifest)
        template = manifest.campaign_template
        values = dict(manifest.base_configuration)
        configurations = {"base": values}
        for parameter in manifest.parameters:
            candidates = parameter.choices if parameter.kind.value == "categorical" else (parameter.lower, parameter.upper)
            for index, value in enumerate(candidates):
                if value is None:
                    continue
                resolved = dict(values)
                resolved[parameter.name] = value
                configurations[f"{parameter.name}-{index}"] = resolved
        matrix = CampaignMatrix(
            campaign_id=f"validate-{path_component(manifest.tuning_id)}",
            title=f"Validate tuning: {manifest.title}",
            systems=tuple(template["systems"]),
            scenarios=tuple(ScenarioDefinition(item["scenario_id"], item.get("parameters", {})) for item in template["scenarios"]),
            configurations=tuple(ConfigurationDefinition(name, config) for name, config in configurations.items()),
            repetitions=template["repetitions"],
            seeds=tuple(template.get("seeds", [])),
            max_parallel=template.get("max_parallel", 1),
            max_infrastructure_retries=template.get("max_infrastructure_retries", 0),
            wall_time_budget_s=template.get("wall_time_budget_s"),
            metadata=template.get("metadata", {}),
        )
        campaign = plan_campaign(matrix)
        CampaignRunner.validate(campaign, backend)
        return {
            "valid": True,
            "tuning_id": manifest.tuning_id,
            "title": manifest.title,
            "backend_id": backend.backend_id,
            "backend_version": backend.backend_version,
            "strategy_id": manifest.strategy_id,
            "candidate_budget": manifest.budget,
            "runs_per_candidate": len(template["systems"]) * len(template["scenarios"]) * template["repetitions"],
            "total_planned_runs": manifest.budget * len(template["systems"]) * len(template["scenarios"]) * template["repetitions"],
            "parameters": [to_json_value(item) for item in manifest.parameters],
            "objectives": [
                {"metric_id": item.metric_id, "direction": item.direction.value, "aggregation": manifest.objective_aggregations[item.metric_id]}
                for item in manifest.objectives
            ],
            "constraints": list(manifest.constraints),
            "scenarios": [item["scenario_id"] for item in template["scenarios"]],
            "repetitions": template["repetitions"],
            "robot_profile": to_json_value(manifest.robot_profile) if manifest.robot_profile else None,
            "validation_scope": "base configuration plus one-at-a-time parameter bounds/choices; cross-parameter combinations are checked during each actual candidate run",
        }

    def start_tuning(self, manifest_name: str) -> dict[str, Any]:
        manifest = load_tuning_manifest(self.manifest_path(manifest_name), profile_root=self.workspace)
        backend = self._backend(manifest.backend_id)
        self._check_tuning_policy(manifest)
        key = manifest.tuning_id
        return self._start_job(
            "tuning",
            key,
            lambda _event: self._execute_tuning(manifest, backend),
        )

    def tuning_result(self, tuning_id: str) -> dict[str, Any]:
        path = self.tuning_root / path_component(tuning_id) / "tuning.json"
        if not path.is_file():
            with self._lock:
                job = self._jobs.get(("tuning", tuning_id))
            if job and job[0].done():
                error = job[0].exception()
                if error is not None:
                    return {"tuning_id": tuning_id, "status": "failed", "reason": str(error)}
            return {
                "tuning_id": tuning_id,
                "status": "running" if job and not job[0].done() else "not_found",
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def _backend(self, backend_id: str):
        if backend_id not in self.policy.allowed_backends:
            raise ValueError(f"backend {backend_id!r} is blocked by the MCP workspace policy")
        backend = load_backend(backend_id)
        return backend

    def _check_campaign_policy(self, backend_id: str, campaign) -> None:
        if backend_id not in self.policy.allowed_backends:
            raise ValueError(f"backend {backend_id!r} is blocked by the MCP workspace policy")
        if len(campaign.runs) > self.policy.max_runs_per_campaign:
            raise ValueError("campaign exceeds the workspace run-count limit")
        if campaign.max_parallel > self.policy.max_parallel:
            raise ValueError("campaign exceeds the workspace concurrency limit")
        if campaign.wall_time_budget_s is not None and campaign.wall_time_budget_s > self.policy.max_wall_time_s:
            raise ValueError("campaign exceeds the workspace wall-time limit")

    def _check_tuning_policy(self, manifest) -> None:
        if manifest.backend_id not in self.policy.allowed_backends:
            raise ValueError(f"backend {manifest.backend_id!r} is blocked by the MCP workspace policy")
        template = manifest.campaign_template
        runs_per_candidate = (
            len(template["systems"])
            * len(template["scenarios"])
            * template["repetitions"]
        )
        if manifest.budget > self.policy.max_tuning_candidates:
            raise ValueError("tuning budget exceeds the workspace candidate limit")
        if manifest.budget * runs_per_candidate > self.policy.max_total_tuning_runs:
            raise ValueError("tuning budget multiplied by campaign size exceeds the workspace quota")
        if template.get("max_parallel", 1) > self.policy.max_parallel:
            raise ValueError("tuning campaign exceeds the workspace concurrency limit")
        if manifest.tuning_spec.workers * template.get("max_parallel", 1) > self.policy.max_parallel:
            raise ValueError("tuning workers multiplied by campaign concurrency exceed the workspace limit")
        if (
            template.get("wall_time_budget_s") is not None
            and template["wall_time_budget_s"] > self.policy.max_wall_time_s
        ):
            raise ValueError("tuning campaign exceeds the workspace wall-time limit")

    def _start_job(self, kind: str, identifier: str, target) -> dict[str, Any]:
        key = (kind, identifier)
        with self._lock:
            current = self._jobs.get(key)
            if current is not None and not current[0].done():
                return {"id": identifier, "kind": kind, "started": False, "status": "already_running"}
            cancellation = threading.Event()
            future = self._executor.submit(target, cancellation)
            self._jobs[key] = (future, cancellation)
        return {"id": identifier, "kind": kind, "started": True, "status": "running"}

    def _execute_campaign(self, campaign, backend, cancel_event) -> dict[str, Any]:
        store = SQLiteCampaignStore(self.store_path)
        runner = CampaignRunner(store)
        results = runner.run_campaign(campaign, backend, cancel_event=cancel_event)
        return {"campaign_id": campaign.campaign_id, "result_count": len(results)}

    def _execute_tuning(self, manifest, backend):
        runner = CampaignRunner(SQLiteCampaignStore(self.store_path))
        default_storage = self.state_root / "optuna" / f"{path_component(manifest.tuning_id)}.sqlite3"
        return run_tuning(
            manifest,
            backend,
            runner,
            result_directory=self.tuning_root,
            default_storage_path=default_storage,
        )


def create_mcp_server(workspace: str | Path, allowed_backends: set[str] | None = None):
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError as exc:
        raise RuntimeError("install SimOps with the 'mcp' extra to start the MCP server") from exc

    policy = WorkspacePolicy(
        allowed_backends=allowed_backends if allowed_backends is not None else {"demo"}
    )
    controller = MCPController(workspace, policy)
    server = MCPServer("SimOps Lab")

    async def invoke(controller_call):
        try:
            return controller_call()
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def list_backends() -> list[str]:
        """List adapters that the workspace policy allows this agent to use."""
        return sorted(set(available_backends()) & policy.allowed_backends)

    @server.tool()
    async def list_manifests() -> list[str]:
        """List JSON campaign and tuning manifests in the configured workspace."""
        return sorted(path.name for path in controller.manifest_root.glob("*.json") if not path.is_symlink())

    @server.tool()
    async def validate_campaign(manifest_name: str) -> dict[str, Any]:
        """Validate a named campaign manifest without starting any simulation."""
        return await invoke(lambda: controller.validate_campaign(manifest_name))

    @server.tool()
    async def plan_campaign(manifest_name: str) -> dict[str, Any]:
        """Expand a named campaign manifest into its planned runs."""
        return await invoke(lambda: controller.plan_campaign(manifest_name))

    @server.tool()
    async def start_campaign(manifest_name: str) -> dict[str, Any]:
        """Start a validated campaign in the background using an allowed adapter."""
        return await invoke(lambda: controller.start_campaign(manifest_name))

    @server.tool()
    async def resume_campaign(campaign_id: str) -> dict[str, Any]:
        """Resume unfinished attempts from a campaign already recorded in this workspace."""
        return await invoke(lambda: controller.resume_campaign(campaign_id))

    @server.tool()
    async def get_campaign_status(campaign_id: str) -> dict[str, Any]:
        """Read current run states and recent campaign activity."""
        return await invoke(lambda: controller.campaign_status(campaign_id))

    @server.tool()
    async def get_campaign_result(campaign_id: str) -> dict[str, Any]:
        """Read structured campaign metrics and outcome summaries from the workspace."""
        return await invoke(lambda: controller.campaign_result(campaign_id))

    @server.tool()
    async def cancel_campaign(campaign_id: str) -> dict[str, Any]:
        """Request cooperative cancellation of the in-process campaign job."""
        return await invoke(lambda: controller.cancel_campaign(campaign_id))

    @server.tool()
    async def render_report(campaign_id: str) -> dict[str, Any]:
        """Generate JSON, Markdown and HTML reports for a stored campaign."""
        return await invoke(lambda: controller.render_report(campaign_id))

    @server.tool()
    async def validate_tuning(manifest_name: str) -> dict[str, Any]:
        """Validate a tuning manifest and return its budget, objectives, constraints and profile."""
        return await invoke(lambda: controller.validate_tuning(manifest_name))

    @server.tool()
    async def start_tuning(manifest_name: str) -> dict[str, Any]:
        """Start an LHS or TPE parameter search from a workspace tuning manifest."""
        return await invoke(lambda: controller.start_tuning(manifest_name))

    @server.tool()
    async def get_tuning_result(tuning_id: str) -> dict[str, Any]:
        """Read a finished optimization result, or report whether it is still running."""
        return await invoke(lambda: controller.tuning_result(tuning_id))

    return server
