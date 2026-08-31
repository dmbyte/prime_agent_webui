#!/usr/bin/env python3
import unittest

from task_policy import authorize_task


class TaskPolicyTests(unittest.TestCase):
    def test_user_defaults_are_restricted_and_bounded(self):
        policy = authorize_task({}, "user")
        self.assertEqual(policy["networkMode"], "restricted")
        self.assertFalse(policy["executionApproved"])
        self.assertEqual(policy["limits"]["memoryGiB"], 8)

    def test_user_cannot_request_private_network_or_overrides(self):
        with self.assertRaisesRegex(ValueError, "power-user"):
            authorize_task({"networkMode": "full", "executionMode": "task"}, "user")
        with self.assertRaisesRegex(ValueError, "overrides"):
            authorize_task({"limits": {"memoryGiB": 4}}, "user")

    def test_power_user_can_use_full_network_with_execution(self):
        policy = authorize_task({"profile": "network-operations", "networkMode": "full", "executionMode": "task", "limits": {"memoryGiB": 16, "cpus": 8, "runtimeMinutes": 120}}, "power_user", task_execution_confirmed=True, network_confirmed=True)
        self.assertTrue(policy["executionApproved"])
        self.assertEqual(policy["networkMode"], "full")

    def test_full_network_rejects_execution_denial(self):
        with self.assertRaisesRegex(ValueError, "execution approval"):
            authorize_task({"networkMode": "full", "executionMode": "deny"}, "admin", network_confirmed=True)

    def test_only_admin_gets_package_override(self):
        self.assertFalse(authorize_task({"packageOverride": True}, "power_user")["packageOverride"])
        self.assertTrue(authorize_task({"packageOverride": True}, "admin")["packageOverride"])

    def test_local_paths_require_role_and_per_task_confirmation(self):
        with self.assertRaisesRegex(ValueError, "power-user"):
            authorize_task({"localPaths": ["/home/alice/project"]}, "user")
        with self.assertRaisesRegex(ValueError, "local-file approval"):
            authorize_task({"localPaths": ["/home/alice/project"]}, "power_user")
        result = authorize_task({"localPaths": ["/home/alice/project"]}, "power_user", files_confirmed=True)
        self.assertEqual(result["localPaths"], ["/home/alice/project"])

    def test_local_paths_are_absolute_bounded_and_deduplicated(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            authorize_task({"localPaths": ["relative/project"]}, "admin", files_confirmed=True)
        values = [f"/home/alice/project-{index}" for index in range(9)]
        with self.assertRaisesRegex(ValueError, "No more than"):
            authorize_task({"localPaths": values}, "admin", files_confirmed=True)
        result = authorize_task({"localPaths": ["/home/alice/project", "/home/alice/project"]}, "admin", files_confirmed=True)
        self.assertEqual(result["localPaths"], ["/home/alice/project"])


if __name__ == "__main__":
    unittest.main()
