import importlib.util
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location('timer_api', Path(__file__).with_name('api_v2.py'))
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)


class TaskTimerTests(unittest.TestCase):
    def setUp(self):
        self.task = {'id':'e'*32, 'owner':'alice', 'status':'running', 'startedEpoch':time.time(),
                     'authorization':{'role':'admin','limits':{'runtimeMinutes':30}}}
        api.initialize_task_timer(self.task)
        api.TASKS[self.task['id']] = self.task
        self.addCleanup(lambda: api.TASKS.pop(self.task['id'], None))
        patch = mock.patch.object(api.legacy, 'audit'); patch.start(); self.addCleanup(patch.stop)

    def extend(self, revision=0, owner='alice', role='admin'):
        return api.extend_task_timer(self.task['id'], revision, owner, role)

    def test_initial_warning_and_repeatable_extension(self):
        self.assertFalse(api.task_timer_view(self.task)['timerWarning'])
        initial = self.task['_deadlineMonotonic']
        with mock.patch.object(api.time, 'monotonic', return_value=initial-299):
            self.assertTrue(api.task_timer_view(self.task)['timerWarning'])
            self.assertGreater(self.extend()['remainingSeconds'], 2000)
            self.assertFalse(api.task_timer_view(self.task)['timerWarning'])
        self.assertEqual(self.task['_deadlineMonotonic'], initial+1800)
        self.extend(1)
        self.assertEqual(self.task['_deadlineMonotonic'], initial+3600)

    def test_duplicate_retry_is_idempotent_and_foreign_owner_rejected(self):
        self.extend()
        deadline = self.task['_deadlineMonotonic']
        self.extend()
        self.assertEqual(self.task['_deadlineMonotonic'], deadline)
        with self.assertRaises(ValueError): self.extend(owner='bob')
        with self.assertRaises(ValueError): self.extend(99)
        with self.assertRaises(ValueError): self.extend(True)

    def test_role_and_hard_ceiling_are_enforced(self):
        with self.assertRaises(ValueError): self.extend(role='user')
        for revision in range(7): self.extend(revision)
        self.assertFalse(api.task_timer_view(self.task)['timerExtendable'])
        with self.assertRaises(ValueError): self.extend(7)

    def test_expired_stopped_and_old_tasks_cannot_be_extended(self):
        with mock.patch.object(api.time,'monotonic',return_value=self.task['_deadlineMonotonic']+1):
            self.assertTrue(api.task_deadline_expired(self.task,0))
            with self.assertRaises(ValueError): self.extend()
        self.assertIn('time limit',self.task['rpcError'])
        self.task['_timerExpired'] = False
        self.task['stopRequested'] = True
        with self.assertRaises(ValueError): self.extend()
        self.task.pop('_deadlineMonotonic')
        with self.assertRaises(ValueError): self.extend()

    def test_monitor_checks_extended_deadline_not_original(self):
        initial=self.task['_deadlineMonotonic']
        self.extend()
        with mock.patch.object(api.time,'monotonic',return_value=initial+1):
            self.assertFalse(api.task_deadline_expired(self.task,initial))
        with mock.patch.object(api.time,'monotonic',return_value=initial+1801):
            self.assertTrue(api.task_deadline_expired(self.task,initial))

    def test_live_monitor_survives_original_deadline_after_extension(self):
        script = 'import time,json; print(json.dumps({"type":"agent_start"}),flush=True); time.sleep(.8); print(json.dumps({"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"Done"}]}}),flush=True)'
        process=subprocess.Popen([sys.executable,'-u','-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        self.task.update(process=process, sessionId='existing', _deadlineMonotonic=time.monotonic()+.2)
        self.extend()
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(api,'session_root',return_value=Path(directory)), mock.patch.object(api,'session_stems',return_value=set()), mock.patch.object(api,'append_live_log'), mock.patch.object(api,'recover_failed_task_conversation'), mock.patch.object(api,'append_ledger'), mock.patch.object(api,'store_task_route'), mock.patch.object(api,'record_task_finished'):
                api.monitor_task(self.task['id'],set())
            self.assertEqual(self.task['status'],'completed')
            self.assertGreater(self.task['elapsedSeconds'],.2)
        finally:
            if process.poll() is None: process.terminate(); process.wait(5)
            process.stdin.close(); process.stdout.close()

    def test_extension_endpoint_uses_existing_request_validation(self):
        source=Path(__file__).with_name('api_v2.py').read_text()
        self.assertIn('v2 = {"/api/tasks/extend"',source)
        self.assertIn('not csrf_ok(self.headers)',source)

    def test_no_response_stops_at_the_deadline_with_explanation(self):
        process=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(10)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        self.task.update(process=process, sessionId='existing', _deadlineMonotonic=time.monotonic()+.1)
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(api,'session_root',return_value=Path(directory)), mock.patch.object(api,'session_stems',return_value=set()), mock.patch.object(api,'append_live_log'), mock.patch.object(api,'recover_failed_task_conversation'), mock.patch.object(api,'append_ledger'), mock.patch.object(api,'store_task_route'), mock.patch.object(api,'record_task_finished'):
                api.monitor_task(self.task['id'],set())
            self.assertEqual(self.task['status'],'timed_out')
            self.assertIn('time limit',self.task['rpcError'])
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None: process.terminate(); process.wait(5)
            process.stdin.close(); process.stdout.close()


if __name__ == '__main__': unittest.main()
