import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import skill_credentials as credentials
import connections

DECLARATION = {'id': 'service', 'label': 'Service login', 'fields': [
    {'id': 'username', 'label': 'Username'}, {'id': 'token', 'label': 'Access token'}]}


def requirement():
    row = credentials.declarations({'version': 1, 'credentials': [DECLARATION]})[0]
    return dict(row, key=credentials.requirement_id('s_test', row), skillId='s_test', skillName='Fixture skill')


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = credentials.Vault(self.root / 'vault')
        self.req = requirement()

    def save(self, owner='alice', **values):
        return self.vault.change(owner, [self.req], {'action': 'save', 'key': self.req['key'],
                                                   'values': values or {'username': 'fixture-user', 'token': 'PRIVATE_FIXTURE_ONLY'}})

    def test_encrypted_roundtrip_and_no_plaintext_in_status_or_files(self):
        self.save()
        view = self.vault.view('alice', [self.req])
        self.assertEqual(view[0]['status'], 'saved')
        self.assertNotIn('PRIVATE_FIXTURE_ONLY', json.dumps(view))
        self.assertNotIn('fixture-user', json.dumps(view))
        for path in self.vault.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b'PRIVATE_FIXTURE_ONLY', path.read_bytes())
        self.assertEqual(self.vault.root.stat().st_mode & 0o777, 0o700)

    def test_two_users_have_independent_values_and_delete(self):
        self.save(); self.save('bob', username='bob', token='BOB_FIXTURE')
        self.vault.change('alice', [], {'action': 'delete', 'key': self.req['key']})
        self.assertEqual(self.vault.view('alice', [self.req])[0]['status'], 'missing')
        self.assertEqual(self.vault.view('bob', [self.req])[0]['status'], 'saved')

    def test_blank_preserves_and_replacement_survives_reload(self):
        self.save(); self.save(username='', token='replacement')
        another = credentials.Vault(self.vault.root)
        self.assertEqual(another._load('alice')[self.req['key']]['values'], {'username': 'fixture-user', 'token': 'replacement'})

    def test_disabled_requirement_cannot_be_saved_but_can_be_deleted(self):
        self.save()
        self.assertEqual(self.vault.view('alice', [])[0]['status'], 'inactive')
        with self.assertRaises(ValueError):
            self.vault.change('alice', [], {'action': 'save', 'key': self.req['key'], 'values': {'token': 'x'}})
        self.vault.change('alice', [], {'action': 'delete', 'key': self.req['key']})
        self.assertEqual(self.vault.view('alice', []), [])

    def test_rejects_unrecognized_fields_missing_values_and_owner_override(self):
        for body in [
            {'action': 'save', 'key': self.req['key'], 'values': {'token': 'x'}},
            {'action': 'save', 'key': self.req['key'], 'values': {'evil': 'x'}},
            {'action': 'save', 'key': self.req['key'], 'owner': 'bob', 'values': {}},
            {'action': 'read', 'key': self.req['key']}, [],
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.vault.change('alice', [self.req], body)
        self.assertFalse(self.vault.root.exists())

    def test_corruption_or_ciphertext_swapped_between_users_fails_closed(self):
        self.save(); self.save('bob')
        alice, bob = self.vault._path('alice'), self.vault._path('bob')
        bob.write_bytes(alice.read_bytes())
        with self.assertRaises(ValueError): self.vault.view('bob', [self.req])
        raw = bytearray(alice.read_bytes()); raw[-1] ^= 1; alice.write_bytes(raw)
        with self.assertRaises(ValueError): self.vault.view('alice', [self.req])

    def test_missing_key_is_never_silently_replaced(self):
        self.save(); (self.vault.root/'master.key').unlink()
        with self.assertRaises(ValueError): self.save('bob')
        self.assertFalse((self.vault.root/'master.key').exists())

    def test_rejects_unsafe_permissions_and_symlinks(self):
        self.save(); key = self.vault.root/'master.key'; key.chmod(0o644)
        with self.assertRaises(ValueError): self.vault.view('alice', [self.req])
        key.chmod(0o600)
        target = self.root/'outside'; target.write_bytes(self.vault._path('alice').read_bytes()); target.chmod(0o600)
        self.vault._path('alice').unlink(); self.vault._path('alice').symlink_to(target)
        with self.assertRaises(OSError): self.vault.view('alice', [self.req])

    def test_schema_change_creates_new_requirement_without_reusing_secret(self):
        self.save()
        changed = dict(self.req, key=credentials.requirement_id('different-skill', self.req))
        view = self.vault.view('alice', [changed])
        self.assertEqual([row['status'] for row in view], ['missing', 'inactive'])

    def test_invalid_owner_cannot_escape_store(self):
        for owner in ('..', '../alice', '/tmp/alice', ''):
            with self.assertRaises(ValueError): self.vault.view(owner, [])

    def test_deleted_owner_cannot_inherit_values_on_recreation(self):
        self.save(); self.save('bob')
        self.vault.delete_owner('alice')
        self.assertEqual(self.vault.view('alice', [self.req])[0]['status'], 'missing')
        self.assertEqual(self.vault.view('bob', [self.req])[0]['status'], 'saved')

    def test_concurrent_updates_do_not_lose_other_users(self):
        errors = []
        def save(name):
            try: self.save(name)
            except Exception as error: errors.append(type(error).__name__)
        workers = [threading.Thread(target=save, args=('user'+str(i),)) for i in range(12)]
        for thread in workers: thread.start()
        for thread in workers: thread.join()
        self.assertEqual(errors, [])
        for i in range(12): self.assertEqual(self.vault.view('user'+str(i), [self.req])[0]['status'], 'saved')


class DeclarationTests(unittest.TestCase):
    def test_unreviewed_disabled_foreign_and_unselected_project_requirements_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); agent = root/'.prime/agent'; agent.mkdir(parents=True)
            row = {'owner': 'alice', 'status': 'installed', 'enabled': True, 'name': 'Example', 'credentialRequirements': [DECLARATION]}
            skills = {'good': row, 'pending': dict(row, status='pending'), 'foreign': dict(row, owner='bob'),
                      'disabled': dict(row, enabled=False), 'project': dict(row, scope='project', projectId='p_test')}
            (agent/'webui-metadata.json').write_text(json.dumps({'skills': skills, 'projects': {}}))
            self.assertEqual([r['skillId'] for r in credentials.catalog('alice', root)], ['good'])
            self.assertEqual([r['skillId'] for r in credentials.catalog('bob', root)], ['foreign'])

    def test_published_inventory_is_owner_scoped_and_live_skill_tree_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); agent = root/'.prime/agent'; agent.mkdir(parents=True)
            (agent/'skill-inventory.json').write_text(json.dumps({'owner': 'alice', 'skills': [
                {'id': 'managed:test', 'name': 'Test', 'credentialRequirements': [DECLARATION]}]}))
            self.assertEqual(len(credentials.catalog('alice', root)), 1)
            self.assertEqual(credentials.catalog('bob', root), [])

    def test_manifest_rejects_duplicate_ids_unknown_delivery_and_bad_shapes(self):
        for rows in [[DECLARATION, DECLARATION], [dict(DECLARATION, env='TOKEN')],
                     [dict(DECLARATION, fields=[])], [dict(DECLARATION, id='../escape')]]:
            with self.assertRaises(ValueError): credentials.declarations({'version': 1, 'credentials': rows})

    def test_explicit_protected_global_inventory_is_shared_without_user_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); agent = root/'.prime/agent'; agent.mkdir(parents=True)
            path = agent/'global-credential-inventory.json'
            path.write_text(json.dumps({'version': 1, 'scope': 'global', 'skills': [
                {'id': 'managed:test', 'scope': 'global', 'credentialRequirements': [DECLARATION]}]}))
            path.chmod(0o600)
            self.assertEqual(credentials.catalog('alice', root), credentials.catalog('bob', root))
            self.assertEqual(len(credentials.catalog('bob', root)), 1)
            path.chmod(0o644)
            with self.assertRaises(ValueError): credentials.catalog('bob', root)


class CredentialHTTPTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('vault_auth_test', Path(__file__).with_name('auth.py'))
        self.auth = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.auth)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth._credential_module = credentials
        now = time.time()
        for name in ['alice', 'bob']:
            self.auth.SESSIONS[name] = {'user': name, 'role': 'user', 'csrf': name+'-csrf', 'seen': now,
                                       'persisted': now, 'expires': now+3600}
        patches = [mock.patch.object(self.auth, 'load_users', return_value={'users': {'alice': {'enabled': True}, 'bob': {'enabled': True}}}),
                   mock.patch.dict(os.environ, {'PRIME_CREDENTIALS_ENABLED': '1'}),
                   mock.patch.object(self.auth, 'credential_path', return_value=self.root/'web-auth.json'),
                   mock.patch.object(credentials, 'catalog', return_value=[requirement()])]
        for patch in patches: patch.start(); self.addCleanup(patch.stop)
        self.server = self.auth.ThreadingHTTPServer(('127.0.0.1', 0), self.auth.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method='GET', cookie=None, body=None, csrf=None, spoof=None, path='/auth/credentials'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if cookie: headers['Cookie'] = 'prime_session='+cookie
        if csrf: headers['X-Prime-CSRF'] = csrf
        if spoof: headers['X-Prime-User'] = spoof
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse(); status, data = response.status, json.loads(response.read()); conn.close()
        return status, data

    def test_spoofed_identity_header_does_not_authenticate(self):
        self.assertEqual(self.request(spoof='alice')[0], 401)

    def test_unactivated_feature_fails_closed(self):
        with mock.patch.dict(os.environ, {'PRIME_CREDENTIALS_ENABLED': '0'}):
            self.assertEqual(self.request(cookie='alice')[0], 503)

    def test_shared_host_console_requires_current_administrator_role(self):
        for account, status in [({'enabled': True, 'role': 'user'}, 403),
                                ({'enabled': False, 'role': 'admin'}, 403),
                                ({'enabled': True, 'role': 'admin'}, 200)]:
            with mock.patch.object(self.auth, 'load_users', return_value={'users': {'alice': account}}):
                conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
                conn.request('GET', '/auth/check-admin', headers={'Cookie': 'prime_session=alice', 'X-Prime-Role': 'admin'})
                response = conn.getresponse(); response.read(); conn.close()
                self.assertEqual(response.status, status)
        config = (Path(__file__).parents[1]/'nginx/prime-agent.conf').read_text()
        self.assertEqual(config.count('auth_request /_auth_admin_check;'), 2)

    def test_session_bound_csrf_not_just_matching_cookie_text(self):
        body = {'action': 'save', 'key': requirement()['key'], 'values': {'username': 'x', 'token': 'HTTP_SECRET'}}
        self.assertEqual(self.request('POST', 'alice', body, 'forged')[0], 403)
        self.assertEqual(self.request('POST', 'alice', body, 'alice-csrf')[0], 200)
        self.assertEqual(self.request(cookie='bob', spoof='alice')[1]['credentials'][0]['status'], 'missing')
        self.assertEqual(self.request(cookie='alice', spoof='bob')[1]['credentials'][0]['status'], 'saved')
        self.assertNotIn('HTTP_SECRET', json.dumps(self.request(cookie='alice')))

    def test_expired_and_disabled_sessions_cannot_read(self):
        self.auth.SESSIONS['alice']['expires'] = 1
        with mock.patch.object(self.auth, 'save_sessions_locked'):
            self.assertEqual(self.request(cookie='alice')[0], 401)
        with mock.patch.object(self.auth, 'load_users', return_value={'users': {'bob': {'enabled': False}}}):
            self.assertEqual(self.request(cookie='bob')[0], 401)

    def test_owner_override_rejected(self):
        body = {'action': 'save', 'key': requirement()['key'], 'owner': 'bob', 'values': {'username': 'x', 'token': 'x'}}
        self.assertEqual(self.request('POST', 'alice', body, 'alice-csrf')[0], 400)

    def test_connection_settings_use_real_session_and_csrf(self):
        path = '/auth/connections'
        self.assertEqual(self.request(spoof='alice', path=path)[0], 401)
        self.assertEqual(self.request('POST', 'alice', {'action': 'save'}, 'wrong', path=path)[0], 403)
        self.assertEqual(self.request('POST', 'alice', {'action': 'save', 'owner': 'bob'}, 'alice-csrf', path=path)[0], 400)
        with mock.patch.object(connections.Connections, 'metadata', return_value={}):
            status, body = self.request(cookie='alice', spoof='bob', path=path)
        self.assertEqual(status, 200)
        self.assertEqual(body['connections'], [])
        with mock.patch.dict(os.environ, {'PRIME_CREDENTIALS_ENABLED': '0'}):
            self.assertEqual(self.request(cookie='alice', path=path)[0], 503)


if __name__ == '__main__': unittest.main()
