#!/usr/bin/env python3
import unittest
from pathlib import Path


class RunnerLaunchRegressionTests(unittest.TestCase):
    def test_project_source_directory_is_provisioned_with_webui_acl(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        self.assertIn('project_sources=agent/"project-sources"', source)
        self.assertIn('(project_sources, writable_acl)', source)

    def test_command_construction_is_inside_acl_restoration_boundary(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        try_at = source.index("    try:\n", source.index("def main():"))
        command_at = source.index("openshell_runner.task_spec", try_at)
        finally_at = source.index("    finally:\n", command_at)
        restore_at = source.index('configure(request["owner"])', finally_at)
        self.assertLess(try_at, command_at)
        self.assertLess(command_at, finally_at)
        self.assertLess(finally_at, restore_at)


if __name__ == "__main__":
    unittest.main()
