import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('chat_timeout_api', Path(__file__).with_name('api_v2.py'))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ChatTimeoutTests(unittest.TestCase):
    def test_multiweek_task_and_role_limits(self):
        for minutes in (30, 1440, 20160, 40320, 129600):
            authorized = api.task_policy.authorize_task({'runtimeMinutes':minutes}, 'admin')
            self.assertEqual(authorized['limits']['runtimeMinutes'], minutes)
        for value in (0, -1, 129601, True, 1.5, '20160', float('inf')):
            with self.assertRaises(ValueError):
                api.policy_preference({'runtimeMinutes':value}, 'admin')
        for role, allowed in (('user',30), ('power_user',120)):
            self.assertEqual(api.task_policy.authorize_task({'runtimeMinutes':allowed}, role)['limits']['runtimeMinutes'],allowed)
            with self.assertRaises(ValueError):
                api.task_policy.authorize_task({'runtimeMinutes':allowed+1}, role)

    def test_saved_chat_and_project_runtime_precedence(self):
        data = {'conversations': {'chat-one': {'owner':'alice','projectId':'project','taskPolicy':{'runtimeMinutes':20160}}}}
        project = {'taskPolicy':{'runtimeMinutes':40320}}
        with mock.patch.object(api,'metadata',return_value=data), mock.patch.object(api,'require_conversation_owner'), mock.patch.object(api,'require_project',return_value=project):
            self.assertEqual(api.task_start_runtime({'sessionId':'chat-one'},'alice','admin'),20160)
            self.assertEqual(api.task_start_runtime({'projectId':'project'},'alice','admin'),40320)
            self.assertEqual(api.task_start_runtime({'sessionId':'chat-one','taskPolicy':{'runtimeMinutes':1440}},'alice','admin'),1440)
            data['conversations']['chat-one']['taskPolicy'] = {'profile':'general'}
            self.assertEqual(api.task_start_runtime({'sessionId':'chat-one'},'alice','admin'),30)
            self.assertEqual(api.task_start_runtime({},'alice','admin'),30)
        with self.assertRaises(ValueError):
            api.task_start_runtime({'taskPolicy':{'runtimeMinutes':20160},'conversationPolicy':{'runtimeMinutes':30}},'alice','admin')

    def test_saved_runtime_and_promotion_policy_are_normalized(self):
        policy = api.policy_preference({'profile':'general','runtimeMinutes':40320},'admin')
        self.assertEqual(policy['runtimeMinutes'],40320)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(api,'META',Path(directory)/'metadata.json'):
            api.store_task_route({'sessionId':'chat-one','owner':'alice','persistPolicyOnSessionCreate':True,'policyPreference':policy})
            self.assertEqual(api.metadata()['conversations']['chat-one']['taskPolicy']['runtimeMinutes'],40320)

    def test_two_week_timer_survives_four_hour_and_one_week_marks(self):
        task = {'status':'running','authorization':{'role':'admin','limits':{'runtimeMinutes':20160}}}
        api.initialize_task_timer(task)
        start = task['_deadlineMonotonic'] - 20160*60
        for elapsed in (4*3600+1, 7*86400):
            with mock.patch.object(api.time,'monotonic',return_value=start+elapsed):
                self.assertFalse(api.task_deadline_expired(task, start+1800))
                self.assertFalse(api.task_timer_view(task)['timerWarning'])
        with mock.patch.object(api.time,'monotonic',return_value=start+14*86400-299):
            self.assertTrue(api.task_timer_view(task)['timerWarning'])
        with mock.patch.object(api.time,'monotonic',return_value=start+14*86400+1):
            self.assertTrue(api.task_deadline_expired(task,0))

    def test_timeout_change_invalidates_old_quiet_confirmation(self):
        saved = {'profile':'general','executionMode':'task','networkMode':'restricted','confirmationMode':'always','runtimeMinutes':30}
        with mock.patch.object(api,'metadata',return_value={'conversations':{'chat-one':{'owner':'alice','taskPolicy':saved}}}):
            self.assertTrue(api.persistent_confirmation_allowed(saved,'chat-one',None,'alice'))
            self.assertFalse(api.persistent_confirmation_allowed({**saved,'runtimeMinutes':20160},'chat-one',None,'alice'))

    def test_hosting_capability_lasts_through_multiweek_runner_but_revokes(self):
        import sys
        sys.path.insert(0,str(Path(__file__).parents[1]/'container'))
        import hosting_auth
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = hosting_auth.issue('alice','a'*32,None,{'role':'admin','networkMode':'lan'},root)
            with mock.patch.object(hosting_auth.time,'time',return_value=time.time()+21*86400):
                self.assertEqual(hosting_auth.verify(token,'alice',root)['owner'],'alice')
            hosting_auth.revoke('a'*32,root)
            with self.assertRaises(PermissionError):
                hosting_auth.verify(token,'alice',root)


if __name__ == '__main__':
    unittest.main()
