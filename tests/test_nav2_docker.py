from __future__ import annotations

import unittest

from simops.contracts import MetricState, RunSpec
from simops.nav2_docker import Nav2DockerBackend


class Nav2DockerBackendTests(unittest.TestCase):
    def test_parameters_are_mapped_to_mppi_and_both_costmaps(self):
        yaml = Nav2DockerBackend._parameter_yaml(
            {
                "controller.vx_max": 0.62,
                "controller.wz_max": 1.4,
                "controller.temperature": 0.5,
                "costmap.inflation_radius_m": 0.8,
            }
        )
        self.assertIn("vx_max: 0.62", yaml)
        self.assertIn("wz_max: 1.4", yaml)
        self.assertIn("temperature: 0.5", yaml)
        self.assertEqual(yaml.count("inflation_radius: 0.8"), 2)

    def test_missing_sensor_metric_has_explicit_missing_state(self):
        metric = Nav2DockerBackend._measured("safety.min_laser_range_m", None, "m")
        self.assertIs(metric.state, MetricState.MISSING)
        self.assertIsNone(metric.value)
        self.assertTrue(metric.reason)

    def test_backend_rejects_out_of_range_parameter(self):
        backend = Nav2DockerBackend()
        spec = RunSpec(
            run_id="test-run",
            campaign_id="test-campaign",
            scenario_id="route",
            system_id="nav2",
            configuration_id="bad",
            repetition=0,
            configuration={"controller.vx_max": 9.0},
        )
        self.assertTrue(
            any("controller.vx_max must be between" in error for error in backend.validate(spec))
        )


if __name__ == "__main__":
    unittest.main()
