"""In-container Nav2 task driver used by the pinned demo backend."""

from __future__ import annotations

import argparse
import json
import math
import signal
import subprocess
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-x", type=float, required=True)
    parser.add_argument("--start-y", type=float, required=True)
    parser.add_argument("--start-yaw", type=float, required=True)
    parser.add_argument("--goal-x", type=float, required=True)
    parser.add_argument("--goal-y", type=float, required=True)
    parser.add_argument("--goal-yaw", type=float, required=True)
    parser.add_argument("--timeout-s", type=float, required=True)
    parser.add_argument("--vx-limit", type=float, required=True)
    parser.add_argument("--wz-limit", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log = Path("/simops_work/bringup.log")
    params = Path("/simops_work/nav2_params.yaml")
    _merge_nav2_params(args.params, params)
    launch_command = [
        "ros2", "launch", "nav2_bringup", "tb3_simulation_launch.py",
        "headless:=true", "use_rviz:=false", "slam:=false", "use_simulator:=true",
        f"params_file:={params}",
        f"x_pose:={args.start_x}", f"y_pose:={args.start_y}", f"yaw:={args.start_yaw}",
    ]
    with log.open("w", encoding="utf-8") as log_file:
        launch = subprocess.Popen(
            launch_command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            result = _navigate(args, launch, log)
            Path(args.output).write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            return 0
        finally:
            if launch.poll() is None:
                try:
                    launch.send_signal(signal.SIGINT)
                    launch.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    launch.terminate()
                    try:
                        launch.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        launch.kill()
                        launch.wait(timeout=5)


def _merge_nav2_params(overrides_path: str, output_path: Path) -> None:
    import yaml
    from ament_index_python.packages import get_package_share_directory

    default_path = (
        Path(get_package_share_directory("nav2_bringup")) / "params" / "nav2_params.yaml"
    )
    base = yaml.safe_load(default_path.read_text(encoding="utf-8"))
    overrides = yaml.safe_load(Path(overrides_path).read_text(encoding="utf-8"))

    def update(target: dict, patch: dict) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                update(target[key], value)
            else:
                target[key] = value

    update(base, overrides)
    output_path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")


def _navigate(args: argparse.Namespace, launch: subprocess.Popen[bytes], log: Path) -> dict[str, object]:
    import rclpy
    from action_msgs.msg import GoalStatus
    from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, TwistStamped
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import Odometry
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSDurabilityPolicy, QoSProfile, qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import LaserScan

    rclpy.init(args=None)
    node = Node(
        "simops_turtlebot3_driver",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
    )
    action = ActionClient(node, NavigateToPose, "navigate_to_pose")
    lifecycle_clients = {
        name: node.create_client(GetState, f"/{name}/get_state")
        for name in ("amcl", "bt_navigator")
    }
    path_length = 0.0
    odom_samples = 0
    prior_position: tuple[float, float] | None = None
    min_laser_range: float | None = None
    peak_linear_speed = 0.0
    peak_angular_speed = 0.0
    cmd_samples = 0
    cmd_stamps: list[float] = []
    angular_samples: list[tuple[float, float]] = []
    angular_sign_changes = 0
    spot_turn_samples = 0
    saturated_samples = 0
    post_success = False
    post_success_zero_stamp: float | None = None
    sim_clock_start: float | None = None
    sim_clock_end: float | None = None
    completion_sim_time: float | None = None

    def stamp_seconds(stamp) -> float:
        return float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0

    def clock_callback(message: Clock) -> None:
        nonlocal sim_clock_end
        value = stamp_seconds(message.clock)
        if sim_clock_start is None:
            # Set by goal dispatch below; pre-goal clock ticks are intentionally ignored.
            return
        sim_clock_end = value

    def odom_callback(message: Odometry) -> None:
        nonlocal path_length, odom_samples, prior_position
        point = message.pose.pose.position
        current = (float(point.x), float(point.y))
        if prior_position is not None:
            path_length += math.dist(prior_position, current)
        prior_position = current
        odom_samples += 1

    def scan_callback(message: LaserScan) -> None:
        nonlocal min_laser_range
        finite = [
            float(value)
            for value in message.ranges
            if math.isfinite(value) and message.range_min <= value <= message.range_max
        ]
        if finite:
            observed = min(finite)
            min_laser_range = observed if min_laser_range is None else min(min_laser_range, observed)

    def command_callback(message: TwistStamped) -> None:
        nonlocal peak_linear_speed, peak_angular_speed, cmd_samples
        nonlocal angular_sign_changes, spot_turn_samples, saturated_samples, post_success_zero_stamp
        linear = float(message.twist.linear.x)
        angular = float(message.twist.angular.z)
        stamp = stamp_seconds(message.header.stamp)
        peak_linear_speed = max(peak_linear_speed, abs(linear))
        peak_angular_speed = max(peak_angular_speed, abs(angular))
        cmd_samples += 1
        if stamp > 0:
            cmd_stamps.append(stamp)
            angular_samples.append((stamp, angular))
        if angular_samples and len(angular_samples) > 1:
            previous = angular_samples[-2][1]
            if previous * angular < 0 and abs(previous) > 0.05 and abs(angular) > 0.05:
                angular_sign_changes += 1
        if abs(linear) < 0.03 and abs(angular) > 0.15:
            spot_turn_samples += 1
        if abs(linear) >= 0.95 * args.vx_limit or abs(angular) >= 0.95 * args.wz_limit:
            saturated_samples += 1
        if post_success and post_success_zero_stamp is None and abs(linear) < 0.01 and abs(angular) < 0.01:
            post_success_zero_stamp = stamp

    node.create_subscription(Odometry, "/odom", odom_callback, 20)
    node.create_subscription(LaserScan, "/scan", scan_callback, qos_profile_sensor_data)
    node.create_subscription(TwistStamped, "/cmd_vel", command_callback, 20)
    node.create_subscription(Clock, "/clock", clock_callback, qos_profile_sensor_data)
    initialpose_qos = QoSProfile(depth=10, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
    initial_publisher = node.create_publisher(
        PoseWithCovarianceStamped, "/initialpose", initialpose_qos
    )

    def set_pose(message: PoseStamped, x: float, y: float, yaw: float) -> None:
        message.header.frame_id = "map"
        message.header.stamp = node.get_clock().now().to_msg()
        message.pose.position.x = x
        message.pose.position.y = y
        message.pose.orientation.z = math.sin(yaw / 2.0)
        message.pose.orientation.w = math.cos(yaw / 2.0)

    try:
        startup_deadline = time.monotonic() + min(90.0, args.timeout_s)
        amcl_client = lifecycle_clients["amcl"]
        while time.monotonic() < startup_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if launch.poll() is not None:
                raise RuntimeError(f"Nav2 launch exited early; see {log}")
            if not amcl_client.wait_for_service(timeout_sec=0.0):
                continue
            future = amcl_client.call_async(GetState.Request())
            rclpy.spin_until_future_complete(node, future, timeout_sec=2.0)
            if future.done() and future.result() and future.result().current_state.id == 3:
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("AMCL did not become active before timeout")

        end_initialization = time.monotonic() + 3.0
        next_initialpose = 0.0
        while time.monotonic() < end_initialization:
            if time.monotonic() >= next_initialpose:
                initial = PoseWithCovarianceStamped()
                initial.header.frame_id = "map"
                initial.header.stamp.sec = 0
                initial.header.stamp.nanosec = 0
                initial.pose.pose.position.x = args.start_x
                initial.pose.pose.position.y = args.start_y
                initial.pose.pose.orientation.z = math.sin(args.start_yaw / 2.0)
                initial.pose.pose.orientation.w = math.cos(args.start_yaw / 2.0)
                for index in (0, 7, 35):
                    initial.pose.covariance[index] = 0.25
                initial_publisher.publish(initial)
                next_initialpose = time.monotonic() + 0.5
            rclpy.spin_once(node, timeout_sec=0.1)

        bt_client = lifecycle_clients["bt_navigator"]
        while time.monotonic() < startup_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if launch.poll() is not None:
                raise RuntimeError(f"Nav2 launch exited before activation; see {log}")
            if bt_client.wait_for_service(timeout_sec=0.0):
                future = bt_client.call_async(GetState.Request())
                rclpy.spin_until_future_complete(node, future, timeout_sec=2.0)
                if (
                    future.done()
                    and future.result()
                    and future.result().current_state.id == 3
                    and action.wait_for_server(timeout_sec=0.0)
                ):
                    break
            time.sleep(0.2)
        else:
            raise TimeoutError("Nav2 navigation server did not become active before timeout")

        goal = NavigateToPose.Goal()
        set_pose(goal.pose, args.goal_x, args.goal_y, args.goal_yaw)
        nonlocal_clock = node.get_clock().now().nanoseconds / 1_000_000_000.0
        sim_clock_start = nonlocal_clock
        sim_clock_end = nonlocal_clock
        started = time.monotonic()
        goal_future = action.send_goal_async(goal)
        rclpy.spin_until_future_complete(node, goal_future, timeout_sec=10.0)
        if not goal_future.done() or goal_future.result() is None:
            raise TimeoutError("Nav2 did not acknowledge the navigation goal")
        goal_handle = goal_future.result()
        if not goal_handle.accepted:
            raise RuntimeError("Nav2 rejected the navigation goal")
        result_future = goal_handle.get_result_async()
        deadline = started + args.timeout_s
        while not result_future.done() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if launch.poll() is not None:
                raise RuntimeError(f"Nav2 launch exited during navigation; see {log}")
        duration = time.monotonic() - started
        success = bool(
            result_future.done()
            and result_future.result() is not None
            and result_future.result().status == GoalStatus.STATUS_SUCCEEDED
        )
        if not result_future.done():
            try:
                goal_handle.cancel_goal_async()
            except Exception:
                pass
        post_success = success
        completion_sim_time = sim_clock_end
        # Give sensor callbacks a short interval to flush after the terminal action status.
        flush_deadline = time.monotonic() + 1.0
        while time.monotonic() < flush_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        angular_accel = []
        for prior, current in zip(angular_samples, angular_samples[1:]):
            delta_t = current[0] - prior[0]
            if delta_t > 0:
                angular_accel.append((current[1] - prior[1]) / delta_t)
        rms_angular_accel = math.sqrt(sum(value * value for value in angular_accel) / len(angular_accel)) if angular_accel else None
        sim_end = completion_sim_time if completion_sim_time is not None else sim_clock_end
        sim_duration = max(0.0, sim_end - sim_clock_start) if sim_end is not None and sim_clock_start is not None else None
        route_distance = math.hypot(args.goal_x - args.start_x, args.goal_y - args.start_y)
        return {
            "success": success,
            "duration_s": duration,
            "sim_duration_s": sim_duration,
            "route_efficiency": route_distance / path_length if path_length and path_length > 0 else None,
            "path_length_m": path_length if odom_samples else None,
            "min_laser_range_m": min_laser_range,
            "peak_linear_speed_mps": peak_linear_speed,
            "peak_angular_speed_radps": peak_angular_speed,
            "odom_samples": odom_samples,
            "cmd_samples": cmd_samples,
            "cmd_rate_hz": (len(cmd_stamps) - 1) / (cmd_stamps[-1] - cmd_stamps[0]) if len(cmd_stamps) > 1 and cmd_stamps[-1] > cmd_stamps[0] else None,
            "angular_sign_changes": angular_sign_changes,
            "spot_turn_samples": spot_turn_samples,
            "command_saturation_fraction": saturated_samples / cmd_samples if cmd_samples else None,
            "rms_angular_accel_radps2": rms_angular_accel,
            "stop_after_success_latency_s": (post_success_zero_stamp - completion_sim_time) if post_success_zero_stamp is not None and completion_sim_time is not None else None,
            "goal_status": int(result_future.result().status) if result_future.done() else None,
        }
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
