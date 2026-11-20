"""Isolated, pinned Nav2/TurtleBot3 Docker demonstration backend."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .backends import ExecutionContext
from .contracts import (
    MetricState,
    MetricValue,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
)


BASE_IMAGE = (
    "ghcr.io/ros-navigation/nav2_docker:lyrical-1.5.3-standard"
    "@sha256:22d126afac99a8cf20600756b64196fcbe04fefabbe53851efa946377d83362c"
)
IMAGE = "simops-lab/nav2-turtlebot3:lyrical-1.5.3-gm1.3.46"
RUNNER = Path(__file__).with_name("nav2_docker_runner.py")


def _number(values: dict[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


class Nav2DockerBackend:
    """One headless Nav2 simulation per container; serialized for isolation."""

    backend_id = "nav2-docker"
    thread_safe = False

    def __init__(self) -> None:
        self.image_id: str | None = None
        if shutil.which("docker"):
            try:
                inspected = subprocess.run(
                    ["docker", "image", "inspect", "--format={{.Id}}", IMAGE],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if inspected.returncode == 0:
                    self.image_id = inspected.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
        identity = self.image_id.removeprefix("sha256:")[:12] if self.image_id else "unbuilt"
        self.backend_version = f"0.1.0+adapter0.1.0-nav2lyrical-{identity}"

    def validate(self, run: RunSpec) -> Sequence[str]:
        errors: list[str] = []
        configuration = dict(run.configuration)
        scenario = dict(run.scenario_parameters)
        allowed_configuration = {
            "controller.vx_max",
            "controller.wz_max",
            "controller.temperature",
            "costmap.inflation_radius_m",
        }
        unknown = sorted(set(configuration) - allowed_configuration)
        if unknown:
            errors.append(f"unsupported configuration field(s): {', '.join(unknown)}")
        ranges = {
            "controller.vx_max": (0.1, 0.8, 0.5),
            "controller.wz_max": (0.2, 2.5, 1.9),
            "controller.temperature": (0.05, 2.0, 0.3),
            "costmap.inflation_radius_m": (0.25, 1.0, 0.7),
        }
        for key, (minimum, maximum, default) in ranges.items():
            try:
                value = _number(configuration, key, default)
                if not minimum <= value <= maximum:
                    errors.append(f"configuration.{key} must be between {minimum} and {maximum}")
            except ValueError as exc:
                errors.append(f"configuration.{exc}")

        allowed_scenario = {
            "start_x", "start_y", "start_yaw", "goal_x", "goal_y", "goal_yaw", "timeout_s"
        }
        unknown_scenario = sorted(set(scenario) - allowed_scenario)
        if unknown_scenario:
            errors.append(f"unsupported scenario field(s): {', '.join(unknown_scenario)}")
        values: dict[str, float] = {}
        for key, default in {
            "start_x": -2.0,
            "start_y": -0.5,
            "start_yaw": 0.0,
            "goal_x": 0.0,
            "goal_y": -0.5,
            "goal_yaw": 0.0,
            "timeout_s": 120.0,
        }.items():
            try:
                values[key] = _number(scenario, key, default)
            except ValueError as exc:
                errors.append(f"scenario.{exc}")
        if values and "timeout_s" in values and not 10 <= values["timeout_s"] <= 600:
            errors.append("scenario.timeout_s must be between 10 and 600 seconds")
        if values and all(key in values for key in ("start_x", "start_y", "goal_x", "goal_y")):
            if math.hypot(values["goal_x"] - values["start_x"], values["goal_y"] - values["start_y"]) < 0.25:
                errors.append("start and goal must be at least 0.25 m apart")
        if shutil.which("docker") is None:
            errors.append("Docker CLI was not found on PATH")
        elif self.image_id is None:
            errors.append(
                f"demo image is not built; run: docker build -f examples/nav2-turtlebot3/Dockerfile "
                f"-t {IMAGE} ."
            )
        elif RUNNER.is_file() is False:
            errors.append(f"Nav2 helper script is missing: {RUNNER}")
        return tuple(errors)

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult:
        errors = self.validate(run)
        if errors:
            raise ValueError("; ".join(errors))

        started = datetime.now(UTC)
        started_monotonic = time.monotonic()
        configuration = dict(run.configuration)
        scenario = dict(run.scenario_parameters)
        context.workspace.mkdir(parents=True, exist_ok=True)
        parameter_path = context.workspace / "nav2_overrides.yaml"
        parameter_path.write_text(self._parameter_yaml(configuration), encoding="utf-8")
        output_path = context.workspace / "measurements.json"
        log_path = context.workspace / "nav2.log"
        container_name = "simops-" + "".join(ch for ch in run.run_id.lower() if ch.isalnum())[:40]
        command = [
            "docker", "run", "--rm", "--name", container_name,
            "--shm-size=1g", "--cpus=2",
            "--mount", f"type=bind,src={RUNNER.resolve()},dst=/simops_runner.py,readonly",
            "--mount", f"type=bind,src={context.workspace.resolve()},dst=/simops_work",
            IMAGE,
            "bash", "-lc",
            "source /opt/ros/lyrical/setup.bash && "
            "source /root/nav2_ws/install/setup.bash && python3 /simops_runner.py "
            "--params /simops_work/nav2_overrides.yaml "
            "--output /simops_work/measurements.json "
            "--start-x " + str(_number(scenario, "start_x", -2.0)) +
            " --start-y " + str(_number(scenario, "start_y", -0.5)) +
            " --start-yaw " + str(_number(scenario, "start_yaw", 0.0)) +
            " --goal-x " + str(_number(scenario, "goal_x", 0.0)) +
            " --goal-y " + str(_number(scenario, "goal_y", -0.5)) +
            " --goal-yaw " + str(_number(scenario, "goal_yaw", 0.0)) +
            " --timeout-s " + str(_number(scenario, "timeout_s", 120.0)) +
            " --vx-limit " + str(_number(configuration, "controller.vx_max", 0.5)) +
            " --wz-limit " + str(_number(configuration, "controller.wz_max", 1.9)),
        ]
        process: subprocess.Popen[str] | None = None
        stopped = False
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                while process.poll() is None:
                    if context.cancellation_requested or context.deadline_expired:
                        stopped = True
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                        break
                    time.sleep(0.2)
            if stopped:
                return RunResult(
                    run_id=run.run_id,
                    status=RunStatus.CANCELLED,
                    system_outcome=SystemOutcome.UNKNOWN,
                    artifacts=self._persist_workspace_artifacts(context, context.workspace),
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    failure_reason="campaign cancellation or wall-time budget expired",
                    provenance={"image": IMAGE, "image_id": self.image_id, "adapter": self.backend_id},
                )
            if process.returncode != 0:
                detail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise RuntimeError(f"Nav2 Docker run exited {process.returncode}: {detail}")
            raw = json.loads(output_path.read_text(encoding="utf-8"))
            artifacts = self._persist_workspace_artifacts(context, context.workspace)
            metrics = (
                MetricValue("task.success", raw["success"], "bool", MetricState.OBSERVED, "1"),
                MetricValue("task.duration_s", raw["duration_s"], "s", MetricState.OBSERVED, "1"),
                self._measured("navigation.path_length_m", raw["path_length_m"], "m"),
                self._measured("safety.min_laser_range_m", raw["min_laser_range_m"], "m"),
                self._measured("control.peak_linear_speed_mps", raw["peak_linear_speed_mps"], "m/s"),
                self._measured("control.peak_angular_speed_radps", raw["peak_angular_speed_radps"], "rad/s"),
                self._measured("telemetry.odom_samples", raw["odom_samples"], "count"),
                self._measured("mission.sim_duration_s", raw.get("sim_duration_s"), "s"),
                self._measured("navigation.route_efficiency_proxy", raw.get("route_efficiency"), "ratio"),
                self._measured("control.command_samples", raw.get("cmd_samples"), "count"),
                self._measured("control.command_rate_hz", raw.get("cmd_rate_hz"), "Hz"),
                self._measured("control.angular_sign_changes", raw.get("angular_sign_changes"), "count"),
                self._measured("control.spot_turn_samples", raw.get("spot_turn_samples"), "count"),
                self._measured("control.saturation_fraction", raw.get("command_saturation_fraction"), "ratio"),
                self._measured("control.rms_angular_acceleration_radps2", raw.get("rms_angular_accel_radps2"), "rad/s^2"),
                self._measured("control.stop_after_success_latency_s", raw.get("stop_after_success_latency_s"), "s"),
            )
            success = bool(raw["success"])
            return RunResult(
                run_id=run.run_id,
                status=RunStatus.COMPLETED,
                system_outcome=SystemOutcome.SUCCESS if success else SystemOutcome.FAILURE,
                metrics=metrics,
                artifacts=artifacts,
                started_at=started,
                finished_at=datetime.now(UTC),
                provenance={
                    "backend_id": self.backend_id,
                    "backend_version": self.backend_version,
                    "image": IMAGE,
                    "image_id": self.image_id,
                    "base_image": BASE_IMAGE,
                    "seed_applied": False,
                    "simulation_wall_s": time.monotonic() - started_monotonic,
                    "metric_source": "ROS2 NavigateToPose action, /clock, /odom, /scan, /cmd_vel",
                    "measurement_limitations": ["No independent ground truth or contact sensor in this demo; laser minimum is not footprint clearance."],
                },
                warnings=("This demo measures a fixed TB3 sandbox task; it does not replace scenario validation for a target robot.",),
            )
        except Exception as exc:
            try:
                artifacts = self._persist_workspace_artifacts(context, context.workspace)
            except OSError:
                artifacts = ()
            return RunResult(
                run_id=run.run_id,
                status=RunStatus.FAILED_INFRASTRUCTURE,
                system_outcome=SystemOutcome.UNKNOWN,
                artifacts=artifacts,
                started_at=started,
                finished_at=datetime.now(UTC),
                provenance={
                    "backend_id": self.backend_id,
                    "backend_version": self.backend_version,
                    "image": IMAGE,
                    "image_id": self.image_id,
                    "base_image": BASE_IMAGE,
                },
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            try:
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

    @staticmethod
    def _persist_workspace_artifacts(context: ExecutionContext, workspace: Path):
        files = (
            ("nav2.log", "text/plain", None),
            ("bringup.log", "text/plain", None),
            ("nav2_overrides.yaml", "text/yaml", None),
            ("nav2_params.yaml", "text/yaml", None),
            ("measurements.json", "application/json", "1.0"),
        )
        artifacts = []
        for name, media_type, schema_version in files:
            source = workspace / name
            if source.is_file():
                artifacts.append(
                    context.artifacts.put(
                        name,
                        source.read_bytes(),
                        media_type,
                        schema_version,
                    )
                )
        return tuple(artifacts)

    @staticmethod
    def _parameter_yaml(configuration: dict[str, object]) -> str:
        vx_max = _number(configuration, "controller.vx_max", 0.5)
        wz_max = _number(configuration, "controller.wz_max", 1.9)
        temperature = _number(configuration, "controller.temperature", 0.3)
        inflation = _number(configuration, "costmap.inflation_radius_m", 0.7)
        return (
            "controller_server:\n"
            "  ros__parameters:\n"
            "    FollowPath:\n"
            f"      vx_max: {vx_max:.6g}\n"
            f"      wz_max: {wz_max:.6g}\n"
            f"      temperature: {temperature:.6g}\n"
            "local_costmap:\n"
            "  local_costmap:\n"
            "    ros__parameters:\n"
            "      inflation_layer:\n"
            f"        inflation_radius: {inflation:.6g}\n"
            "global_costmap:\n"
            "  global_costmap:\n"
            "    ros__parameters:\n"
            "      inflation_layer:\n"
            f"        inflation_radius: {inflation:.6g}\n"
        )

    @staticmethod
    def _measured(metric_id: str, value: object, unit: str) -> MetricValue:
        if value is None:
            return MetricValue(
                metric_id,
                None,
                unit,
                MetricState.MISSING,
                "1",
                reason="the corresponding ROS topic did not produce samples",
            )
        return MetricValue(metric_id, value, unit, MetricState.OBSERVED, "1")
