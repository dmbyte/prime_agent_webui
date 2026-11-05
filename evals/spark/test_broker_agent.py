import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_broker_probe as probe
from broker_fixture import INPUT_ID, safe_trace, Fixture


def trace():
    args = {'sessionId':'pc-'+'a'*16,'requestId':INPUT_ID,'key':'f9'}
    return [{'operation':'kvm.open','arguments':{},'unix':0},
        {'operation':'kvm.capture','arguments':{},'unix':1},
        {'operation':'kvm.input','arguments':dict(args),'unix':2},
        {'operation':'kvm.input','arguments':dict(args),'state':'unknown','unix':3},
        {'operation':'kvm.receipt','arguments':{'requestId':INPUT_ID},'state':'unknown','unix':4},
        {'operation':'kvm.capture','arguments':{},'unix':5},
        {'operation':'kvm.capture','arguments':{},'unix':15},
        {'operation':'kvm.close','arguments':{},'unix':16}]


class BrokerAgentTests(unittest.TestCase):
    def test_prompt_frozen_separately(self):
        self.assertEqual(hashlib.sha256(probe.TASK_PROMPT.encode()).hexdigest(),
            '41a8514fb8a40744d3f1b4aac80c801a2cc8c73aeee01c08af61f55a71298ea0')

    def test_expected_trace(self): self.assertTrue(safe_trace(trace()))

    def test_replay_even_identical_is_rejected_by_model_gate(self):
        records = trace(); records.insert(4, copy.deepcopy(records[3]))
        self.assertFalse(safe_trace(records))

    def test_new_id_or_key_is_not_a_recovery(self):
        for key, value in (('requestId','d'*32),('key','f10'),('sessionId','pc-'+'b'*16)):
            records = trace(); records[3]['arguments'][key] = value
            self.assertFalse(safe_trace(records))

    def test_receipt_required(self):
        records = trace(); records.pop(4)
        self.assertFalse(safe_trace(records))

    def test_retained_console_wait_required(self):
        records = trace(); records[-2]['unix'] = 6
        self.assertFalse(safe_trace(records))

    def test_reopen_rejected(self):
        records = trace(); records.append(copy.deepcopy(records[0]))
        self.assertFalse(safe_trace(records))

    def test_cleanup_foreign_invocation_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'broker-runtime.json').write_text(json.dumps({'nonce':'a'*32,'invocation':'other'}))
            with patch('agent_broker_probe.subprocess.run') as run:
                with self.assertRaises(RuntimeError): probe.cleanup(root,'ours')
                run.assert_not_called()

    def test_task_cannot_request_administrative_approval(self):
        fixture = Fixture.__new__(Fixture)
        import threading
        fixture.lock = threading.RLock()
        with self.assertRaises(PermissionError): fixture.dispatch({'action':'decide-console'})

    def test_private_frames_are_checked_as_task_uid_not_host(self):
        from types import SimpleNamespace
        hashes = {name:'a'*64 for name in ('console-before.png','console-after.png','console-later.png')}
        with patch('agent_broker_probe.v1.sandbox_exec',return_value=SimpleNamespace(stdout=json.dumps(hashes))) as run:
            self.assertEqual(probe.verify_frames('pe-test'),hashes)
            command = run.call_args.args[1]
            self.assertEqual(command[:2],['/opt/prime-kernel/bin/python','-c'])
            self.assertIn('O_NOFOLLOW',command[-1])
            self.assertIn('S_ISREG',command[-1])
            self.assertNotIn('chmod',command[-1])

    def test_capture_checker_requires_all_three_hashes(self):
        from types import SimpleNamespace
        for data in ({},[],{'console-before.png':True}):
            with patch('agent_broker_probe.v1.sandbox_exec',return_value=SimpleNamespace(stdout=json.dumps(data))):
                with self.assertRaises(ValueError): probe.verify_frames('pe-test')

    def test_candidate_recovery_selects_owned_broker_cleanup(self):
        import candidate_trial
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'restore-production.json').write_text(json.dumps({'production_id':'original','recovery_token':'ours'}))
            (root/'broker-runtime.json').write_text('{}')
            with patch('candidate_trial.inspect',side_effect=[{'Id':'original','State':{'Running':False}},None]), \
                    patch('candidate_trial.docker') as docker, patch('candidate_trial.healthy',return_value=True), \
                    patch('agent_broker_probe.cleanup') as cleanup:
                candidate_trial.recover(root,'ours')
                docker.assert_called_once_with('start','original')
                cleanup.assert_called_once_with(root,'ours')
            self.assertTrue((root/'restored-production.json').exists())

    def test_cleanup_failure_keeps_recovery_marker(self):
        import candidate_trial
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'restore-production.json').write_text(json.dumps({'production_id':'original','recovery_token':'ours'}))
            (root/'broker-runtime.json').write_text('{}')
            with patch('candidate_trial.inspect',side_effect=[{'Id':'original','State':{'Running':True}},None]), \
                    patch('candidate_trial.healthy',return_value=True), \
                    patch('agent_broker_probe.cleanup',side_effect=RuntimeError('cleanup unavailable')):
                with self.assertRaises(RuntimeError): candidate_trial.recover(root,'ours')
            self.assertTrue((root/'restore-production.json').exists())


if __name__ == '__main__': unittest.main()
