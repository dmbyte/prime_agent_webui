import fcntl
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import runtime_maintenance as maintenance


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'maintenance.lock'
        self.path.touch()
        patch=mock.patch.dict(os.environ,{'PRIME_MAINTENANCE_LOCK':str(self.path)})
        patch.start(); self.addCleanup(patch.stop)

    def test_shared_launchers_block_exclusive_update(self):
        with maintenance.admission(), maintenance.admission(), self.path.open('rb') as update:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(update,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with self.path.open('rb') as update:
            fcntl.flock(update,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_update_blocks_all_admission_before_function_runs(self):
        called=[]
        @maintenance.admitted
        def launch(): called.append(True)
        with self.path.open('rb') as update:
            fcntl.flock(update,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'maintenance is in progress'): launch()
        self.assertFalse(called)
        launch(); self.assertEqual(called,[True])

    def test_missing_and_symlink_fail_closed(self):
        self.path.unlink()
        with self.assertRaisesRegex(RuntimeError,'guard unavailable'):
            with maintenance.admission(): pass
        target=self.path.with_name('target'); target.touch(); self.path.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError,'guard unavailable'):
            with maintenance.admission(): pass

    def test_exception_releases_lease(self):
        with self.assertRaises(ValueError):
            with maintenance.admission(): raise ValueError()
        with self.path.open('rb') as update:
            fcntl.flock(update,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_every_producer_uses_admission(self):
        root=Path(__file__).parents[1]
        for file,method in [('dashboard/api_v2.py','def task_start_runtime'),
                            ('container/runner_launch.py','def main'),
                            ('container/kvm_broker.py','def _new_session'),
                            ('container/hosting_broker.py','def _start'),
                            ('dashboard/connection_native.py','def start'),
                            ('dashboard/connection_browser.py','def __init__')]:
            source=(root/file).read_text()
            self.assertRegex(source,r'@admitted\s+'+method)

    def test_guard_bootstrap_checks_idle_before_restarting_and_restores_web(self):
        root=Path(__file__).parents[1]
        source=(root/'openshell/install-update-guards.sh').read_text()
        pause=source.index('sudo -n systemctl stop nginx')
        self.assertIn("sudo -n systemctl stop nginx\nidle",source)
        self.assertLess(source.index("trap 'sudo -n systemctl start nginx' EXIT"),pause)
        self.assertLess(source.index('\nidle\n'),pause)
        self.assertLess(source.index('flock -n -x 8'),source.index('systemctl --user restart'))
        self.assertIn('sandbox\',\'list\',\'--all-workspaces',source)

    def test_installer_keeps_existing_lock_inode(self):
        source=(Path(__file__).parents[1]/'openshell/install.sh').read_text()
        self.assertIn('if ! sudo test -e /var/lib/prime-runner/openshell-maintenance.lock; then',source)
        self.assertIn('flock -n -x 8',source)
