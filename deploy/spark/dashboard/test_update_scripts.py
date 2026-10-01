#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class UpdateScriptTests(unittest.TestCase):
    def test_prime_agent_updater_captures_cli_version_from_stderr(self):
        script = (ROOT / "deploy/spark/update/update-prime-agent.sh").read_text()
        self.assertIn('before=$(prime-agent --version 2>&1)', script)
        self.assertIn('after=$(prime-agent --version 2>&1)', script)

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
        self.assertIn('deploy/spark/container/runner_recover.py', script)
        self.assertIn('/usr/local/libexec/prime-runner-recover', script)

    def test_webui_update_installs_privileged_runner_dependencies(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        for helper in ("task_common.py", "openshell_runner.py", "model_gateway.py", "runner_broker.py"):
            self.assertIn(f"deploy/spark/container/{helper}", script)

    def test_webui_update_activates_release_pinned_openshell_images(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        self.assertIn('"$repo/deploy/spark/openshell/install.sh"', script)
        self.assertIn("PRIME_RUNNER_WORKSPACE_ROOT", script)

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
        self.assertIn('rsync -a --ignore-existing', script)
        self.assertIn('deploy/spark/prime/AGENTS.managed.md', script)
        self.assertIn('pre-prime-managed-', script)
        self.assertIn("source_expiry > target_expiry", script)
        self.assertIn("Retained the gateway Codex credential", script)

    def test_openshell_012_install_and_volume_admission_are_pinned(self):
        installer = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        config = (ROOT / "deploy/spark/openshell/gateway.toml").read_text()
        volumes = (ROOT / "deploy/spark/openshell/provision-volumes.sh").read_text()
        self.assertIn("version=0.1.2", installer)
        self.assertIn("openshell-gateway config preflight", installer)
        self.assertIn("version = 2", config)
        self.assertIn('compute_driver = "docker"', config)
        self.assertIn("allow_driver_config = true", config)
        self.assertIn("resource_admission", config)
        self.assertNotIn("grpc_endpoint =", config)
        self.assertIn("openshell.ai/sandbox-attachable-workspace=default", volumes)
        self.assertIn("openshell.ai/sandbox-attachable=true", volumes)

    def test_openshell_updater_reports_effective_version_after_manual_migration(self):
        script = (ROOT / "deploy/spark/update/update-openshell.sh").read_text()
        self.assertIn('set_dashboard_version "$installed"', script)
        self.assertIn("zz-openshell-version.conf", script)

    def test_volume_provisioning_refreshes_only_managed_agent_policy(self):
        script = (ROOT / "deploy/spark/openshell/provision-volumes.sh").read_text()
        self.assertIn('deploy/spark/prime/AGENTS.managed.md', script)
        self.assertIn("DGX Spark Prime Agent operating policy", script)
        self.assertIn('pre-prime-managed-', script)

    def test_broker_unit_allows_only_prime_agent_home_workspace(self):
        unit = (ROOT / "deploy/spark/systemd/prime-runner-broker.service").read_text()
        self.assertIn("PRIME_RUNNER_WORKSPACE_ROOT=/home/@WEB_OWNER@/prime-agent/tasks", unit)
        self.assertIn("/home/@WEB_OWNER@/prime-agent", unit)
        self.assertNotIn("InaccessiblePaths=/home", unit)

    def test_broker_repairs_interrupted_task_acls_before_start(self):
        unit = (ROOT / "deploy/spark/systemd/prime-runner-broker.service").read_text()
        recovery = (ROOT / "deploy/spark/container/runner_recover.py").read_text()
        self.assertIn("ExecStartPre=/usr/bin/python3 /usr/local/libexec/prime-runner-recover", unit)
        self.assertIn('WRITABLE_DIRS = ("sessions", "trash", "project-sources", "skills")', recovery)
        self.assertIn("m::--x", recovery)
        self.assertIn("m::rwX", recovery)

    def test_openshell_install_moves_stale_user_broker_units_to_recovery(self):
        script = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        self.assertIn("stale-openshell-user-units-", script)
        self.assertIn("prime-model-gateway.service prime-runner-broker.service", script)
        self.assertIn('mv "$stale_path" "$stale_unit_backup/"', script)


if __name__ == "__main__":
    unittest.main()
