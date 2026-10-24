import ast
import base64
import http.client
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

import connections
import connection_broker
import skill_credentials

TASK = 'a'*32
PROJECT = 'p_'+'b'*24
SECRET = 'SYNTHETIC_CONNECTION_SECRET'
POLICY = {'profile': 'network-operations', 'networkMode': 'full', 'executionMode': 'task', 'role': 'user'}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name); self.root = self.home/'config'; self.root.mkdir(mode=0o700)
        self.agent = self.home/'.prime/agent'; self.agent.mkdir(parents=True)
        self.manager = connections.Connections(self.root, self.home)
        self.decl = {'id': 'github', 'label': 'GitHub', 'adapter': 'github-readonly',
                     'fields': [{'id': 'token', 'label': 'Token'}]}
        self.meta = {'projects': {PROJECT: {'owner': 'alice', 'name': 'Fixture'}},
                     'skills': {'s_fixture': {'owner': 'alice', 'status': 'installed', 'enabled': True,
                                'credentialRequirements': [self.decl]}},
                     'tasks': {TASK: {'owner': 'alice', 'projectId': PROJECT, 'status': 'running'}}}
        self.save_meta()
        skill_credentials._write(self.root/'web-auth.json', json.dumps({'users': {'alice': {'enabled': True}, 'bob': {'enabled': True}}}).encode())
        patch = mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED': '1', 'PRIME_CREDENTIALS_ENABLED': '1'})
        patch.start(); self.addCleanup(patch.stop)
        if not Path('/proc/self/stat').exists():
            identity = mock.patch.object(connections, 'process_identity', return_value='fixture-boot:process-start')
            identity.start(); self.addCleanup(identity.stop)
        self.req = self.manager.requirements('alice')[0]
        self.save_credential()
        self.body = {'action': 'save', 'name': 'My repository', 'credentialKey': self.req['key'],
                     'projectId': PROJECT, 'expiresAt': time.time()+3600, 'enabled': True}
        self.key = self.manager.change('alice', self.body)['id']
        self.token = self.manager.issue('alice', TASK, PROJECT, POLICY)

    def save_meta(self):
        (self.agent/'webui-metadata.json').write_text(json.dumps(self.meta))

    def save_credential(self, values=None):
        self.manager.vault.change('alice', [self.req], {'action': 'save', 'key': self.req['key'], 'values': values or {'token': SECRET}})

    def call(self, **extra):
        request = {'token': self.token, 'action': 'call', 'connection': self.key,
                   'operation': 'github.repository', 'arguments': {'repository': 'example/demo'}, **extra}
        return self.manager.dispatch(request, 'alice', transport=lambda *args: {'private': True, 'open_issues_count': 3, 'description': SECRET})

    def test_read_only_summary_and_no_secret_in_metadata_disk_or_capability(self):
        self.assertEqual(self.call(), {'repository': 'example/demo', 'private': True, 'open_issues_count': 3})
        self.assertNotIn(SECRET, json.dumps(self.manager.view('alice')))
        self.assertEqual(self.manager.view('bob')['connections'], [])
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(SECRET.encode(), path.read_bytes())
                self.assertNotIn(self.token.encode(), path.read_bytes())
        self.assertEqual(self.manager.dispatch({'action': 'list', 'token': self.token}, 'alice')['connections'][0]['id'], self.key)

    def test_other_user_forged_token_and_owner_override_denied(self):
        for request, owner in [({'token': self.token, 'action': 'list'}, 'bob'),
                               ({'token': self.token[:-1]+'z', 'action': 'list'}, 'alice'),
                               ({'token': self.token, 'action': 'list', 'owner': 'alice'}, 'alice')]:
            with self.subTest(owner=owner), self.assertRaises((ValueError, PermissionError)):
                self.manager.dispatch(request, owner)

    def test_task_expiry_stop_owner_project_change_and_account_disable_denied(self):
        for changes in ({'status': 'completed'}, {'owner': 'bob'}, {'projectId': None}):
            original = dict(self.meta['tasks'][TASK]); self.meta['tasks'][TASK].update(changes); self.save_meta()
            with self.assertRaises(PermissionError): self.call()
            self.meta['tasks'][TASK] = original; self.save_meta()
        skill_credentials._write(self.root/'web-auth.json', json.dumps({'users': {'alice': {'enabled': False}}}).encode())
        with self.assertRaises(PermissionError): self.call()

    def test_expired_and_revoked_capabilities(self):
        with mock.patch.object(connections.time, 'time', return_value=time.time()+7200):
            with self.assertRaises(PermissionError): self.call()
        self.manager.revoke(TASK)
        with self.assertRaises((OSError, PermissionError)): self.call()

    def test_issuer_restart_or_pid_reuse_invalidates_persisted_grant(self):
        with mock.patch.object(connections, 'process_identity', return_value='different-boot:or-start'):
            with self.assertRaises(PermissionError): self.call()

    def test_connection_update_delete_and_skill_disable_revoke(self):
        self.manager.change('alice', dict(self.body, id=self.key, enabled=False))
        with self.assertRaises(PermissionError): self.call()
        self.manager.change('alice', dict(self.body, id=self.key))
        with self.assertRaises(PermissionError): self.call()  # Old revision stays revoked.
        self.manager.change('alice', {'action': 'delete', 'id': self.key})
        with self.assertRaises(PermissionError): self.call()

    def test_disabled_or_removed_skill_cannot_use_stored_credentials(self):
        self.meta['skills']['s_fixture']['enabled'] = False; self.save_meta()
        with self.assertRaises(PermissionError): self.call()

    def test_removed_credential_cannot_authenticate(self):
        self.manager.vault.change('alice', [], {'action': 'delete', 'key': self.req['key']})
        with self.assertRaises(PermissionError): self.call()

    def test_credential_rotation_revokes_connections_without_exposing_new_value(self):
        self.save_credential({'token': 'ROTATED_SYNTHETIC_TOKEN'})
        with self.assertRaises(PermissionError): self.call()
        self.assertEqual(self.manager.view('alice')['connections'][0]['status'], 'unavailable')

    def test_only_originally_granted_connections_and_project(self):
        second = self.manager.change('alice', dict(self.body, name='Added later'))['id']
        with self.assertRaises(PermissionError): self.call(connection=second)
        self.assertIsNone(self.manager.issue('alice', 'c'*32, None, POLICY))
        self.meta['projects'][PROJECT]['owner'] = 'bob'; self.save_meta()
        with self.assertRaises(PermissionError): self.call()

    def test_global_connection_requires_explicit_scope_and_matches_own_task(self):
        key = self.manager.change('alice', dict(self.body, projectId=None))['id']
        self.meta['tasks']['d'*32] = {'owner': 'alice', 'projectId': None, 'status': 'running'}; self.save_meta()
        token = self.manager.issue('alice', 'd'*32, None, POLICY)
        rows = self.manager.dispatch({'token': token, 'action': 'list'}, 'alice')['connections']
        self.assertEqual([r['id'] for r in rows], [key])

    def test_invalid_configuration(self):
        for changes in ({'owner': 'bob'}, {'projectId': 'p_'+'c'*24}, {'expiresAt': float('nan')},
                        {'expiresAt': 1}, {'expiresAt': time.time()+91*86400}, {'enabled': 'true'},
                        {'credentialKey': 'missing'}, {'id': 'c_'+'f'*32}, {'name': '\nsecret'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.change('alice', dict(self.body, **changes))

    def test_network_execution_and_role_gates(self):
        for policy in (dict(POLICY, networkMode='restricted'), dict(POLICY, networkMode='lan'), dict(POLICY, executionMode='deny')):
            self.assertIsNone(self.manager.issue('alice', 'c'*32, PROJECT, policy))
        with mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED': '0'}):
            self.assertIsNone(self.manager.issue('alice', 'c'*32, PROJECT, POLICY))
            with self.assertRaises(PermissionError): self.call()

    def test_arbitrary_urls_methods_paths_and_operations_rejected(self):
        for kwargs in ({'operation': 'github.write'}, {'url': 'https://evil.example'},
                       {'arguments': {'repository': 'example/demo', 'method': 'POST'}},
                       {'arguments': {'repository': '../..'}}, {'arguments': {'repository': 'example/repo?x=y'}},
                       {'arguments': {'repository': 'https://evil.example'}}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, PermissionError)):
                self.call(**kwargs)

    def test_revocation_during_request_withholds_result(self):
        def transport(*args):
            self.manager.change('alice', dict(self.body, id=self.key, enabled=False))
            return {'private': True}
        request = {'token': self.token, 'action': 'call', 'connection': self.key, 'operation': 'github.repository', 'arguments': {'repository': 'example/demo'}}
        with self.assertRaises(PermissionError): self.manager.dispatch(request, 'alice', transport)

    def test_deleted_account_connections_and_capabilities_are_removed(self):
        self.manager.delete_owner('alice')
        self.assertEqual(self.manager.view('alice')['connections'], [])
        self.assertFalse((self.root/'connection-capabilities'/f'{TASK}.json').exists())

    def test_http_broker_real_loopback_roundtrip_and_generic_errors(self):
        server = connection_broker.Server(('127.0.0.1', 0), self.manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with mock.patch.object(connections, 'get_json', return_value={'private': True, 'description': SECRET}):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                body = {'token': self.token, 'action': 'call', 'connection': self.key,
                        'operation': 'github.repository', 'arguments': {'repository': 'example/demo'}}
                client.request('POST', '/connections', json.dumps(body), {'Content-Type': 'application/json', 'X-Prime-Connection-Owner': 'alice'})
                response = client.getresponse(); raw = response.read(); client.close()
                self.assertEqual(response.status, 200); self.assertNotIn(SECRET.encode(), raw)
            with mock.patch.object(connections, 'get_json', side_effect=RuntimeError(SECRET)):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('POST', '/connections', json.dumps(body), {'Content-Type': 'application/json', 'X-Prime-Connection-Owner': 'alice'})
                response = client.getresponse(); raw = response.read(); client.close()
                self.assertEqual(response.status, 502); self.assertNotIn(SECRET.encode(), raw)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class AdapterTests(unittest.TestCase):
    def test_endpoints_reject_ssrf_redirect_userinfo_dns_and_encoding(self):
        for target in ('http://192.168.1.2', 'https://localhost', 'https://127.0.0.1', 'https://169.254.169.254',
                       'https://[::1]', 'https://example.com', 'https://user:pass@192.168.1.2',
                       'https://192.168.1.2/redfish', 'https://192.168.1.2?x=1', 'https://192.168.1.2#x',
                       'https://192.168.1.2:444', 'https://192.168.1.2\n', 'https://192.168.01.2'):
            with self.subTest(target=target), self.assertRaises(ValueError): connections.endpoint(target)
        self.assertEqual(connections.endpoint('https://192.168.1.2:443/'), 'https://192.168.1.2')

    def test_redfish_only_allows_same_origin_fixed_collection_and_enums(self):
        values = {'endpoint': 'https://192.168.1.2', 'username': 'fixture', 'password': SECRET}
        row = {'endpoint': values['endpoint']}
        seen = []
        def transport(origin, path, headers):
            seen.append((origin, path, headers))
            if path == '/redfish/v1/Systems': return {'Members': [{'@odata.id': '/redfish/v1/Systems/1'}]}
            return {'PowerState': 'On', 'Status': {'Health': 'OK', 'State': SECRET}, 'SerialNumber': SECRET}
        result = connections.perform(row, values, 'redfish.systems', {}, transport)
        self.assertEqual(result, {'systems': [{'index': 0, 'powerState': 'On', 'health': 'OK', 'state': 'Unknown'}]})
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][2]['Authorization'], 'Basic '+base64.b64encode(('fixture:'+SECRET).encode()).decode())
        for path in ('https://evil.example', '//evil.example', '/redfish/v1/Systems/../Managers', '/redfish/v1/Systems/a%2Fb'):
            with self.assertRaises(ValueError):
                connections.perform(row, values, 'redfish.systems', {}, lambda *args: {'Members': [{'@odata.id': path}]})
        with self.assertRaises(ValueError): connections.perform({'endpoint': 'https://192.168.1.3'}, values, 'redfish.systems', {}, transport)
        with self.assertRaises(ValueError): connections.perform(row, values, 'redfish.systems', {'action': 'reset'}, transport)

    def test_redfish_limits_and_network_profile(self):
        row = {'adapter': 'redfish-readonly', 'endpoint': 'https://192.168.1.2'}
        self.assertTrue(connections.permitted(row, POLICY))
        self.assertFalse(connections.permitted(row, dict(POLICY, profile='general')))
        self.assertFalse(connections.permitted(row, dict(POLICY, networkMode='internet')))
        values = {'endpoint': row['endpoint'], 'username': 'fixture', 'password': SECRET}
        for response in ({'Members': [{}]*17}, {'Members': [], 'Members@odata.nextLink': '/other'}, {}):
            with self.assertRaises(ValueError): connections.perform(row, values, 'redfish.systems', {}, lambda *args: response)

    def test_transport_never_follows_redirects_or_returns_error_bodies(self):
        for status in (301, 302, 307, 401, 500):
            response = mock.Mock(status=status)
            with mock.patch.object(connections.http.client, 'HTTPSConnection') as cls:
                cls.return_value.getresponse.return_value = response
                with self.assertRaises(ValueError): connections.get_json('https://api.github.com', '/repos/a/b', {})
                response.read1.assert_not_called()
                self.assertEqual(cls.call_count, 1)
                cls.return_value.close.assert_called_once()

    def test_transport_bounds_body_and_verifies_tls(self):
        response = mock.Mock(status=200)
        response.getheader.side_effect = lambda key, default=None: {'Content-Type': 'application/json'}.get(key, default)
        response.read1.side_effect = [b'{'*connections.MAX_RESPONSE, b'x']
        with mock.patch.object(connections.http.client, 'HTTPSConnection') as cls:
            cls.return_value.getresponse.return_value = response
            with self.assertRaises(ValueError): connections.get_json('https://api.github.com', '/repos/a/b', {})
            context = cls.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, connections.ssl.CERT_REQUIRED)

    def test_reviewed_adapter_schema_is_closed(self):
        for adapter, fields in [('arbitrary-env', [{'id': 'token', 'label': 'Token'}]),
                                ('github-readonly', [{'id': 'password', 'label': 'Password'}])]:
            with self.assertRaises(ValueError): skill_credentials.declarations({'version': 1, 'credentials': [
                {'id': 'test', 'label': 'Test', 'adapter': adapter, 'fields': fields}]})

    def test_runner_capability_transfer_has_no_token_in_process_arguments(self):
        source = (Path(__file__).parents[1]/'container/runner_launch.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'prepare_connection_capability')
        namespace = {'subprocess': mock.Mock(), 'OPENSHELL_COMMON': ['openshell']}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<fixture>', 'exec'), namespace)
        spec = {'name': 'pt-fixture', 'inputFifo': '/tmp/fixture', 'execute': ['openshell', 'sandbox', 'exec', '--', '/usr/bin/python3', '-c', 'print("ok")']}
        token = TASK+'.'+'b'*64
        namespace['prepare_connection_capability'](spec, token)
        call = namespace['subprocess'].run.call_args
        self.assertEqual(call.kwargs['input'], token.encode())
        self.assertNotIn(token, repr(call.args))
        self.assertNotIn(token, repr(spec))
        self.assertIn('PRIME_CONNECTION_TOKEN', spec['execute'][6])

    def test_capability_stdin_script_and_relay_execute_and_remove_private_file(self):
        source = (Path(__file__).parents[1]/'container/runner_launch.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'prepare_connection_capability')
        namespace = {'subprocess': mock.Mock(), 'OPENSHELL_COMMON': ['openshell']}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<fixture>', 'exec'), namespace)
        token = TASK+'.'+'b'*64
        with tempfile.TemporaryDirectory() as directory:
            fifo = str(Path(directory)/'fifo')
            spec = {'name': 'pt-fixture', 'inputFifo': fifo, 'execute': ['openshell', 'sandbox', 'exec', '--', '/usr/bin/python3', '-c',
                    'import hashlib; print(hashlib.sha256(os.environ["PRIME_CONNECTION_TOKEN"].encode()).hexdigest())']}
            namespace['prepare_connection_capability'](spec, token)
            command = namespace['subprocess'].run.call_args.args[0]
            subprocess.run([sys.executable, '-c', command[-2], command[-1]], input=token.encode(), check=True, capture_output=True)
            self.assertEqual(Path(fifo+'.connection').stat().st_mode & 0o777, 0o600)
            result = subprocess.run([sys.executable, '-c', spec['execute'][6]], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), connections.hashlib.sha256(token.encode()).hexdigest())
            self.assertFalse(Path(fifo+'.connection').exists())


if __name__ == '__main__':
    unittest.main()
