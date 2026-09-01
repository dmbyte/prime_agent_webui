#!/usr/bin/env python3
import unittest
from pathlib import Path


class RunnerLaunchRegressionTests(unittest.TestCase):
    def test_command_construction_is_inside_acl_restoration_boundary(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        try_at = source.index("    try:\n", source.index("def main():"))
        command_at = source.index("argv=container_runner.command", try_at)
        finally_at = source.index("    finally:\n", command_at)
        restore_at = source.index('configure(request["owner"])', finally_at)
        self.assertLess(try_at, command_at)
        self.assertLess(command_at, finally_at)
        self.assertLess(finally_at, restore_at)


if __name__ == "__main__":
    unittest.main()
