import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'container'))
import inference_policy
import model_gateway


class InferencePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'policy.json'
        self.row = {'accountIdSha256': hashlib.sha256(b'fixture-account').hexdigest(),
                    'models': ['fixture-model'], 'noTraining': True,
                    'reviewedUntil': time.time() + 3600, 'evidence': 'Synthetic test only'}
        self.save()
        self.patch = mock.patch.object(inference_policy, 'POLICY_PATH', self.path)
        self.patch.start(); self.addCleanup(self.patch.stop)
        original = os.fstat
        def root_stat(fd):
            values = list(original(fd)); values[4] = 0
            return os.stat_result(values)
        self.stat_patch = mock.patch.object(inference_policy.os, 'fstat', side_effect=root_stat)
        self.stat_patch.start(); self.addCleanup(self.stat_patch.stop)

    def save(self):
        self.path.write_text(json.dumps({'version': 1, 'owners': {'alice': {'openai-codex': self.row}}}))
        self.path.chmod(0o644)

    def test_only_exact_owner_account_and_model_are_listed(self):
        self.assertEqual(inference_policy.approved_models('alice', 'openai-codex', 'fixture-account'), ['fixture-model'])
        self.assertEqual(inference_policy.approved_models('bob', 'openai-codex', 'fixture-account'), [])
        self.assertEqual(inference_policy.approved_models('alice', 'openai-codex', 'another-account'), [])

    def test_missing_malformed_and_unsafe_policy_fail_closed(self):
        self.path.unlink()
        self.assertEqual(inference_policy.approvals('alice'), {})
        self.path.write_text('bad json')
        self.assertEqual(inference_policy.approvals('alice'), {})
        self.save(); self.path.chmod(0o666)
        self.assertEqual(inference_policy.approvals('alice'), {})
        self.save(); self.stat_patch.stop()
        with mock.patch.object(inference_policy.os, 'fstat', return_value=mock.Mock(st_mode=0o100644, st_uid=123, st_size=100)):
            self.assertEqual(inference_policy.approvals('alice'), {})

    def test_expiry_opt_in_and_wildcards_are_not_approval(self):
        for key, value in [('reviewedUntil', time.time()-1), ('reviewedUntil', float('inf')),
                           ('noTraining', False), ('noTraining', 'true'), ('models', ['*']),
                           ('models', []), ('evidence', '')]:
            old = self.row[key]; self.row[key] = value; self.save()
            self.assertEqual(inference_policy.approvals('alice'), {}, (key, value))
            self.row[key] = old

    def test_symlink_policy_is_rejected(self):
        target = self.root/'target.json'; self.path.rename(target); self.path.symlink_to(target)
        self.assertEqual(inference_policy.approvals('alice'), {})


class GatewayApprovalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name)/'gateway.sock')
        self.server = model_gateway.Server(self.path, 'alice')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection('localhost')
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.connect(self.path)
        connection.request(method, path, json.dumps(payload) if payload is not None else None)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_catalog_is_scoped_metadata_not_credentials(self):
        with mock.patch.object(model_gateway, 'external_models', return_value=['fixture-model']) as approved:
            status, body = self.request('GET', '/routing-models')
        approved.assert_called_once_with('alice')
        self.assertEqual(status, 200)
        self.assertEqual(body['externalModels'], ['openai-codex/fixture-model'])
        self.assertNotIn('accountId', json.dumps(body))

    def test_unapproved_request_never_reads_credentials_or_connects(self):
        with mock.patch.object(model_gateway, 'external_models', return_value=[]), \
             mock.patch.object(model_gateway, 'credential') as credential, \
             mock.patch.object(model_gateway.http.client, 'HTTPSConnection') as upstream:
            status, body = self.request('POST', '/openai-codex/responses', {'model': 'unapproved'})
        self.assertEqual(status, 403)
        self.assertIn('not approved', body['error']['message'])
        credential.assert_not_called(); upstream.assert_not_called()

    def test_approved_route_forwards_exact_endpoint_and_checks_account(self):
        response = mock.Mock(status=200)
        response.getheaders.return_value = [('Content-Type', 'application/json')]
        response.read1.side_effect = [b'{"ok":true}', b'']
        conn = mock.Mock(); conn.getresponse.return_value = response
        auth = {'access': 'fixture-secret', 'accountId': 'fixture-account'}
        with mock.patch.object(model_gateway, 'external_models', return_value=['fixture-model']), \
             mock.patch.object(model_gateway, 'credential', return_value=auth), \
             mock.patch.object(inference_policy, 'approved_models', return_value=['fixture-model']) as approval, \
             mock.patch.object(model_gateway.http.client, 'HTTPSConnection', return_value=conn):
            status, body = self.request('POST', '/openai-codex/responses', {'model': 'fixture-model'})
        self.assertEqual((status, body), (200, {'ok': True}))
        approval.assert_called_once_with('alice', 'openai-codex', 'fixture-account')
        self.assertEqual(conn.request.call_args.args[1], '/backend-api/codex/responses')

    def test_changed_account_cannot_use_previous_approval(self):
        with mock.patch.object(model_gateway, 'external_models', return_value=['fixture-model']), \
             mock.patch.object(model_gateway, 'credential', return_value={'accountId': 'changed'}), \
             mock.patch.object(inference_policy, 'approved_models', return_value=[]), \
             mock.patch.object(model_gateway.http.client, 'HTTPSConnection') as upstream:
            status, _ = self.request('POST', '/openai-codex/responses', {'model': 'fixture-model'})
        self.assertEqual(status, 403); upstream.assert_not_called()

    def test_unknown_endpoint_and_nonobject_payload_rejected(self):
        with mock.patch.object(model_gateway, 'external_models', return_value=['fixture-model']), \
             mock.patch.object(model_gateway, 'credential') as credential:
            self.assertEqual(self.request('POST', '/openai-codex/other', {'model': 'fixture-model'})[0], 403)
            self.assertEqual(self.request('POST', '/openai-codex/responses', [1, 2])[0], 403)
        credential.assert_not_called()

    def test_unauthorized_retry_rechecks_changed_account_before_resending(self):
        response = mock.Mock(status=401)
        conn = mock.Mock(); conn.getresponse.return_value = response
        with mock.patch.object(model_gateway, 'external_models', return_value=['fixture-model']), \
             mock.patch.object(model_gateway, 'credential', side_effect=[
                 {'access': 'fixture', 'accountId': 'original'}, {'accountId': 'changed'}]) as credential, \
             mock.patch.object(inference_policy, 'approved_models', side_effect=[['fixture-model'], []]) as approval, \
             mock.patch.object(model_gateway.http.client, 'HTTPSConnection', return_value=conn) as upstream:
            status, _ = self.request('POST', '/openai-codex/codex/responses', {'model': 'fixture-model'})
        self.assertEqual(status, 403)
        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(conn.request.call_count, 1)
        credential.assert_called_with('alice', force_refresh=True)
        approval.assert_called_with('alice', 'openai-codex', 'changed')


if __name__ == '__main__':
    unittest.main()
