import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('runtime_inputs_api', Path(__file__).with_name('api_v2.py'))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class RuntimeInputTests(unittest.TestCase):
    def test_acl_targets_sandbox_uid_not_host_supplementary_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source'; path.write_text('fixture')
            with mock.patch.object(api, 'container_mode', return_value=True), mock.patch.object(api.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid()+1)), mock.patch.object(api.subprocess, 'run') as run:
                api.grant_runtime_access(path)
                args = run.call_args.args[0]
                self.assertIn(f'u:{os.getuid()+1}:r--,m::r--', args)
                self.assertTrue(args[-1].startswith('/proc/self/fd/'))
                self.assertTrue(run.call_args.kwargs['pass_fds'])
                self.assertTrue(run.call_args.kwargs['check'])

    def test_acl_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'real').touch(); (root/'link').symlink_to(root/'real')
            with mock.patch.object(api, 'container_mode', return_value=True), mock.patch.object(api.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid()+1)), mock.patch.object(api.subprocess, 'run') as run:
                with self.assertRaises(OSError): api.grant_runtime_access(root/'link')
                run.assert_not_called()

    def test_existing_project_sources_have_access_repaired_without_recopy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input.txt'; source.write_text('private fixture')
            project = 'p_'+'a'*24
            with mock.patch.object(api, 'project_source_root', return_value=root/'sources'), mock.patch.object(api, 'upload_path', return_value=source), mock.patch.object(api, 'grant_runtime_access') as grant, mock.patch.object(api, 'container_mode', return_value=False):
                rows = api.sync_project_sources(project, 'alice', ['file'])
                grant.reset_mock()
                with mock.patch.object(api.shutil, 'copy2') as copy:
                    api.sync_project_sources(project, 'alice', ['file'])
                    copy.assert_not_called()
                grant.assert_any_call(root/'sources'/project, directory=True)
                grant.assert_any_call(root/'sources'/project/'01-input.txt')
                self.assertIn('/project-sources/'+project, rows[0]['path'])
                self.assertEqual((root/'sources'/project/'01-input.txt').read_text(), 'private fixture')

    def fixture(self, root):
        sid = 'recovered-'+'a'*32
        path = root/'sessions'/f'{sid}.jsonl'; path.parent.mkdir()
        records = [{'type':'session','id':sid,'timestamp':'2026-10-24T12:00:00Z'},
                   {'type':'message','message':{'role':'user','content':[{'type':'text','text':'Preserve this exact prompt.'}]}}]
        path.write_text(''.join(json.dumps(row)+'\n' for row in records))
        meta = {'conversations': {sid: {'owner':'alice','recoveredFromTask':'a'*32}}}
        return sid, path, meta

    def test_legacy_recovery_preserves_messages_and_exact_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sid, path, meta = self.fixture(root); original = path.read_bytes()
            with mock.patch.object(api, 'metadata', return_value=meta), mock.patch.object(api, 'session_root', return_value=root/'sessions'), mock.patch.object(api, 'session_trash', return_value=root/'trash'), mock.patch.object(api, 'container_mode', return_value=True), mock.patch.object(api, 'grant_runtime_access') as grant:
                api.prepare_recovered_session(sid, 'alice')
                api.prepare_recovered_session(sid, 'alice')
                self.assertEqual(json.loads(path.read_text().splitlines()[0])['cwd'], '/project')
                self.assertEqual(path.read_bytes().partition(b'\n')[2], original.partition(b'\n')[2])
                backups = list((root/'trash/recovery-format-backups').glob('*.jsonl'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), original)
                grant.assert_any_call(path, writable=True)
                # Leave v1 for the installed runtime's own entry migration.
                self.assertNotIn('version', json.loads(path.read_text().splitlines()[0]))

    def test_recovery_rejects_other_owner_and_running_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sid, path, meta = self.fixture(root); original = path.read_bytes()
            with mock.patch.object(api, 'metadata', return_value=meta), mock.patch.object(api, 'session_root', return_value=root/'sessions'):
                with self.assertRaises(ValueError): api.prepare_recovered_session(sid, 'bob')
                with mock.patch.dict(api.TASKS, {'fixture': {'sessionId':sid, 'status':'running'}}):
                    with self.assertRaisesRegex(ValueError, 'active task'): api.prepare_recovered_session(sid, 'alice')
            self.assertEqual(path.read_bytes(), original)

    def test_ordinary_native_session_is_not_rewritten(self):
        with mock.patch.object(api, 'metadata', return_value={'conversations': {'native-session':{'owner':'alice'}}}), mock.patch.object(api.legacy, 'session_path') as path:
            api.prepare_recovered_session('native-session', 'alice')
            path.assert_not_called()

    def test_recovered_error_has_native_usage_without_fabricated_tokens(self):
        records = [{'type':'session','id':'fixture'}, {'type':'model_change','provider':'spark-qwen','modelId':'fixture-model'},
                   {'type':'message','message':{'role':'assistant','content':[{'type':'text','text':'Startup failed.'}]}}]
        with mock.patch.object(api, 'container_mode', return_value=True):
            api.normalize_recovery_entries(records)
        message = records[2]['message']
        self.assertEqual(records[0]['cwd'], '/project')
        self.assertEqual(message['usage']['input'], 0)
        self.assertEqual(message['usage']['cost']['total'], 0)
        self.assertEqual(message['model'], 'fixture-model')
        self.assertEqual(message['content'][0]['text'], 'Startup failed.')
        original = json.dumps(records)
        api.normalize_recovery_entries(records)
        self.assertEqual(json.dumps(records), original)


if __name__ == '__main__': unittest.main()
