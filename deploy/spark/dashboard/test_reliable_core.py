"""Real HTTP auth boundary and local fault-injection; never production state."""
import http.client
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import api_v2 as api
import auth


class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.users = {'users': {'alice': {'role': 'user', 'enabled': True},
                                'bob': {'role': 'admin', 'enabled': True}}}
        now = time.time()
        patches = [mock.patch.object(auth, 'load_users', side_effect=lambda: self.users),
                   mock.patch.dict(auth.SESSIONS, {'alice-session': {'user': 'alice', 'role': 'admin',
                       'csrf': 'alice-csrf', 'seen': now, 'persisted': now, 'expires': now+600}}, clear=True)]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)
        self.auth_server = auth.ThreadingHTTPServer(('127.0.0.1', 0), auth.Handler)
        self.server = api.legacy.BoundedThreadingHTTPServer(('127.0.0.1', 0), api.Handler)
        for server in (self.auth_server, self.server):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        original = http.client.HTTPConnection
        def local_connection(host, port=None, **kw):
            return original(host, self.auth_server.server_port if port == 8764 else port, **kw)
        patch = mock.patch.object(api.http.client, 'HTTPConnection', side_effect=local_connection)
        patch.start(); self.addCleanup(patch.stop)
        self.connection = original

    def request(self, path, *, method='GET', cookie='prime_session=alice-session', extra=None):
        connection = self.connection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Cookie': cookie, 'X-Prime-User': 'bob', 'X-Prime-Role': 'admin',
                   'Origin': next(iter(api.legacy.ALLOWED_ORIGINS)), 'Content-Type': 'application/json',
                   'X-Prime-CSRF': 'alice-csrf'} | (extra or {})
        connection.request(method, path, body='{}' if method == 'POST' else None, headers=headers)
        response = connection.getresponse(); result = response.status, json.loads(response.read())
        connection.close(); return result

    def test_forged_headers_and_missing_session_cannot_read(self):
        for path in ('/api/state', '/api/tasks', '/api/activity', '/api/telemetry'):
            self.assertEqual(self.request(path, cookie='')[0], 401)
            self.assertEqual(self.request(path, cookie='prime_session=forged')[0], 401)

    def test_cookie_identity_overrides_forged_owner_and_stale_role(self):
        with mock.patch.object(api, 'task_snapshot', return_value=[]) as snapshot:
            self.assertEqual(self.request('/api/tasks')[0], 200)
            snapshot.assert_called_once_with('alice')
        with mock.patch.object(api, 'admin_status') as admin:
            self.assertNotEqual(self.request('/api/admin')[0], 200)
            admin.assert_not_called()

    def test_disabled_and_deleted_accounts_denied(self):
        self.users['users']['alice']['enabled'] = False
        self.assertEqual(self.request('/api/tasks')[0], 401)
        del self.users['users']['alice']
        self.assertEqual(self.request('/api/tasks')[0], 401)

    def test_csrf_bound_to_session_not_attacker_cookie(self):
        with mock.patch.object(api, 'task_start_runtime') as start:
            status, _ = self.request('/api/tasks/start', method='POST',
                cookie='prime_session=alice-session; prime_csrf=forged', extra={'X-Prime-CSRF': 'forged'})
            self.assertEqual(status, 403); start.assert_not_called()

    def test_health_discloses_only_aggregate_liveness(self):
        with mock.patch.dict(api.TASKS, {'x': {'owner': 'private-owner', 'status': 'running'}}, clear=True):
            self.assertEqual(self.request('/api/health', cookie=''), (200, {'ok': True, 'activeTasks': 1}))

    def test_auth_outage_fails_closed(self):
        with mock.patch.object(api.http.client, 'HTTPConnection', return_value=mock.Mock(
                request=mock.Mock(side_effect=OSError('private')))):
            status, body = self.request('/api/tasks')
        self.assertEqual(status, 503); self.assertNotIn('private', json.dumps(body))

    def test_nonadmin_cannot_use_legacy_host_controls(self):
        self.assertNotEqual(self.request('/api/activity')[0], 200)
        self.assertEqual(self.request('/api/activity/stop', method='POST')[0], 403)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.tid = 'a'*32
        patches = [mock.patch.object(api, 'META', self.root/'metadata.json'),
                   mock.patch.object(api, 'TASK_LOGS', self.root/'logs'),
                   mock.patch.object(api, 'LEDGER', self.root/'ledger.jsonl'),
                   mock.patch.object(api, 'session_root', return_value=self.root/'sessions'),
                   mock.patch.object(api, 'session_stems', return_value=set()),
                   mock.patch.object(api, 'grant_runtime_access'),
                   mock.patch.object(api.legacy, 'audit'),
                   mock.patch.object(api, 'revoke_connection_task'),
                   mock.patch.dict(api.TASKS, {}, clear=True)]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)
        self.task = {'id': self.tid, 'owner': 'alice', 'status': 'running', 'started': api.now_iso(),
                     'startedEpoch': time.time(), 'submittedMessage': 'Synthetic original request',
                     'provider': 'spark-qwen', 'model': 'qwen3.8-flash-next', '_durable': True}
        api.TASKS[self.tid] = self.task

    def test_checkpoint_excludes_credentials_tool_input_and_private_reasoning(self):
        self.task.update(connectionToken='SECRET', authorization={'token':'SECRET'},
                         process=object(), liveLog=['SECRET'], thinkingText='SECRET')
        api.checkpoint_task(self.task)
        raw = api.META.read_text(); self.assertNotIn('SECRET', raw)
        self.assertEqual(api.metadata()['tasks'][self.tid]['prompt'], 'Synthetic original request')
        self.assertEqual(api.META.stat().st_mode & 0o777, 0o600)

    def test_restart_preserves_request_and_unknown_step_without_replay(self):
        api.apply_task_event(self.tid, {'type':'tool_execution_start', 'toolName':'ipython', 'toolCallId':'step-1'})
        api.TASKS.clear()
        with mock.patch.object(api.subprocess, 'Popen') as spawn:
            api.restore_task_checkpoints(); spawn.assert_not_called()
        task = api.TASKS[self.tid]
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['toolSteps'][0]['state'], 'unknown')
        self.assertIn('unverified', task['terminalReport'])
        self.assertTrue(task['sessionId'].startswith('recovered-'))
        self.assertIn('Synthetic original request', (self.root/'sessions'/f"{task['sessionId']}.jsonl").read_text())
        api.revoke_connection_task.assert_called_with(self.tid)
        api.TASKS.clear(); api.restore_task_checkpoints()
        self.assertEqual(api.TASKS[self.tid]['terminalReport'], task['terminalReport'])

    def test_tool_result_is_not_claimed_as_verified_target_effect(self):
        api.apply_task_event(self.tid, {'type':'tool_execution_start','toolCallId':'one','toolName':'ipython'})
        api.apply_task_event(self.tid, {'type':'tool_execution_end','toolCallId':'one','toolName':'ipython','result':{}})
        self.assertEqual(api.metadata()['tasks'][self.tid]['toolSteps'][0]['state'], 'returned')
        self.assertEqual([row['sequence'] for row in self.task['runtimeEvents']], [1, 2])

    def test_monitor_crash_keeps_report_and_prompt(self):
        with mock.patch.object(api, '_monitor_task', side_effect=RuntimeError('SECRET')):
            api.monitor_task(self.tid, set())
        row = api.metadata()['tasks'][self.tid]
        self.assertEqual(row['status'], 'failed'); self.assertNotIn('SECRET', row['terminalReport'])
        self.assertEqual(row['prompt'], self.task['submittedMessage'])

    def test_clean_runtime_exit_without_answer_is_failure(self):
        process = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self.task['process'] = process
        try:
            api.monitor_task(self.tid, set())
            self.assertEqual(self.task['status'], 'failed')
            self.assertIn('without a final answer', self.task['terminalReport'])
        finally:
            if process.stdin: process.stdin.close()
            process.stdout.close()

    def test_existing_conversation_gets_retained_report_without_log(self):
        self.task['sessionId'] = 'existing-session'
        api.finish_task_record(self.task, 'failed', 'Runtime unavailable')
        with mock.patch.object(api, 'require_conversation_owner'):
            logs = api.conversation_task_logs('existing-session', 'alice')
            self.assertEqual(len(logs), 1); self.assertIn('Runtime unavailable', logs[0]['terminalReport'])
            self.assertEqual(api.conversation_task_logs('existing-session', 'bob'), [])

    def test_unavailable_transcript_does_not_lose_terminal_report(self):
        with mock.patch.object(api, 'recover_failed_task_conversation', side_effect=PermissionError()):
            api.finish_task_record(self.task, 'failed', 'Runtime failed')
        self.assertIn('Runtime failed', api.metadata()['tasks'][self.tid]['terminalReport'])

    def test_prompt_saved_before_process_spawn_and_failed_submission_retained(self):
        for failure in ('spawn', 'stdin'):
            with self.subTest(failure=failure), ExitStack() as stack:
                stack.enter_context(mock.patch.object(api, 'container_mode', return_value=False))
                stack.enter_context(mock.patch.object(api, 'prime_env', return_value={}))
                stack.enter_context(mock.patch.object(api.legacy, 'settings_view', return_value={'thinking':'low'}))
                stack.enter_context(mock.patch.object(api, 'route_task', return_value={
                    'provider':'spark-qwen','model':'qwen3.8-flash-next','routeReason':'fixture'}))
                stack.enter_context(mock.patch.object(api, 'model_details', return_value={}))
                stack.enter_context(mock.patch.object(api, 'resolve_effort', return_value=('low', 'fixture')))
                stack.enter_context(mock.patch.object(api, 'normalize_file_ids', return_value=[]))
                stack.enter_context(mock.patch.object(api, 'project_context', return_value=''))
                process = mock.Mock(pid=123)
                process.stdin.write.side_effect = BrokenPipeError()
                def spawn(*args, **kwargs):
                    records = api.metadata()['tasks']
                    self.assertTrue(any(row.get('prompt') == 'Original '+failure and row['status']=='starting' for row in records.values()))
                    if failure == 'spawn': raise OSError('synthetic')
                    return process
                stack.enter_context(mock.patch.object(api.subprocess, 'Popen', side_effect=spawn))
                with self.assertRaises((OSError, RuntimeError)):
                    api.launch_task('Original '+failure, owner='alice')
                records = [row for row in api.metadata()['tasks'].values() if row['prompt']=='Original '+failure]
                self.assertEqual(len(records), 1); self.assertEqual(records[0]['status'], 'failed')
                self.assertTrue(records[0]['sessionId'].startswith('recovered-'))


if __name__ == '__main__': unittest.main()
