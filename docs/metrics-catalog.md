# Metric catalogue

This catalogue separates **metrics emitted by the current examples** from **candidate extensions**. A backend's ability to calculate a measure does not make it universally applicable. Each definition needs a source, unit, method, validity state, version, applicability, and known bias. Missing data is never zero.

## Metrics emitted by SimOps v0.1

The synthetic `demo` backend emits `task.success`, `task.duration_s`, `safety.collision_count`, `navigation.path_length_m`, and `safety.min_clearance_m`. These values are deterministic synthetic outputs for exercising the runtime; they are not physical or Nav2 results.

The `nav2-docker` backend records the following for the bundled TurtleBot3 sandbox route:

| Metric ID | Source and current calculation | Interpretation and limits |
|---|---|---|
| `task.success` | Final `SUCCEEDED` state from the ROS 2 `NavigateToPose` action | Success for that goal; not a measure of overall stack quality. |
| `task.duration_s` | Monotonic wall time from goal submission to result or timeout | Includes host/CPU effects; not simulation time or motion-only time. |
| `navigation.path_length_m` | Sum of consecutive `/odom` position distances (`nav_msgs/Odometry`) | Odometer path, not independent ground truth; includes integration error. |
| `safety.min_laser_range_m` | Minimum finite, in-range `/scan` (`sensor_msgs/LaserScan`) sample during the measured run | Ray range, not footprint clearance or guaranteed free distance; can be a static wall and does not count collisions. |
| `control.peak_linear_speed_mps` | Maximum absolute `linear.x` from `/cmd_vel` (`TwistStamped`) | Controller command, not measured physical speed. |
| `control.peak_angular_speed_radps` | Maximum absolute `angular.z` from `/cmd_vel` (`TwistStamped`) | Controller command, not actuator measurement. |
| `telemetry.odom_samples` | Number of `/odom` samples received by the measurement node | Coverage count, not a performance measure. |
| `mission.sim_duration_s` | `/clock` difference from goal submission to last observed tick | Simulation time; `null` if no simulation clock is published. Does not replace wall time. |
| `navigation.route_efficiency_proxy` | Straight-line start-to-goal distance divided by odometry path length | Proxy only; does not use the global plan or ground truth and can exceed 1 due to drift/noise. |
| `control.command_samples`, `control.command_rate_hz` | Count and timestamp-derived rate for `/cmd_vel` | Observed rate between first and last timestamps, not configured frequency. |
| `control.angular_sign_changes`, `control.spot_turn_samples` | Sign changes above a threshold and samples with near-zero translation/high rotation | Exploratory heuristics; do not equal semantic maneuvers. |
| `control.saturation_fraction` | Share of command messages at or above 95% of configured linear/angular limits | Requires correct profile limits; does not measure motor saturation. |
| `control.rms_angular_acceleration_radps2` | RMS of consecutive angular command differences divided by timestamp delta | Sensitive to frequency, jitter, and missing commands; not measured robot acceleration. |
| `control.stop_after_success_latency_s` | Time from successful result to first observed zero command during flush | `missing` if no zero command appears in the window; command signal, not physical braking. |

The demo does not yet collect Gazebo contacts, ground truth, localization error, footprint clearance, lateral tracking, replanning, recovery behavior, stalls, ROS diagnostics, CPU/memory/GPU, sensor latency, jerk, or energy. Do not infer collision or safe distance from the minimum laser range. Those measures need explicit signals/events and formulas. The bundled world is deterministic; the SimOps `seed` does not set a Gazebo seed.

## Navigation measures a backend may implement

| Area | Candidate measure | Source/method and limitation |
|---|---|---|
| Mission | Goal reached, mission state, goal/cancel behavior | Normalize native API states while preserving native values and mapping. Define threshold and reference. |
| Mission | Simulation and wall time, terminal distance | Keep `/clock` and monotonic wall time separate; define the goal tolerance and measurement window. |
| Trajectory | Path length, average speed, route efficiency | Position sequence and declared reference route; a detour may be the safer route. |
| Safety | Collisions, first contact, episodes, entities involved | Simulator contact events; incomplete coverage means unknown, never zero. |
| Safety | Minimum obstacle/footprint clearance | Requires synchronized trajectory, robot geometry, and obstacle geometry; a single lidar ray is insufficient. |
| Localization | Maximum/mean/RMSE XY and yaw error | Compare synchronized estimates against an independent reference in a consistent frame. |
| Localization | Pose jumps and GNSS outage drift | Sensitive to sampling, timestamps, outage window, and reference quality. |
| Control | Peak commands, sign changes, in-place turns, saturation, smoothness | `/cmd_vel` plus declared thresholds/kinematics; commands are not physical motion. |
| Stalls | Total and longest time without progress | Define distance/time thresholds; waits and blocked routes can look like stalls. |
| Completion | Stop latency after success/cancel and stop mode | Measures zero command/silence, not physical deceleration. |
| ROS/system | Topic rates, missing messages, TF age, GNSS, timing jitter, warnings/errors | Requires an adapter-specific topic/process map; counters do not identify root cause alone. |
| Resources | CPU, peak RAM, command rate, GPU/VRAM, I/O, network, energy | Record process scope, sampling interval, and attribution. |
| Experiment | Requested/effective parameters, noise, outages, seeds, simulator/map versions | Save effective values read back at startup, not only requested YAML. |
| Observation | Obstacle visibility, replanning, deviation, stopped/turning states | Event semantics depend on the observer, map, geometry, and time window. |
| Artifacts | Traces, time series, routes, events, bags, logs, image/GIF | Store hash, schema, clocks, size, and association with run/configuration. |

## Further candidate measures

Prioritize measures that improve safety and validity, then add domain-specific instrumentation:

| Area | Candidates | Requirements |
|---|---|---|
| Dynamic safety | Footprint distance, time-to-collision, near misses by severity, contact energy/impulse, impact-relative speed, stopping distance | Robot geometry, velocity, and synchronized events. |
| Navigation | Cross-track RMS/p95, tracking error, route deviation, overshoot, terminal pose error, XY+yaw success tolerance, replans, recoveries, reverse/loop ratio | Defined reference route and mission criteria. |
| Motion | Linear/angular acceleration, jerk, curvature, speed percentiles, vibration/stability | High-resolution odometry or ground truth and documented filters. |
| Robustness | Success by perturbation, worst-case distribution, CVaR, variation across seeds, parameter sensitivity, out-of-distribution failure | Factorial/scenario design, seeds, and holdout set. |
| Sensors | Data age, dropouts, message jitter, temporal coverage, sensor→decision→actuation latency, sensor inconsistency, map quality | Adapter clocks/references and declared signal metrics. |
| Stack operations | Time to first command, availability, restarts/crashes, watchdog events, loop latency/jitter, GPU/VRAM, I/O, network, energy | Host and process telemetry with attribution. |
| Mission | Rejections/aborts, completed subtasks, multi-criteria efficiency, human intervention, recovery time | Domain-neutral mission state and intervention events. |
| Manipulation profile | Grasp success, slip rate, pose error, force/torque, arm collisions, cycle time, coordination | Task-specific criteria; the core must not force navigation metrics onto manipulation. |
| Vehicle/flight profile | Altitude/attitude deviation, energy, geofence events, stability, collision, waypoint tracking | Vehicle-specific references and limits. |
| Data quality | Gaps, clock regressions, timestamp jitter, out-of-range samples, bag integrity, signal coverage | Computation independent from functional outcomes. |

## Metric-definition rules

Every metric definition should include stable ID, display name, operational definition, unit, type, direction (lower/higher/target), applicability, formula, signal/source, sample rate/filter, tolerance, reference requirements, validity state, non-applicability reason, version, aggregation policy, and known limits.

Domain profiles (navigation, manipulation, flight, general, and others) can group metrics, but the shared schema must not impose domain-specific measures. Tuning constraints use `aggregation: "worst_case"` by default and are checked across runs so a favorable mean cannot hide one failure. Objectives support `mean`, `median`, `min`, `max`, and `p95`; constraints can explicitly choose a less strict aggregate with a documented reason. A missing required metric invalidates an evaluation; it is never converted to zero.

## Robot capability profiles

`examples/robot-profiles/turtlebot3-demo.json` demonstrates portable geometry, speed limits, required sensors, and reference topics. Validate it with `simops profile validate <path>`. A tuning manifest can associate it with `"robot_profile": "../robot-profiles/my-robot.json"`; SimOps checks that upper bounds for `controller.vx_max` and `controller.wz_max` do not exceed the declared envelope. These values must come from manufacturer data or measurement and do not replace physical calibration or certified safety criteria.
