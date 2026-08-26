#!/usr/bin/env python3
import os
import tempfile
import unittest
from unittest import mock

import container_runner


def policy(network="restricted", execution="task", profile="general"):
    return {"profile": profile, "networkMode": network, "executionMode": execution,
            "limits": {"memoryGiB": 8, "cpus": 4, "runtimeMinutes": 30,
                       "pids": 256, "openFiles": 1024, "temporaryGiB": 4}}


class ContainerRunnerTests(unittest.TestCase):
    def build(self, authorization=None, owner="alice"):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(os, "getuid", return_value=1200), mock.patch.object(os, "getgid", return_value=1200):
            return container_runner.command("a" * 32, owner, authorization or policy(), "openai", "example", "low", storage_root=root)

    def test_restricted_task_is_rootless_read_only_and_bounded(self):
        argv = self.build()
        joined = " ".join(argv)
        self.assertIn("--network none", joined)
        self.assertIn("--read-only", argv)
        self.assertIn("--cap-drop=all", argv)
        self.assertIn("no-new-privileges", argv)
        self.assertIn("--memory 8g", joined)
        self.assertNotIn("--privileged", argv)

    def test_denied_execution_disables_prime_tools(self):
        self.assertIn("--no-tools", self.build(policy(execution="deny")))

    def test_full_network_uses_rootless_user_mode_not_host(self):
        argv = self.build(policy(network="full", profile="network-operations"))
        joined = " ".join(argv)
        self.assertIn("slirp4netns", joined)
        self.assertNotIn("--network host", joined)

    def test_owner_cannot_escape_storage_root(self):
        with self.assertRaisesRegex(ValueError, "owner"):
            self.build(owner="../root")


if __name__ == "__main__":
    unittest.main()
