"""Command-line interface for validating and operating local campaigns."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from threading import Event

from .analysis import analyze_campaign
from .backends import available_backends, load_backend
from .manifest import load_campaign_manifest
from .paths import path_component
from .reports import write_report
from .robot_profile import load_robot_profile
from .runner import CampaignRunner
from .serialization import pretty_json, to_json_value
from .store import SQLiteCampaignStore
from .tuning import load_tuning_manifest, run_tuning

DEFAULT_STORE = Path(".simops/campaigns.sqlite3")


def _add_store_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE, help="SQLite campaign journal")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simops",
        description="Plan, execute, resume and report reproducible experiment campaigns.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="validate a robot capability profile")
    profile_sub = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_validate = profile_sub.add_parser("validate", help="check robot geometry, limits, and signal contract")
    profile_validate.add_argument("path", type=Path)
    profile_validate.set_defaults(handler=_cmd_profile_validate)

    backends_parser = subparsers.add_parser("backends", help="list installed backend adapters")
    backends_parser.set_defaults(handler=_cmd_backends)

    validate_parser = subparsers.add_parser("validate", help="validate a campaign before running it")
    validate_parser.add_argument("manifest", type=Path)
    validate_parser.set_defaults(handler=_cmd_validate)

    plan_parser = subparsers.add_parser("plan", help="show the resolved campaign matrix")
    plan_parser.add_argument("manifest", type=Path)
    plan_parser.add_argument("--json", action="store_true", dest="as_json")
    plan_parser.set_defaults(handler=_cmd_plan)

    run_parser = subparsers.add_parser("run", help="run or resume unfinished campaign runs")
    run_parser.add_argument("manifest", type=Path)
    _add_store_argument(run_parser)
    run_parser.add_argument("--report-dir", type=Path, default=Path(".simops/reports"))
    run_parser.set_defaults(handler=_cmd_run)

    resume_parser = subparsers.add_parser("resume", help="resume unfinished work from the local journal")
    resume_parser.add_argument("campaign_id")
    _add_store_argument(resume_parser)
    resume_parser.add_argument("--report-dir", type=Path, default=Path(".simops/reports"))
    resume_parser.set_defaults(handler=_cmd_resume)

    status_parser = subparsers.add_parser("status", help="inspect campaign, run and attempt states")
    status_parser.add_argument("campaign_id")
    _add_store_argument(status_parser)
    status_parser.set_defaults(handler=_cmd_status)

    report_parser = subparsers.add_parser("report", help="render JSON, Markdown and HTML reports")
    report_parser.add_argument("campaign_id")
    _add_store_argument(report_parser)
    report_parser.add_argument("--report-dir", type=Path, default=Path(".simops/reports"))
    report_parser.set_defaults(handler=_cmd_report)

    tune_parser = subparsers.add_parser("tune", help="optimize parameters by running stored campaigns")
    tune_parser.add_argument("manifest", type=Path)
    _add_store_argument(tune_parser)
    tune_parser.add_argument("--result-dir", type=Path, default=Path(".simops/tunings"))
    tune_parser.set_defaults(handler=_cmd_tune)

    mcp_parser = subparsers.add_parser("mcp", help="serve this workspace over local MCP stdio")
    mcp_parser.add_argument("--workspace", type=Path, default=Path("."))
    mcp_parser.add_argument(
        "--allow-backend",
        action="append",
        dest="allowed_backends",
        help="allow an installed adapter (repeatable); default is demo only",
    )
    mcp_parser.set_defaults(handler=_cmd_mcp)
    return parser


def _store(path: Path) -> SQLiteCampaignStore:
    return SQLiteCampaignStore(path)


def _loaded(path: Path):
    loaded = load_campaign_manifest(path)
    backend = load_backend(loaded.backend_id)
    CampaignRunner.validate(loaded.campaign, backend)
    return loaded, backend


def _cmd_profile_validate(args: argparse.Namespace) -> int:
    profile = load_robot_profile(args.path)
    print(f"Valid robot profile: {profile.profile_id} ({profile.name})")
    print(f"Footprint radius: {profile.footprint_radius_m:g} m")
    print(f"Motion envelope: {profile.max_linear_speed_mps:g} m/s, {profile.max_angular_speed_radps:g} rad/s")
    print(f"Sensors declared: {len(profile.sensors)}; reference topics: {len(profile.reference_topics)}")
    return 0


def _cmd_backends(_args: argparse.Namespace) -> int:
    for name in available_backends():
        print(name)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    loaded, backend = _loaded(args.manifest)
    print(
        f"Valid: {len(loaded.campaign.runs)} runs, backend "
        f"{backend.backend_id}@{backend.backend_version}"
    )
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    loaded = load_campaign_manifest(args.manifest)
    campaign = loaded.campaign
    if args.as_json:
        print(
            pretty_json(
                {
                    "backend_id": loaded.backend_id,
                    "campaign": to_json_value(campaign),
                }
            ),
            end="",
        )
        return 0
    print(f"Campaign: {campaign.title} ({campaign.campaign_id})")
    print(f"Backend: {loaded.backend_id}")
    print(f"Runs: {len(campaign.runs)}")
    print(f"Concurrency: {campaign.max_parallel}; infrastructure retries: {campaign.max_infrastructure_retries}")
    for run in campaign.runs:
        print(
            f"{run.run_id}  system={run.system_id}  scenario={run.scenario_id}  "
            f"configuration={run.configuration_id}  repetition={run.repetition}  seed={run.seed}"
        )
    return 0


def _run_with_signal_handling(runner: CampaignRunner, campaign, backend):
    cancel_event = Event()
    previous = signal.getsignal(signal.SIGINT)

    def request_cancel(_signum, _frame):
        cancel_event.set()

    signal.signal(signal.SIGINT, request_cancel)
    try:
        return runner.run_campaign(campaign, backend, cancel_event=cancel_event)
    finally:
        signal.signal(signal.SIGINT, previous)


def _write_campaign_report(store: SQLiteCampaignStore, campaign_id: str, report_dir: Path) -> None:
    stored = store.get_campaign(campaign_id)
    if stored is None:
        raise ValueError(f"campaign {campaign_id!r} is not in the store")
    model = analyze_campaign(
        stored["campaign"],
        store.results(campaign_id),
        backend_id=stored["backend_id"],
        backend_version=stored["backend_version"],
    )
    paths = write_report(model, report_dir / path_component(campaign_id))
    for path in paths:
        print(path)


def _cmd_run(args: argparse.Namespace) -> int:
    loaded, backend = _loaded(args.manifest)
    store = _store(args.store)
    runner = CampaignRunner(store)
    results = _run_with_signal_handling(runner, loaded.campaign, backend)
    _write_campaign_report(store, loaded.campaign.campaign_id, args.report_dir)
    states = store.run_states(loaded.campaign.campaign_id)
    print(f"Saved {len(results)} run results; states: {json.dumps(_state_counts(states), sort_keys=True)}")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    store = _store(args.store)
    stored = store.get_campaign(args.campaign_id)
    if stored is None:
        raise ValueError(f"campaign {args.campaign_id!r} is not in the store")
    backend = load_backend(stored["backend_id"])
    if backend.backend_version != stored["backend_version"]:
        raise ValueError(
            f"stored backend version {stored['backend_version']!r} differs from installed "
            f"version {backend.backend_version!r}; use a new campaign_id"
        )
    runner = CampaignRunner(store)
    results = _run_with_signal_handling(runner, stored["campaign"], backend)
    _write_campaign_report(store, args.campaign_id, args.report_dir)
    print(f"Saved {len(results)} run results; states: {json.dumps(_state_counts(store.run_states(args.campaign_id)), sort_keys=True)}")
    return 0


def _state_counts(states: dict[str, dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for state in states.values():
        status = str(state["status"])
        counts[status] = counts.get(status, 0) + 1
    return counts


def _cmd_status(args: argparse.Namespace) -> int:
    store = _store(args.store)
    campaign = store.get_campaign(args.campaign_id)
    if campaign is None:
        raise ValueError(f"campaign {args.campaign_id!r} is not in the store")
    states = store.run_states(args.campaign_id)
    events = store.events(args.campaign_id)
    print(
        pretty_json(
            {
                "campaign_id": args.campaign_id,
                "title": campaign["title"],
                "backend_id": campaign["backend_id"],
                "backend_version": campaign["backend_version"],
                "status": campaign["status"],
                "fingerprint": campaign["fingerprint"],
                "run_states": states,
                "event_count": len(events),
                "last_event": events[-1] if events else None,
            }
        ),
        end="",
    )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    _write_campaign_report(_store(args.store), args.campaign_id, args.report_dir)
    return 0


def _cmd_tune(args: argparse.Namespace) -> int:
    manifest = load_tuning_manifest(args.manifest)
    backend = load_backend(manifest.backend_id)
    store = _store(args.store)
    runner = CampaignRunner(store)
    default_tpe_db = args.store.parent / "optuna" / f"{path_component(manifest.tuning_id)}.sqlite3"
    result = run_tuning(
        manifest,
        backend,
        runner,
        result_directory=args.result_dir,
        default_storage_path=default_tpe_db,
    )
    output = args.result_dir / path_component(manifest.tuning_id)
    print(f"Strategy: {result.strategy_id}; candidates recorded: {len(result.candidates)}")
    print(f"Feasible Pareto candidates: {len(result.pareto_front)}")
    print(output / "tuning.json")
    print(output / "tuning.md")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import create_mcp_server

    server = create_mcp_server(
        args.workspace,
        allowed_backends=set(args.allowed_backends) if args.allowed_backends else {"demo"},
    )
    server.run(transport="stdio")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"simops: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
