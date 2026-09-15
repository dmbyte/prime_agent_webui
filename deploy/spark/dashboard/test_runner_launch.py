#!/usr/bin/env python3
import unittest
from pathlib import Path


class RunnerLaunchRegressionTests(unittest.TestCase):
    def test_project_source_directory_is_provisioned_with_webui_acl(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        self.assertIn('project_sources=agent/"project-sources"', source)
        self.assertIn('(project_sources, writable_acl)', source)

    def test_task_workspace_defaults_to_home_prime_agent_tasks(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        self.assertIn('PRIME_RUNNER_WORKSPACE_ROOT', source)
        self.assertIn('prime-agent/tasks', source)
        self.assertIn('setfacl", "-m", writable_acl, str(workspace)', source)

    def test_command_construction_is_inside_acl_restoration_boundary(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        try_at = source.index("    try:\n", source.index("def main():"))
        command_at = source.index("openshell_runner.task_spec", try_at)
        finally_at = source.index("    finally:\n", command_at)
        restore_at = source.index('configure(request["owner"])', finally_at)
        self.assertLess(try_at, command_at)
        self.assertLess(command_at, finally_at)
        self.assertLess(finally_at, restore_at)

    def test_openshell_cli_never_inherits_prime_rpc_stdin(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        create_at = source.index('subprocess.Popen(spec["create"]')
        execute_at = source.index('subprocess.Popen(spec["execute"]')
        create_call = source[create_at:source.index(")", create_at)]
        execute_call = source[execute_at:source.index(")", execute_at)]
        self.assertIn("stdin=subprocess.DEVNULL", create_call)
        self.assertIn("stdin=subprocess.DEVNULL", execute_call)

    def test_prime_rpc_input_is_forwarded_through_sandbox_fifo(self):
        source = (Path(__file__).parents[1] / "container" / "runner_launch.py").read_text()
        self.assertIn("def forward_stdin_to_fifo", source)
        self.assertIn('spec["prepareInput"]', source)
        self.assertIn('spec["inputFifo"]', source)

    def test_nemotron_memory_target_preserves_qwen_coresidency(self):
        root = Path(__file__).parents[3]
        template = (root / "deploy/spark/vllm-nemotron35/vllm.env.template").read_text()
        start = (root / "deploy/spark/vllm-nemotron35/start.sh").read_text()
        self.assertIn("GPU_MEMORY_UTILIZATION=0.38", template)
        self.assertIn('GPU_MEMORY_UTILIZATION:-0.38', start)


if __name__ == "__main__":
    unittest.main()
