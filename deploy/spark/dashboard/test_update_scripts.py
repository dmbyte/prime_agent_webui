#!/usr/bin/env python3
import unittest
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class UpdateScriptTests(unittest.TestCase):
    def updater(self):
        return (ROOT / 'deploy/spark/update/update-prime-agent.sh').read_text()

    def updater_function(self, name):
        return name+'() {'+self.updater().split(name+'() {', 1)[1].split('\n}\n', 1)[0]+'\n}\n'

    def test_prime_version_accepts_migration_noise_but_not_ambiguous_or_failed_output(self):
        function = self.updater_function('cli_version')
        for output, code, expected in (
            ('0.10.2', 0, '0.10.2'),
            ('Downloading Rust v0.10.2...\nMigration complete.\n0.10.2', 0, '0.10.2'),
            ('prime-agent 0.10.2\n', 0, '0.10.2'),
            ('0.10.2', 1, None),
            ('Download failed for v0.10.2', 0, None),
            ('0.9.8\n0.10.2', 0, None),
            ('0.10.2', 124, None),
        ):
            with self.subTest(output=output, code=code):
                script = 'set -e\nruntime=/unused\nfixture_output=$1; fixture_code=$2\ntimeout(){ printf "%s\\n" "$fixture_output" >&2; return "$fixture_code"; }\n'
                result = subprocess.run(['bash', '-c', script+function+'value=$(cli_version); printf "%s" "$value"', 'test', output, str(code)], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, expected is not None)
                if expected: self.assertEqual(result.stdout, expected)

    def test_prime_package_version_checks_identity_without_launching_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)/'lib/node_modules/prime-agent/package.json'
            package.parent.mkdir(parents=True)
            for name, version, valid in (('prime-agent','0.10.2',True), ('wrong','0.10.2',False), ('prime-agent','garbage',False)):
                package.write_text(json.dumps(dict(name=name, version=version)))
                result = subprocess.run(['bash','-c','runtime=$1\n'+self.updater_function('package_version')+'package_version', 'test', directory], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, valid)

    def test_prime_failed_status_names_phase_and_preserves_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = 'status_dir=$1; status_file="$status_dir/agent.json"; phase="checksum verification"; failure_reason=""; download_dir=""\n'
            script = setup+self.updater_function('write_status')+self.updater_function('finish')+'trap finish EXIT\nexit 23\n'
            result = subprocess.run(['bash','-c',script,'test',directory], capture_output=True, text=True)
            self.assertEqual(result.returncode, 23)
            status = json.loads((Path(directory)/'agent.json').read_text())
            self.assertEqual(status['result'], 'failed')
            self.assertEqual(status['exitCode'], 23)
            self.assertIn('checksum verification', status['reason'])

    def test_prime_update_locks_before_status_and_checks_package_and_cli(self):
        script = self.updater()
        self.assertLess(script.index('flock -n 9'), script.index('write_status running 0'))
        self.assertIn('if [[ $before != "$release_version" ]]', script)
        self.assertIn('[[ $installed == "$release_version" ]]', script)
        self.assertIn('if [[ $after != "$release_version" ]]', script)
        self.assertIn('timeout 180s', script)
        self.assertNotIn('systemctl', script)

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
        for helper in ("task_common.py", "openshell_runner.py", "model_gateway.py", "inference_policy.py", "runner_broker.py"):
            self.assertIn(f"deploy/spark/container/{helper}", script)
        self.assertIn('/usr/local/libexec/prime-approve-inference-route', script)

    def test_installer_adds_policy_helper_without_approving_routes(self):
        script = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        self.assertIn('deploy/spark/container/inference_policy.py', script)
        self.assertIn('/usr/local/libexec/prime-approve-inference-route', script)
        self.assertNotIn('--confirm-no-training', script)

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

    def test_openshell_install_and_volume_admission_are_pinned(self):
        installer = (ROOT / "deploy/spark/openshell/install.sh").read_text()
        config = (ROOT / "deploy/spark/openshell/gateway.toml").read_text()
        volumes = (ROOT / "deploy/spark/openshell/provision-volumes.sh").read_text()
        self.assertIn("version=0.1.5", installer)
        self.assertIn("ae381703f78061141bbac44aa85fb7d9856cb567d2ab2b4306318365f5466ac5", installer)
        unit = (ROOT / 'deploy/spark/systemd/prime-dashboard-api.service').read_text()
        self.assertIn('PRIME_OPENSHELL_VERSION=0.1.5', unit)
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

    def test_openshell_updater_waits_before_first_sandbox_inventory(self):
        script = (ROOT / 'deploy/spark/update/update-openshell.sh').read_text()
        self.assertLess(script.index('\nverify_gateway\n'), script.index('sandbox_ids=$(openshell'))

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
