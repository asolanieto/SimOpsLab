from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_tools_validate_start_status_and_report_campaign(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP optional dependency is not installed")
        from simops.mcp_server import create_mcp_server

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            manifests = workspace / "manifests"
            manifests.mkdir()
            shutil.copy(Path("examples/demo-campaign.json"), manifests / "demo-campaign.json")
            shutil.copy(Path("examples/demo-tuning.json"), manifests / "demo-tuning.json")
            server = create_mcp_server(workspace)
            async with Client(server) as client:
                tools = await client.list_tools()
                self.assertIn("start_campaign", {tool.name for tool in tools.tools})
                self.assertIn("validate_tuning", {tool.name for tool in tools.tools})
                listed = await client.call_tool("list_backends", {})
                self.assertEqual(listed.structured_content["result"], ["demo"])
                tuning_validation = await client.call_tool(
                    "validate_tuning", {"manifest_name": "demo-tuning.json"}
                )
                self.assertTrue(tuning_validation.structured_content["valid"])
                self.assertEqual(tuning_validation.structured_content["candidate_budget"], 12)
                validation = await client.call_tool(
                    "validate_campaign", {"manifest_name": "demo-campaign.json"}
                )
                self.assertTrue(validation.structured_content["valid"])
                traversal = await client.call_tool(
                    "validate_campaign", {"manifest_name": "../demo-campaign.json"}
                )
                self.assertTrue(traversal.is_error)
                started = await client.call_tool(
                    "start_campaign", {"manifest_name": "demo-campaign.json"}
                )
                self.assertEqual(started.structured_content["status"], "running")
                for _ in range(100):
                    status = await client.call_tool(
                        "get_campaign_status", {"campaign_id": "demo-navigation-smoke"}
                    )
                    if status.structured_content["status"] == "completed":
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(status.structured_content["status"], "completed")
                result = await client.call_tool(
                    "get_campaign_result", {"campaign_id": "demo-navigation-smoke"}
                )
                self.assertEqual(result.structured_content["campaign"]["planned_runs"], 8)
                self.assertEqual(len(result.structured_content["groups"]), 4)
                self.assertIn(
                    "task.success@1", result.structured_content["groups"][0]["metrics"]
                )
                report = await client.call_tool(
                    "render_report", {"campaign_id": "demo-navigation-smoke"}
                )
                self.assertEqual(len(report.structured_content["files"]), 3)
                json_path = workspace / report.structured_content["files"][0]
                self.assertTrue(json_path.is_file())
                analysis = json.loads(json_path.read_text(encoding="utf-8"))
                self.assertEqual(analysis["campaign"]["planned_runs"], 8)


class MCPWorkspacePolicyTests(unittest.TestCase):
    def test_tuning_profile_cannot_escape_workspace(self):
        from simops.mcp_server import MCPController, WorkspacePolicy

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            manifests = workspace / "manifests"
            manifests.mkdir(parents=True)
            outside_profile = root / "robot.json"
            shutil.copy(Path("examples/robot-profiles/turtlebot3-demo.json"), outside_profile)
            manifest = json.loads(Path("examples/nav2-turtlebot3/tuning.json").read_text())
            manifest["robot_profile"] = "../../robot.json"
            (manifests / "escape.json").write_text(json.dumps(manifest))
            controller = MCPController(workspace, WorkspacePolicy(allowed_backends={"nav2-docker"}))
            with self.assertRaisesRegex(ValueError, "inside the configured workspace"):
                controller.start_tuning("escape.json")


if __name__ == "__main__":
    unittest.main()
