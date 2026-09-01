#!/usr/bin/env python3
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import container_runner


def policy(network="restricted", execution="task", profile="general"):
    return {"profile": profile, "networkMode": network, "executionMode": execution,
            "limits": {"memoryGiB": 8, "cpus": 4, "runtimeMinutes": 30,
                       "pids": 256, "openFiles": 1024, "temporaryGiB": 4}}


class ContainerRunnerTests(unittest.TestCase):
    def test_image_preprovisions_prime_kernel_runtime(self):
        containerfile = (Path(__file__).parents[1] / "container" / "Containerfile").read_text()
        self.assertIn("PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python", containerfile)
        self.assertIn("ipykernel /usr/local/lib/node_modules/prime-agent/dist/prime-agent-runtime", containerfile)
        self.assertIn("uv venv --python /usr/bin/python3.11 /opt/prime-kernel", containerfile)
        self.assertLess(
            containerfile.index("uv-aarch64-unknown-linux-gnu.tar.gz"),
            containerfile.index('if [ "$PROFILE" = "development" ]'),
        )

    def build(self, authorization=None, owner="alice"):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(os, "getuid", return_value=1200), mock.patch.object(os, "getgid", return_value=1200):
            return container_runner.command("a" * 32, owner, authorization or policy(), "openai", "example", "low", storage_root=root)

    def test_restricted_task_is_rootless_read_only_and_bounded(self):
        argv = self.build()
        joined = " ".join(argv)
        self.assertIn("--network none", joined)
        self.assertIn("--read-only", argv)
        self.assertIn("--read-only-tmpfs=false", argv)
        self.assertTrue(any(value.startswith("/tmp:") and "notmpcopyup" in value for value in argv))
        self.assertTrue(any(value.startswith("/run:") and "notmpcopyup" in value for value in argv))
        self.assertIn("--cap-drop=all", argv)
        self.assertIn("no-new-privileges", argv)
        self.assertIn("--memory 8g", joined)
        self.assertIn("NO_PROXY=127.0.0.1,localhost,::1", argv)
        self.assertNotIn("--privileged", argv)

    def test_denied_execution_disables_prime_tools(self):
        self.assertIn("--no-tools", self.build(policy(execution="deny")))

    def test_full_network_uses_rootless_user_mode_not_host(self):
        argv = self.build(policy(network="full", profile="network-operations"))
        joined = " ".join(argv)
        self.assertIn("slirp4netns", joined)
        self.assertNotIn("--network host", joined)

    def test_proxy_modes_mount_only_the_selected_user_gateway(self):
        argv = self.build(policy(network="internet"))
        joined = " ".join(argv)
        self.assertIn("/gateway/alice/internet,dst=/run/prime-gateway,ro", joined)
        self.assertNotIn("/gateway/alice/lan", joined)

    def test_broker_command_crosses_only_validated_runner_boundary(self):
        argv = container_runner.broker_command("a" * 32, "alice", policy(), "openai", "example", "low")
        self.assertEqual(argv[0], "/usr/local/libexec/prime-runner-client")
        self.assertEqual(len(argv), 2)

    def test_production_manifest_requires_digest_pinned_profile(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = os.path.join(root, "images.json")
            with open(manifest, "w") as handle:
                handle.write('{"general":"localhost/prime-task-general:0.8.0@sha256:' + 'a' * 64 + '"}')
            with mock.patch.object(os, "getuid", return_value=1200), mock.patch.object(os, "getgid", return_value=1200):
                argv = container_runner.command("a" * 32, "alice", policy(), "openai", "example", "low", storage_root=root, image_manifest=manifest)
            self.assertTrue(any(value.endswith("@sha256:" + "a" * 64) for value in argv))

    def test_owner_cannot_escape_storage_root(self):
        with self.assertRaisesRegex(ValueError, "owner"):
            self.build(owner="../root")

    def test_selected_local_path_is_mounted_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "project")
            os.mkdir(source)
            authorization = policy()
            authorization["localPaths"] = [source]
            with mock.patch.object(container_runner, "LOCAL_PATH_ROOTS", (container_runner.Path(root).resolve(),)), mock.patch.object(os, "getuid", return_value=1200), mock.patch.object(os, "getgid", return_value=1200):
                argv = container_runner.command("a" * 32, "alice", authorization, "openai", "example", "low", storage_root=os.path.join(root, "storage"))
            self.assertIn(f"type=bind,src={container_runner.Path(source).resolve()},dst=/project-files/01-project,ro", argv)

    def test_sensitive_and_outside_root_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            sensitive = os.path.join(root, ".ssh")
            os.mkdir(sensitive)
            with mock.patch.object(container_runner, "LOCAL_PATH_ROOTS", (container_runner.Path(root).resolve(),)):
                with self.assertRaisesRegex(ValueError, "Sensitive"):
                    container_runner.local_mounts([sensitive])
            with self.assertRaisesRegex(ValueError, "approved data roots"):
                container_runner.local_mounts([root])

if __name__ == "__main__":
    unittest.main()
