#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "container"))
import openshell_runner


class OpenShellRunnerTests(unittest.TestCase):
    def build(self, local_paths=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        storage = root / "users"
        gateway = root / "gateway" / "alice" / "restricted"
        gateway.mkdir(parents=True)
        manifest = root / "images.json"
        manifest.write_text(json.dumps({"general": {"image": "local/prime-openshell-general:0.9.5-" + "a" * 12}}))
        policy = {"profile": "general", "networkMode": "restricted", "executionMode": "task", "approvalMode": "manual", "localPaths": local_paths or [], "limits": {"memoryGiB": 8, "cpus": 4, "runtimeMinutes": 30, "pids": 256, "openFiles": 1024, "temporaryGiB": 4}}
        return openshell_runner.task_spec("a" * 32, "alice", policy, "spark-nemotron", "example", "low", storage_root=storage, image_manifest=manifest, policy_root=root / "policies", workspace_root=root / "prime-agent/tasks")

    def test_openshell_task_is_bounded_and_default_deny(self):
        spec = self.build()
        create = " ".join(spec["create"])
        execute = " ".join(spec["execute"])
        self.assertIn("--memory 8Gi", create)
        self.assertIn("--cpu 4", create)
        self.assertIn("--approval-mode manual", create)
        self.assertIn("--gateway spark-local", create)
        self.assertIn("/home/prime/.prime", create)
        self.assertIn("/run/prime-gateway", create)
        self.assertIn("sandbox exec", execute)
        self.assertIn("--workdir /project", execute)
        self.assertIn("os.O_RDONLY|os.O_NONBLOCK", execute)
        self.assertIn("subprocess.Popen(sys.argv[2:]", execute)
        self.assertIn("TINI_SUBREAPER=1", execute)
        self.assertIn("PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python", execute)
        self.assertIn("IPYTHONDIR=/home/prime/.prime/ipython", execute)
        self.assertIn("UV_CACHE_DIR=/home/prime/.prime/cache/uv", execute)
        self.assertIn("NPM_CONFIG_PREFIX=/home/prime/.prime/tools/npm", execute)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH=/home/prime/.prime/tools/playwright", execute)
        self.assertIn("--daemon-socket /tmp/prime-daemon-aaaaaaaaaaaaaaaa.sock", execute)
        self.assertEqual(spec["daemonSocket"], "/tmp/prime-daemon-aaaaaaaaaaaaaaaa.sock")
        self.assertTrue(str(spec["workspace"]).endswith("/prime-agent/tasks/alice"))
        config = json.loads(spec["create"][spec["create"].index("--driver-config-json") + 1])
        volumes = config["docker"]["mounts"][:3]
        self.assertEqual([row["type"] for row in volumes], ["volume", "volume", "volume"])
        self.assertEqual(volumes[0]["source"], "prime-alice-prime")
        self.assertEqual(volumes[2]["source"], "prime-alice-gateway-restricted")
        self.assertIn("network_policies: {}", spec["policy"].read_text())
        self.assertIn("compatibility: hard_requirement", spec["policy"].read_text())
        self.assertIn("mkfifo -m 600 /tmp/prime-rpc-", " ".join(spec["prepareInput"]))
        self.assertTrue(spec["inputFifo"].startswith("/tmp/prime-rpc-"))

    def test_missing_resource_limits_use_bounded_defaults(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        manifest = root / "images.json"
        manifest.write_text(json.dumps({"general": {"image": "local/prime-openshell-general:0.9.5-" + "a" * 12}}))
        spec = openshell_runner.task_spec(
            "b" * 32,
            "alice",
            {"profile": "general", "networkMode": "restricted", "executionMode": "deny", "approvalMode": "manual"},
            "spark-nemotron",
            "example",
            "low",
            storage_root=root / "users",
            image_manifest=manifest,
            policy_root=root / "policies",
        )
        create = " ".join(spec["create"])
        self.assertIn("--memory 8Gi", create)
        self.assertIn("--cpu 4", create)
        self.assertIn("timeout --signal=TERM --kill-after=15s 30m", " ".join(spec["execute"]))

    def test_local_path_is_read_only_volume_subpath_and_landlock_policy(self):
        with tempfile.TemporaryDirectory() as source_root:
            source = Path(source_root) / "project"
            source.mkdir()
            with mock.patch.object(openshell_runner.task_common, "LOCAL_PATH_ROOTS", (Path(source_root).resolve(),)):
                spec = self.build([str(source)])
            config = json.loads(spec["create"][spec["create"].index("--driver-config-json") + 1])
            local = [row for row in config["docker"]["mounts"] if row["target"].startswith("/project-files/")][0]
            self.assertTrue(local["read_only"])
            self.assertEqual(local["type"], "volume")
            self.assertEqual(local["subpath"], "project")
            self.assertIn(local["target"], spec["policy"].read_text())

    def test_project_sources_are_read_only_inside_the_sandbox(self):
        spec = self.build()
        policy = spec["policy"].read_text()
        self.assertIn("    - /home/prime/.prime/agent/project-sources", policy)
        self.assertIn("    - /home/prime/.prime", policy)

    def test_browser_runtime_devices_are_granted_at_sandbox_creation(self):
        policy = self.build()["policy"].read_text()
        for path in ("/dev/urandom", "/dev/random", "/dev/shm"):
            self.assertIn(f"    - {path}", policy)


if __name__ == "__main__":
    unittest.main()
