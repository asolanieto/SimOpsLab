from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from simops.optimization import ParameterKind, ParameterSpec
from simops.robot_profile import load_robot_profile
from simops.tuning import _validate_profile_parameter_bounds, load_tuning_manifest


class RobotProfileTests(unittest.TestCase):
    def test_example_profile_loads_and_declares_sensor_contract(self):
        profile = load_robot_profile(Path("examples/robot-profiles/turtlebot3-demo.json"))
        self.assertEqual(profile.profile_id, "turtlebot3-demo-envelope")
        self.assertGreater(profile.footprint_radius_m, 0)
        self.assertEqual({item["name"] for item in profile.sensors}, {"laser", "odometry", "velocity_command"})

    def test_profile_rejects_tuning_speed_bounds_outside_robot_envelope(self):
        profile = load_robot_profile(Path("examples/robot-profiles/turtlebot3-demo.json"))
        parameter = ParameterSpec("controller.vx_max", ParameterKind.FLOAT, lower=0.1, upper=0.3)
        with self.assertRaisesRegex(ValueError, "exceeds robot profile"):
            _validate_profile_parameter_bounds(profile, (parameter,), {})

    def test_nav2_tuning_manifest_binds_robot_envelope(self):
        manifest = load_tuning_manifest(Path("examples/nav2-turtlebot3/tuning.json"))
        self.assertEqual(manifest.robot_profile.profile_id, "turtlebot3-demo-envelope")
        self.assertEqual(manifest.objective_aggregations["task.duration_s"], "mean")
        self.assertEqual(manifest.constraints[0]["aggregation"], "worst_case")

    def test_profile_rejects_nonpositive_geometry(self):
        data = json.loads(Path("examples/robot-profiles/turtlebot3-demo.json").read_text())
        data["geometry"]["footprint_radius_m"] = 0
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "finite positive"):
                load_robot_profile(path)


if __name__ == "__main__":
    unittest.main()
