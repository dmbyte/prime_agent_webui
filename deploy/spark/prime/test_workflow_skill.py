import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SCRIPTS = Path(__file__).parent/'skills/prime-workflows/scripts'
spec = importlib.util.spec_from_file_location('prime_workflows', SCRIPTS/'prime_workflows.py')
workflows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflows)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.w = workflows.CodingWorkflow(self.root)

    def test_real_command_result_hash_and_no_replay(self):
        command = [sys.executable, '-c', "from pathlib import Path; Path('out').write_text('ok'); print('done')"]
        result = self.w.run('test', command, artifacts=['out'])
        self.assertEqual(result['state'], 'passed')
        self.assertEqual(result['exitCode'], 0)
        self.assertEqual(result['artifacts'][0]['sha256'], hashlib.sha256(b'ok').hexdigest())
        (self.root/'out').unlink()
        self.assertEqual(self.w.run('test', command, artifacts=['out']), result)
        self.assertFalse((self.root/'out').exists())
        with self.assertRaises(ValueError): self.w.run('test', [sys.executable, '-V'])
        self.assertEqual((self.root/'.prime-workflows/test.json').stat().st_mode & 0o777, 0o600)

    def test_failed_missing_artifact_and_spawn_failure(self):
        self.assertEqual(self.w.run('fail', [sys.executable, '-c', 'raise SystemExit(2)'])['state'], 'failed')
        self.assertEqual(self.w.run('missing', [sys.executable, '-V'], artifacts=['missing'])['state'], 'artifact-error')
        self.assertEqual(self.w.run('spawn', ['/no/such/executable'])['state'], 'not-started')

    def test_denied_group_signal_preserves_completed_result(self):
        with mock.patch.object(workflows.os, 'killpg', side_effect=PermissionError()):
            result = self.w.run('denied', [sys.executable, '-c', "print('ok')"])
        self.assertEqual(result['state'], 'passed')
        self.assertFalse(result['cleanupVerified'])
        self.assertTrue(result['cleanup']['leaderExited'])
        self.assertEqual(self.w.receipt('denied'), result)

    def test_denied_group_signal_timeout_kills_only_known_child(self):
        with mock.patch.object(workflows.os, 'killpg', side_effect=PermissionError()):
            result = self.w.run('denied-timeout', [sys.executable, '-c', 'import time; time.sleep(30)'], timeout=1)
        self.assertEqual(result['state'], 'timed-out')
        self.assertFalse(result['cleanupVerified'])
        self.assertTrue(result['cleanup']['leaderExited'])

    def test_fully_denied_cleanup_is_bounded_and_not_claimed_successful(self):
        process = mock.Mock(pid=123)
        process.poll.return_value = None
        process.kill.side_effect = PermissionError()
        process.wait.side_effect = subprocess.TimeoutExpired('fixture', 2)
        with mock.patch.object(workflows.os, 'killpg', side_effect=PermissionError()):
            result = self.w._stop(process)
        self.assertEqual(result, {'groupStopped': False, 'leaderExited': False})
        process.wait.assert_called_once_with(timeout=2)

    def test_output_bounded_and_secrets_not_inherited(self):
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_TOKEN': 'secret', 'OPENAI_API_KEY': 'secret'}):
            result = self.w.run('bounded', [sys.executable, '-c',
                "import os; assert 'PRIME_CONNECTION_TOKEN' not in os.environ; assert 'OPENAI_API_KEY' not in os.environ; print('x'*100000)"])
        self.assertEqual(result['state'], 'passed')
        self.assertTrue(result['outputTruncated'])
        self.assertEqual(len(result['output']), 65536)

    def test_timeout_kills_process_group_and_never_retries(self):
        command = [sys.executable, '-c',
                   "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',\"import time; from pathlib import Path; time.sleep(2); Path('late').touch()\"]); time.sleep(30)"]
        result = self.w.run('timeout', command, timeout=1)
        self.assertEqual(result['state'], 'timed-out')
        self.assertFalse(result['retryAllowed'])
        # Independent wait command verifies the descendant cannot publish later.
        subprocess.run([sys.executable, '-c', 'import time; time.sleep(1.3)'], check=True)
        self.assertFalse((self.root/'late').exists())
        self.assertEqual(self.w.run('timeout', command, timeout=1), result)

    def test_restart_with_inflight_record_is_unknown_without_launch(self):
        command = [sys.executable, '-V']
        self.w.begin('interrupted', ['command', command, None, 120, []])
        restored = workflows.CodingWorkflow(self.root)
        with mock.patch.object(workflows.subprocess, 'Popen') as launch:
            result = restored.run('interrupted', command)
        self.assertEqual(result['state'], 'unknown'); launch.assert_not_called()

    def test_invalid_paths_symlinks_fifo_and_concurrent_step_rejected(self):
        (self.root/'escape').symlink_to(self.root.parent, target_is_directory=True)
        for path in ('../out', '/tmp/out', 'escape/out', '.'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.w.path(path)
        os.mkfifo(self.root/'fifo')
        with self.assertRaises(ValueError): self.w.artifacts(['fifo'])
        with self.w.lock('busy'), self.assertRaises(BlockingIOError): self.w.receipt('busy')
        for timeout in (True, 0, float('inf'), float('nan'), 3601):
            with self.assertRaises(ValueError): self.w.run('invalid', ['true'], timeout=timeout)

    def test_preview_persists_lan_address_and_lost_reply_is_not_retried(self):
        (self.root/'hosted/demo').mkdir(parents=True)
        host = mock.Mock()
        host.static.return_value = {'id': 'h_fixture', 'url': 'http://192.168.1.10:18080', 'scope': 'project'}
        result = self.w.preview('preview', host, name='demo', directory='hosted/demo')
        self.assertEqual(result['state'], 'published')
        self.assertFalse(result['clientReachabilityVerified'])
        self.w.preview('preview', host, name='demo', directory='hosted/demo')
        self.assertEqual(host.static.call_count, 1)
        host.static.side_effect = TimeoutError()
        self.assertEqual(self.w.preview('lost', host, name='demo2', directory='hosted/demo')['state'], 'unknown')
        self.w.preview('lost', host, name='demo2', directory='hosted/demo')
        self.assertEqual(host.static.call_count, 2)
        with self.assertRaises(ValueError): self.w.preview('unsafe', host, name='root', directory='.prime-workflows')

    def test_preview_invalid_address_stops_without_duplicate_service(self):
        (self.root/'hosted/demo').mkdir(parents=True)
        for i, url in enumerate(('http://127.0.0.1:8000', 'http://user:secret@192.168.1.9', 'https://example.com')):
            host = mock.Mock(); host.static.return_value = {'url': url}
            self.assertEqual(self.w.preview('bad'+str(i), host, name='x', directory='hosted/demo')['state'], 'unknown')


class BMCWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.b = workflows.BMCWorkflow(self.root)
        self.client = mock.Mock(connection_id='c_'+'a'*32, session_id='pc-'+'b'*16)
        self.cls = mock.Mock(return_value=self.client)
        self.cls.open.return_value = self.client
        self.module = types.ModuleType('bmc_html5_kvm')
        self.module.PrivateKVMClient = self.cls
        self.module._connection_id = lambda value: value
        self.module._connection_call = mock.Mock(return_value={'systemIds': ['1']})
        patch = mock.patch.dict(sys.modules, {'bmc_html5_kvm': self.module})
        patch.start(); self.addCleanup(patch.stop)

    def test_pending_approval_reuses_id_then_no_replay_after_ack(self):
        self.b.open_console('console', self.client.connection_id)
        self.client.input.side_effect = [{'approvalRequired': True, 'approvalId': 'a_'+'c'*64},
                                        {'actionReceipt': {'state': 'acknowledged'}}]
        first = self.b.key('boot', 'console', 'f9')
        self.assertEqual(first['state'], 'approval-required')
        second = self.b.key('boot', 'console', 'f9')
        self.assertEqual(first['requestId'], second['requestId'])
        self.assertEqual(second['state'], 'acknowledged')
        self.b.key('boot', 'console', 'f9')
        self.assertEqual(self.client.input.call_count, 2)
        self.assertEqual(self.client.input.call_args_list[0], self.client.input.call_args_list[1])
        with self.assertRaises(ValueError): self.b.key('boot', 'console', 'f10')

    def test_lost_ack_unknown_no_replay_and_read_only_receipt(self):
        self.b.open_console('console', self.client.connection_id)
        self.client.input.side_effect = TimeoutError('must not appear in record')
        result = self.b.key('boot', 'console', 'f9')
        self.assertEqual(result['state'], 'unknown')
        self.b.key('boot', 'console', 'f9')
        self.assertEqual(self.client.input.call_count, 1)
        self.b.action_receipt('boot')
        self.cls.action_receipt.assert_called_once_with(self.client.connection_id, result['requestId'])
        self.assertNotIn('must not appear', json.dumps(result))

    def test_open_loss_never_reopens_or_sends_input(self):
        self.cls.open.side_effect = TimeoutError()
        self.assertEqual(self.b.open_console('console', self.client.connection_id)['state'], 'unknown')
        self.b.open_console('console', self.client.connection_id)
        self.cls.open.assert_called_once()
        with self.assertRaises(ValueError): self.b.key('boot', 'console', 'f9')
        self.client.input.assert_not_called()

    def test_inspection_uses_only_fixed_operation_and_connection(self):
        self.b.inspect(self.client.connection_id, system_id='1')
        self.module._connection_call.assert_called_once_with('call', connection=self.client.connection_id,
                                              operation='redfish.installation', arguments={'systemId': '1'})


if __name__ == '__main__':
    unittest.main()
