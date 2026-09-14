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

    def test_openshell_install_moves_stale_user_broker_units_to_recovery(self):
        script = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        self.assertIn("stale-openshell-user-units-", script)
        self.assertIn("prime-model-gateway.service prime-runner-broker.service", script)
        self.assertIn('mv "$stale_path" "$stale_unit_backup/"', script)


if __name__ == "__main__":
    unittest.main()
