import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('runner_recover_test', Path(__file__).parents[1]/'container/runner_recover.py')
recovery = importlib.util.module_from_spec(spec); spec.loader.exec_module(recovery)


class RecoveryOwnershipTests(unittest.TestCase):
    def test_web_owned_recovered_transcript_does_not_fail_runner_start(self):
        path = mock.Mock()
        path.lstat.return_value = SimpleNamespace(st_uid=os.geteuid()+1, st_mode=stat.S_IFREG | 0o660)
        with mock.patch.object(recovery.subprocess, 'run') as run:
            recovery.set_acl(['-m', 'fixture'], path)
            run.assert_not_called()

    def test_runner_owned_file_restores_acl_and_preserves_errors(self):
        path = mock.Mock()
        path.lstat.return_value = SimpleNamespace(st_uid=os.geteuid(), st_mode=stat.S_IFREG | 0o600)
        with mock.patch.object(recovery.subprocess, 'run') as run:
            recovery.set_acl(['-m', 'fixture'], path)
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs['check'])

    def test_symlinks_are_not_followed_and_acl_changes_are_not_recursive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'sub').mkdir(); (root/'sub/file').touch()
            (root/'link').symlink_to('/tmp', target_is_directory=True)
            with mock.patch.object(recovery.subprocess, 'run') as run:
                recovery.restore_tree(root, 'fixture')
                self.assertEqual(run.call_count, 2)
                self.assertTrue(all('-Rm' not in call.args[0] for call in run.call_args_list))
                self.assertTrue(all(not call.args[0][-1].endswith('/link') for call in run.call_args_list))


if __name__ == '__main__': unittest.main()
