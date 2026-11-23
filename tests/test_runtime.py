from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from simops.analysis import analyze_campaign, wilson_interval
from simops.backends import ExecutionContext
from simops.contracts import RunResult, RunSpec, RunStatus
from simops.demo import DemoNavigationBackend
from simops.manifest import load_campaign_manifest
from simops.paths import path_component
from simops.planner import (
    CampaignMatrix,
    ConfigurationDefinition,
    ScenarioDefinition,
    plan_campaign,
)
from simops.reports import write_report
from simops.runner import CampaignRunner
from simops.store import CampaignConflictError, FilesystemArtifactStore, SQLiteCampaignStore
from simops.tuning import _aggregate_constraint, load_tuning_manifest, run_tuning


class CountingBackend:
    backend_id = "counting"
    backend_version = "1"
    thread_safe = True

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()
        self.delegate = DemoNavigationBackend()

    def validate(self, run: RunSpec):
        return self.delegate.validate(run)

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        with self._lock:
            self.calls += 1
        return self.delegate.execute(run, context)


class FailOnceBackend(CountingBackend):
    backend_id = "fail-once"

    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        with self._lock:
            self.calls += 1
        if self.fail:
            self.fail = False
            raise OSError("temporary simulator startup failure")
        return self.delegate.execute(run, context)


class BlockingBackend(CountingBackend):
    backend_id = "blocking"

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test backend was not released")
        return super().execute(run, context)


def campaign(campaign_id: str = "runtime-test", *, retries: int = 0, parallel: int = 2):
    return plan_campaign(
        CampaignMatrix(
            campaign_id=campaign_id,
            title="Runtime test",
            systems=("demo-robot",),
            scenarios=(ScenarioDefinition("open", {"difficulty": 0.1}),),
            configurations=(
                ConfigurationDefinition("baseline", {"max_speed_mps": 0.4}),
            ),
            repetitions=4,
            seeds=(11, 22, 33, 44),
            max_parallel=parallel,
            max_infrastructure_retries=retries,
        )
    )


class RuntimeTests(unittest.TestCase):
    def test_manifest_to_store_to_report_and_resume_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "campaign.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1.0",
                        "backend": "demo",
                        "campaign": {
                            "campaign_id": "end-to-end",
                            "title": "End-to-end",
                            "systems": ["robot"],
                            "scenarios": [{"scenario_id": "open", "parameters": {"difficulty": 0.1}}],
                            "configurations": [
                                {"configuration_id": "baseline", "values": {"max_speed_mps": 0.4}}
                            ],
                            "repetitions": 3,
                            "seeds": [1, 2, 3],
                            "max_parallel": 2,
                        },
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_campaign_manifest(manifest_path)
            backend = CountingBackend()
            # The test backend's identity differs from the manifest's demo ID only at the store layer.
            store = SQLiteCampaignStore(root / "store.sqlite3")
            runner = CampaignRunner(store)
            results = runner.run_campaign(loaded.campaign, backend)
            self.assertEqual(len(results), 3)
            self.assertEqual(backend.calls, 3)
            self.assertEqual(set(next(iter(store.run_states("end-to-end").values()))), {
                "status", "attempt_count", "infrastructure_failures"
            })
            runner.run_campaign(loaded.campaign, backend)
            self.assertEqual(backend.calls, 3)
            self.assertEqual(len(store.events("end-to-end")), 11)

            stored = store.get_campaign("end-to-end")
            model = analyze_campaign(
                stored["campaign"], results,
                backend_id=stored["backend_id"],
                backend_version=stored["backend_version"],
            )
            output = root / "reports"
            json_path, markdown_path, html_path = write_report(model, output)
            self.assertEqual(json.loads(json_path.read_text())["campaign"]["planned_runs"], 3)
            self.assertIn("Wilson 95%", markdown_path.read_text())
            self.assertIn("<html", html_path.read_text())

    def test_infrastructure_failure_is_retried_and_kept_in_attempt_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = campaign("retry-test", retries=1, parallel=1)
            store = SQLiteCampaignStore(Path(temporary) / "store.sqlite3")
            backend = FailOnceBackend()
            results = CampaignRunner(store).run_campaign(spec, backend)
            self.assertEqual(len(results), 4)
            self.assertEqual(backend.calls, 5)
            first_run_events = [event for event in store.events("retry-test") if event["event_type"] == "run_started"]
            self.assertEqual(len(first_run_events), 5)
            self.assertEqual(sum(result.status is RunStatus.COMPLETED for result in results), 4)

    def test_interrupted_attempt_is_marked_then_resumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = campaign("recover-test", retries=1, parallel=1)
            store = SQLiteCampaignStore(Path(temporary) / "store.sqlite3")
            backend = CountingBackend()
            store.register_campaign(spec, backend.backend_id, backend.backend_version)
            store.start_attempt(spec.runs[0])
            self.assertEqual(store.recover_interrupted(spec.campaign_id), 1)
            self.assertEqual(
                store.run_states(spec.campaign_id)[spec.runs[0].run_id]["status"],
                "interrupted",
            )
            results = CampaignRunner(store).run_campaign(spec, backend)
            self.assertEqual(len(results), 4)
            self.assertEqual(backend.calls, 4)
            self.assertEqual(
                store.run_states(spec.campaign_id)[spec.runs[0].run_id]["attempt_count"], 2
            )

    def test_concurrent_local_coordinators_serialize_by_campaign(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = campaign("coordinator-lock", parallel=1)
            backend = BlockingBackend()
            runners = (
                CampaignRunner(SQLiteCampaignStore(root / "store.sqlite3")),
                CampaignRunner(SQLiteCampaignStore(root / "store.sqlite3")),
            )
            results = []
            errors = []
            second_started = threading.Event()
            second_done = threading.Event()

            def run(index: int) -> None:
                try:
                    if index == 1:
                        second_started.set()
                    results.append(runners[index].run_campaign(spec, backend))
                except Exception as exc:  # captured so thread failures fail this test
                    errors.append(exc)
                finally:
                    if index == 1:
                        second_done.set()

            first = threading.Thread(target=run, args=(0,))
            second = threading.Thread(target=run, args=(1,))
            first.start()
            self.assertTrue(backend.started.wait(timeout=2))
            second.start()
            self.assertTrue(second_started.wait(timeout=1))
            self.assertFalse(second_done.wait(timeout=0.1))
            backend.release.set()
            first.join(timeout=3)
            second.join(timeout=3)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(backend.calls, 4)
            self.assertTrue(
                all(state["attempt_count"] == 1 for state in runners[0].store.run_states(spec.campaign_id).values())
            )

    def test_campaign_id_cannot_resume_with_different_backend_or_spec(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = SQLiteCampaignStore(Path(temporary) / "store.sqlite3")
            spec = campaign("conflict-test")
            store.register_campaign(spec, "backend-a", "1")
            with self.assertRaises(CampaignConflictError):
                store.register_campaign(spec, "backend-a", "2")

    def test_artifact_store_checks_content_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = FilesystemArtifactStore(temporary)
            reference = artifacts.put("trace.json", b"{\"x\": 1}", "application/json", "1")
            self.assertEqual(artifacts.get(reference), b"{\"x\": 1}")
            path = Path(temporary) / reference.sha256[:2] / reference.sha256
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                artifacts.get(reference)

    def test_wilson_interval_and_no_outcome_case(self):
        interval = wilson_interval(5, 5)
        self.assertIsNotNone(interval)
        self.assertLess(interval[0], 1.0)
        self.assertIsNone(wilson_interval(0, 0))

    def test_worst_case_constraints_reject_single_run_failure_even_when_mean_passes(self):
        self.assertEqual(sum([0, 0, 0, 1]) / 4, 0.25)
        self.assertEqual(_aggregate_constraint([0, 0, 0, 1], "worst_case", "<="), 1)
        self.assertEqual(_aggregate_constraint([1, 1, 1, 0], "worst_case", ">="), 0)
        self.assertEqual(_aggregate_constraint([0, 0, 0, 1], "mean", "<="), 0.25)

    def test_lhs_tuning_runs_and_persists_real_candidate_campaigns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = load_tuning_manifest(Path("examples/demo-tuning.json"))
            store = SQLiteCampaignStore(root / "store.sqlite3")
            result = run_tuning(
                manifest,
                DemoNavigationBackend(),
                CampaignRunner(store),
                result_directory=root / "tuning-results",
                default_storage_path=root / "optuna.sqlite3",
            )
            self.assertEqual(result.strategy_id, "latin-hypercube-v1")
            self.assertEqual(len(result.candidates), manifest.budget)
            tuning_output = root / "tuning-results" / path_component(manifest.tuning_id)
            self.assertTrue((tuning_output / "tuning.json").exists())
            self.assertTrue((tuning_output / "tuning.md").exists())
            for candidate in result.candidates:
                campaign_id = candidate.metadata.get("campaign_id")
                self.assertIsInstance(campaign_id, str)
                self.assertEqual(len(store.results(campaign_id)), 8)

    def test_tpe_plugin_reports_missing_optional_dependency(self):
        try:
            import optuna  # noqa: F401
        except ImportError:
            from simops.optuna_tpe import OptunaTPESearch

            spec = load_tuning_manifest(Path("examples/demo-tuning.json")).tuning_spec
            with self.assertRaisesRegex(RuntimeError, "optional"):
                OptunaTPESearch().optimize(spec, lambda _params: None, budget=1)

    def test_tpe_runs_constrained_multiobjective_study_and_resumes(self):
        try:
            import optuna  # noqa: F401
        except ImportError:
            self.skipTest("Optuna optional dependency is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = load_tuning_manifest(Path("examples/demo-tuning.json"))
            spec = replace(source.tuning_spec, n_startup_trials=2)
            manifest = replace(source, strategy_id="tpe", budget=3, tuning_spec=spec)
            store = SQLiteCampaignStore(root / "store.sqlite3")
            runner = CampaignRunner(store)
            first = run_tuning(
                manifest,
                DemoNavigationBackend(),
                runner,
                result_directory=root / "results",
                default_storage_path=root / "optuna.sqlite3",
            )
            second = run_tuning(
                manifest,
                DemoNavigationBackend(),
                runner,
                result_directory=root / "results",
                default_storage_path=root / "optuna.sqlite3",
            )
            self.assertEqual(len(first.candidates), 3)
            self.assertEqual(len(second.candidates), 6)
            self.assertTrue(all(candidate.state == "complete" for candidate in second.candidates))


if __name__ == "__main__":
    unittest.main()
