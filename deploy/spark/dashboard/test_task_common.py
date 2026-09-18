#!/usr/bin/env python3
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "container"))
import task_common


def policy(network="restricted", execution="task", profile="general"):
    return {"profile": profile, "networkMode": network, "executionMode": execution,
            "limits": {"memoryGiB": 8, "cpus": 4, "runtimeMinutes": 30,
                       "pids": 256, "openFiles": 1024, "temporaryGiB": 4}}


class TaskCommonTests(unittest.TestCase):
    def test_image_preprovisions_prime_kernel_runtime(self):
        containerfile = (Path(__file__).parents[1] / "container" / "Containerfile").read_text()
        self.assertIn("PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python", containerfile)
        self.assertIn("ipykernel /usr/local/lib/node_modules/prime-agent/dist/prime-agent-runtime", containerfile)
        self.assertIn("uv venv --python /usr/bin/python3.11 /opt/prime-kernel", containerfile)
        self.assertIn("python3-pip", containerfile)
        self.assertIn("UV_CACHE_DIR=/home/prime/.prime/cache/uv", containerfile)
        self.assertIn("chromium dnsutils ipmitool", containerfile)
        entrypoint = (Path(__file__).parents[1] / "container" / "prime-container-entrypoint.sh").read_text()
        self.assertIn("skill_registry=\"$prime_state/agent/skills\"", entrypoint)
        self.assertIn("workspace-backup-", entrypoint)
        installer = (Path(__file__).parents[1] / "openshell" / "install.sh").read_text()
        self.assertIn('docker build --file "$repo/deploy/spark/container/Containerfile"', installer)
        self.assertLess(
            containerfile.index("uv-aarch64-unknown-linux-gnu.tar.gz"),
            containerfile.index('if [ "$PROFILE" = "development" ]'),
        )

    def test_broker_command_crosses_only_validated_runner_boundary(self):
        argv = task_common.broker_command("a" * 32, "alice", policy(), "openai", "example", "low")
        self.assertEqual(argv[0], "/usr/local/libexec/prime-runner-client")
        self.assertEqual(len(argv), 2)

    def test_owner_cannot_escape_storage_root(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "owner"):
                task_common.prepare_user_storage(root, "../root")

    def test_workspace_can_live_under_separate_host_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent, workspace = task_common.prepare_user_storage(root / "users", "alice", root / "prime-agent/tasks")
            self.assertEqual(agent, (root / "users/alice/prime/agent").resolve())
            self.assertEqual(workspace, (root / "prime-agent/tasks/alice").resolve())
            self.assertTrue(workspace.is_dir())

    def test_workspace_owner_cannot_escape_separate_host_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "owner"):
                task_common.prepare_user_storage(root / "users", "../alice", root / "prime-agent/tasks")

    def test_selected_local_path_is_resolved_for_read_only_mount(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "project")
            os.mkdir(source)
            with mock.patch.object(task_common, "LOCAL_PATH_ROOTS", (task_common.Path(root).resolve(),)):
                mounts = task_common.local_mounts([source])
            self.assertEqual(mounts, [(task_common.Path(source).resolve(), "/project-files/01-project")])

    def test_sensitive_and_outside_root_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            sensitive = os.path.join(root, ".ssh")
            os.mkdir(sensitive)
            with mock.patch.object(task_common, "LOCAL_PATH_ROOTS", (task_common.Path(root).resolve(),)):
                with self.assertRaisesRegex(ValueError, "Sensitive"):
                    task_common.local_mounts([sensitive])
            with self.assertRaisesRegex(ValueError, "approved data roots"):
                task_common.local_mounts([root])


if __name__ == "__main__":
    unittest.main()
