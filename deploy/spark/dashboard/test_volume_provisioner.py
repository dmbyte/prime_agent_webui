import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'container'))
import volume_provisioner as vp


class VolumeProvisionerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root/'tasks'
        self.specs = vp.volume_specs('alice', self.workspace, self.root)
        for path in self.specs.values(): path.mkdir(mode=0o700, parents=True)
        self.records = {}; self.calls = []

    def docker(self, *args):
        self.calls.append(args); name = args[-1]
        if args[0] == 'create':
            self.records[name] = dict(Name=name, Driver='local', Labels=dict(vp.LABELS),
                Options=dict(type='none', o='bind', device=str(self.specs[name])))
            return SimpleNamespace(returncode=0, stdout=name, stderr='')
        if name not in self.records:
            return SimpleNamespace(returncode=1, stdout='', stderr='Error: no such volume')
        return SimpleNamespace(returncode=0, stdout=json.dumps([self.records[name]]), stderr='')

    def reconcile(self, body=None):
        with mock.patch.object(vp, 'docker', side_effect=self.docker):
            return vp.reconcile(body or {'owner': 'alice'}, self.workspace, os.getuid(), self.root)

    def test_new_owner_registers_all_volumes_with_admission_labels(self):
        self.assertEqual(self.reconcile(), {'ok': True, 'volumes': 8})
        self.assertEqual(set(self.records), set(self.specs))
        self.assertTrue(all(row['Labels'] == vp.LABELS for row in self.records.values()))

    def test_repeat_is_idempotent_and_never_deletes(self):
        self.reconcile(); self.calls.clear(); self.reconcile()
        self.assertTrue(all(call[0] == 'inspect' for call in self.calls))

    def test_untrusted_paths_and_owners_are_rejected_before_docker(self):
        for owner in ('../bob', '..', '/root', 'alice;id', 'a\nb'):
            with self.subTest(owner=owner), self.assertRaises(ValueError): self.reconcile({'owner': owner})
        with self.assertRaises(ValueError): self.reconcile({'owner': 'alice', 'device': '/root'})
        self.assertEqual(self.calls, [])

    def test_existing_other_owner_source_is_not_replaced(self):
        self.reconcile(); self.calls.clear()
        self.records['prime-alice-prime']['Options']['device'] = '/var/lib/prime-runner/users/bob/prime'
        with self.assertRaisesRegex(ValueError, 'conflicts'): self.reconcile()
        self.assertTrue(all(call[0] == 'inspect' for call in self.calls))

    def test_unadmitted_existing_volume_is_not_deleted_or_relabeled(self):
        self.reconcile(); self.calls.clear(); self.records['prime-alice-prime']['Labels'] = {}
        with self.assertRaisesRegex(ValueError, 'conflicts'): self.reconcile()
        self.assertTrue(all(call[0] == 'inspect' for call in self.calls))

    def test_symlink_source_is_rejected(self):
        path = self.specs['prime-alice-kvm']; path.rmdir(); path.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'): self.reconcile()
        self.assertEqual(self.calls, [])

    def test_world_accessible_or_missing_source_fails_before_any_registration(self):
        path = self.specs['prime-alice-kvm']; path.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'unsafe'): self.reconcile()
        path.rmdir()
        with self.assertRaises(OSError): self.reconcile()
        self.assertEqual(self.calls, [])

    def test_wrong_source_uid_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            vp.validate_source(self.workspace/'alice', os.getuid()+1)

    def test_docker_failure_is_not_treated_as_missing_volume(self):
        with mock.patch.object(vp, 'docker', return_value=SimpleNamespace(returncode=1, stderr='daemon unavailable')) as command:
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                vp.reconcile({'owner': 'alice'}, self.workspace, os.getuid(), self.root)
            self.assertEqual(command.call_count, 1)

    def test_nonrunner_peer_cannot_provision(self):
        handler = object.__new__(vp.Handler)
        handler.connection = mock.Mock()
        handler.connection.getsockopt.return_value = struct.pack('3i', 1, 1001, 1)
        handler.server = SimpleNamespace(runner_uid=995, workspace_root=self.workspace)
        handler.rfile = io.BytesIO(b'{"owner":"alice"}\n'); handler.wfile = io.BytesIO()
        with mock.patch.object(vp.socket, 'SO_PEERCRED', 17, create=True), mock.patch.object(vp, 'reconcile') as reconcile:
            handler.handle(); reconcile.assert_not_called()
        self.assertEqual(handler.wfile.getvalue(), b'')

    def test_launcher_provisions_after_gateway_and_before_sandbox_creation(self):
        source = (Path(__file__).parents[1]/'container/runner_launch.py').read_text()
        self.assertLess(source.index('stage("Checking model gateway")'), source.index('volume_provisioner.provision'))
        self.assertLess(source.index('volume_provisioner.provision'), source.index('stage("Creating OpenShell sandbox")'))
        runtime = (Path(__file__).parents[1]/'container/openshell_runner.py').read_text()
        self.assertNotIn('prime-volume-provisioner-v1', runtime)

    def test_service_has_no_task_control_api_and_fixed_entrypoint(self):
        source = (Path(__file__).parents[1]/'systemd/prime-volume-provisioner.service').read_text()
        self.assertIn('ProtectSystem=strict', source)
        self.assertIn('RestrictAddressFamilies=AF_UNIX', source)
        self.assertNotIn('ReadWritePaths=', source)


if __name__ == '__main__': unittest.main()
