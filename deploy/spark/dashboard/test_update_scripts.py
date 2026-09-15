#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class UpdateScriptTests(unittest.TestCase):
    def test_webui_update_installs_shared_task_helper(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        self.assertIn('deploy/spark/container/task_common.py', script)
        self.assertIn('"$live/task_common.py"', script)
        self.assertIn('/usr/local/lib/prime-runner/', script)

    def test_webui_update_installs_privileged_runner_launcher(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        self.assertIn('deploy/spark/container/runner_launch.py', script)
        self.assertIn('/usr/local/libexec/prime-runner-launch', script)
        self.assertIn('deploy/spark/container/runner_client.py', script)
        self.assertIn('/usr/local/libexec/prime-runner-client', script)

    def test_webui_update_installs_privileged_runner_dependencies(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        for helper in ("task_common.py", "openshell_runner.py", "model_gateway.py", "runner_broker.py"):
            self.assertIn(f"deploy/spark/container/{helper}", script)

    def test_webui_update_refreshes_runner_unit_and_home_workspace_volume(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        provision = (ROOT / "deploy/spark/openshell/provision-volumes.sh").read_text()
        self.assertIn("PRIME_RUNNER_WORKSPACE_ROOT", script)
        self.assertIn("prime-agent/tasks", script)
        self.assertIn("prime-runner-broker.service", script)
        self.assertIn("provision-volumes.sh", script)
        self.assertIn("/var/lib/prime-runner/users/${owner}/workspace", provision)
        self.assertIn("--ignore-existing --exclude uploads", provision)
        self.assertIn('setfacl -Rm "u:${USER}:rwX,g:prime-web:rwX', provision)

    def test_openshell_install_uses_home_task_workspace(self):
        script = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        self.assertIn("PRIME_RUNNER_WORKSPACE_ROOT", script)
        self.assertIn("prime-agent/tasks", script)
        self.assertIn("owner_workspace=\"${workspace_root}/${USER}\"", script)

    def test_broker_unit_allows_only_prime_agent_home_workspace(self):
        unit = (ROOT / "deploy/spark/systemd/prime-runner-broker.service").read_text()
        self.assertIn("PRIME_RUNNER_WORKSPACE_ROOT=/home/@WEB_OWNER@/prime-agent/tasks", unit)
        self.assertIn("/home/@WEB_OWNER@/prime-agent", unit)
        self.assertNotIn("InaccessiblePaths=/home", unit)

    def test_openshell_install_moves_stale_user_broker_units_to_recovery(self):
        script = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        self.assertIn("stale-openshell-user-units-", script)
        self.assertIn("prime-model-gateway.service prime-runner-broker.service", script)
        self.assertIn('mv "$stale_path" "$stale_unit_backup/"', script)


if __name__ == "__main__":
    unittest.main()
