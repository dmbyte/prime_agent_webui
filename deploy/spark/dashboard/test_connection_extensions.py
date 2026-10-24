import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import connection_approvals
import connection_browser_worker
import connection_native
import connection_sessions
import connection_sol
import connections
import skill_credentials
import test_connections as fixtures


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root/'images.json'
        self.manifest.write_text(json.dumps({'general': {'image': 'local/prime-openshell-general:0.9.5-'+'a'*12}}))
        self.calls = []
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return b'{"private":true}'
        self.runtime = connection_native.NativeRuntime(self.root/'leases', self.manifest, run)

    def test_native_secret_only_in_provider_environment_and_cleanup_order(self):
        with self.runtime.lease({'adapter': 'github-readonly'}, {'token': fixtures.SECRET}, time.time()+90) as lease:
            self.assertEqual(lease.get_json('https://api.github.com', '/repos/a/b', {'Authorization': fixtures.SECRET}), {'private': True})
            for path in self.runtime.root.rglob('*'):
                if path.is_file(): self.assertNotIn(fixtures.SECRET, path.read_text())
            with self.assertRaises(PermissionError): lease.get_json('https://evil.example', '/repos/a/b', {})
        self.assertFalse(list(self.runtime.root.glob('pc-*.json')))
        for argv, kwargs in self.calls:
            self.assertNotIn(fixtures.SECRET, json.dumps(argv))
            self.assertNotIn(fixtures.SECRET.encode(), kwargs.get('input') or b'')
        secrets = [kwargs['env']['PRIME_UPSTREAM_TOKEN'] for argv, kwargs in self.calls if 'env' in kwargs]
        self.assertEqual(secrets, [fixtures.SECRET])
        self.assertEqual([c[0][:2] for c in self.calls[-3:]], [['sandbox', 'delete'], ['provider', 'delete'], ['profile', 'delete']])
        create = next(c[0] for c in self.calls if c[0][:2] == ['sandbox', 'create'])
        self.assertNotIn('--driver-config-json', create)
        self.assertIn('--no-auto-providers', create)
        self.assertNotIn('prime-container-entrypoint', str(self.calls))

    def test_profile_is_exact_host_read_only_and_private_ip_pinned(self):
        profile = connection_native.profile('pc-'+'a'*32, 'https://192.168.1.4', ['/redfish/v1/Systems'])
        endpoint = profile['endpoints'][0]
        self.assertEqual(endpoint['allowed_ips'], ['192.168.1.4/32'])
        self.assertEqual(endpoint['rules'], [{'allow': {'method': 'GET', 'path': '/redfish/v1/Systems'}}])
        self.assertNotIn('tls', endpoint)
        self.assertEqual(profile['binaries'], ['/usr/bin/python3.11'])

    def test_basic_uses_one_header_placeholder_for_encoded_pair(self):
        _, _, value, style = connection_native.http_binding({'adapter': 'redfish-readonly', 'endpoint': 'https://192.168.1.4'},
                                                           {'username': 'fixture', 'password': fixtures.SECRET})
        self.assertEqual(connection_native.base64.b64decode(value).decode(), 'fixture:'+fixtures.SECRET)
        self.assertEqual(style, 'basic')

    def test_cleanup_failure_retains_journal_and_reaper_denies_new_work(self):
        name = 'pc-'+'c'*16
        skill_credentials._write(self.runtime.root/(name+'.json'), json.dumps({'expiresAt': 1}).encode())
        self.runtime.run = mock.Mock(side_effect=RuntimeError('synthetic'))
        with self.assertRaises(RuntimeError): self.runtime.reap()
        self.assertTrue((self.runtime.root/(name+'.json')).exists())
        with self.assertRaises(RuntimeError):
            with self.runtime.lease({'adapter': 'github-readonly'}, {'token': fixtures.SECRET}, time.time()+90): pass

    def test_failed_creation_cleans_exact_resources_and_rejects_unpinned_image(self):
        base = self.runtime.run
        def run(argv, **kwargs):
            if argv[:2] == ['sandbox', 'create']: raise RuntimeError('fixture failure')
            return base(argv, **kwargs)
        self.runtime.run = run
        with self.assertRaises(RuntimeError):
            with self.runtime.lease({'adapter': 'github-readonly'}, {'token': fixtures.SECRET}, time.time()+90): pass
        self.assertFalse(list(self.runtime.root.glob('pc-*.json')))
        self.manifest.write_text('{"general":{"image":"arbitrary:latest"}}')
        with self.assertRaises(ValueError): self.runtime.image()

    def test_native_capacity_is_bounded_and_released_after_failure(self):
        with self.runtime.lease({'adapter': 'github-readonly'}, {'token': 'dummy'}, time.time()+90):
            with self.runtime.lease({'adapter': 'github-readonly'}, {'token': 'dummy'}, time.time()+90):
                with self.assertRaises(RuntimeError):
                    with self.runtime.lease({'adapter': 'github-readonly'}, {'token': 'dummy'}, time.time()+90): pass
        with self.runtime.lease({'adapter': 'github-readonly'}, {'token': 'dummy'}, time.time()+90): pass


class ConsoleTests(unittest.TestCase):
    setUp = fixtures.ConnectionTests.setUp
    save_meta = fixtures.ConnectionTests.save_meta
    save_credential = fixtures.ConnectionTests.save_credential

    def test_native_failure_never_falls_back_to_direct_transport(self):
        self.manager.native = mock.Mock()
        self.manager.native.lease.side_effect = RuntimeError('native unavailable')
        with mock.patch.object(connections, 'get_json') as direct:
            with self.assertRaises(RuntimeError):
                self.manager.dispatch({'action': 'call', 'token': self.token, 'connection': self.key,
                    'operation': 'github.repository', 'arguments': {'repository': 'example/demo'}}, 'alice')
            direct.assert_not_called()

    def test_private_browser_receives_saved_policy_not_task_override(self):
        self.configure('bmc-browser')
        self.call('browser.open')
        self.assertIs(self.factory.call_args.args[2]['ignoreCertificateErrors'], False)
        self.manager.vault.change('alice', [self.req], {'action': 'save', 'key': self.req['key'],
                                  'values': {}, 'ignoreCertificateErrors': True})
        self.manager.sessions.reap()
        self.worker.close.assert_called_once()
        self.manager.change('alice', dict(self.body, id=self.key))
        self.manager.revoke(fixtures.TASK)
        self.token = self.manager.issue('alice', fixtures.TASK, fixtures.PROJECT, fixtures.POLICY)
        self.call('browser.open')
        self.assertIs(self.factory.call_args.args[2]['ignoreCertificateErrors'], True)
        with self.assertRaises(ValueError):
            self.call('browser.open', {'requestId': 'b'*32, 'ignoreCertificateErrors': True})

    def configure(self, adapter='ipmi-sol'):
        patch = mock.patch.dict(os.environ, {'PRIME_CONNECTION_CONSOLES_ENABLED': '1'})
        patch.start(); self.addCleanup(patch.stop)
        self.meta['skills']['s_fixture']['credentialRequirements'] = [{
            'id': 'console', 'label': 'Fixture console', 'adapter': adapter,
            'fields': [{'id': name, 'label': name} for name in ('endpoint', 'username', 'password')]}]
        self.save_meta()
        self.req = self.manager.requirements('alice')[0]
        self.save_credential({'endpoint': 'https://192.168.1.4', 'username': 'fixture', 'password': fixtures.SECRET})
        self.body = dict(self.body, credentialKey=self.req['key'], endpoint='https://192.168.1.4')
        self.key = self.manager.change('alice', self.body)['id']
        self.manager.revoke(fixtures.TASK)
        self.token = self.manager.issue('alice', fixtures.TASK, fixtures.PROJECT, fixtures.POLICY)
        self.worker = mock.Mock()
        self.worker.read.return_value = {'text': 'Synthetic boot screen'}
        self.worker.send.return_value = {'sent': True}
        self.factory = mock.Mock(return_value=self.worker)
        self.manager.sessions = connection_sessions.Sessions(self.manager, mock.Mock(), self.factory, self.factory)

    def call(self, operation='sol.open', arguments=None, **extra):
        request = {'action': 'call', 'token': self.token, 'connection': self.key, 'operation': operation,
                   'arguments': arguments if arguments is not None else {'requestId': 'a'*32}, **extra}
        return self.manager.dispatch(request, 'alice')

    def approve(self, result, owner='alice', approve=True):
        return self.manager.change(owner, {'action': 'decide-console', 'id': result['approvalId'], 'approve': approve})

    def open(self):
        self.approve(self.call())
        return self.call()['sessionId']

    def test_sol_open_and_input_need_human_exact_once_approval(self):
        self.configure()
        pending = self.call()
        self.factory.assert_not_called()
        self.assertTrue(pending['approvalRequired'])
        self.assertEqual(self.manager.view('bob')['consoleApprovals'], [])
        with self.assertRaises(ValueError): self.approve(pending, owner='bob')
        self.approve(pending)
        key = self.call()['sessionId']
        args = {'sessionId': key, 'requestId': 'b'*32, 'key': 'f9'}
        pending = self.call('sol.input', args)
        self.worker.send.assert_not_called()
        self.approve(pending)
        self.assertEqual(self.call('sol.input', args), {'sent': True})
        self.worker.send.assert_called_once_with(args)
        with self.assertRaises(PermissionError): self.call('sol.input', args)
        changed = self.call('sol.input', dict(args, key='enter'))
        self.assertTrue(changed['approvalRequired'])

    def test_read_close_and_cross_task_access(self):
        self.configure(); key = self.open()
        self.assertEqual(self.call('sol.read', {'sessionId': key}), {'text': 'Synthetic boot screen'})
        self.meta['tasks']['d'*32] = {'owner': 'alice', 'projectId': fixtures.PROJECT, 'status': 'running'}; self.save_meta()
        other = self.manager.issue('alice', 'd'*32, fixtures.PROJECT, fixtures.POLICY)
        with self.assertRaises(PermissionError): self.call('sol.read', {'sessionId': key}, token=other)
        self.call('sol.close', {'sessionId': key})
        self.worker.close.assert_called_once()
        with self.assertRaises(PermissionError): self.call('sol.read', {'sessionId': key})

    def test_revocation_task_stop_rotation_idle_and_expiry_close_workers(self):
        for condition in ('disabled', 'stopped', 'rotation', 'idle', 'expiry'):
            with self.subTest(condition=condition):
                self.configure(); key = self.open()
                if condition == 'disabled': self.manager.change('alice', dict(self.body, id=self.key, enabled=False))
                if condition == 'stopped': self.meta['tasks'][fixtures.TASK]['status'] = 'completed'; self.save_meta()
                if condition == 'rotation': self.save_credential({'password': 'new-fixture'})
                if condition == 'idle': self.manager.sessions.sessions[key]['lastUse'] -= 301
                if condition == 'expiry': self.manager.sessions.sessions[key]['expiresAt'] = 1
                self.manager.sessions.reap()
                self.worker.close.assert_called_once()
                self.assertFalse(self.manager.sessions.sessions)
                self.meta['tasks'][fixtures.TASK]['status'] = 'running'; self.save_meta()

    def test_disabled_console_flag_and_network_mode_deny_new_grants(self):
        self.configure()
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_CONSOLES_ENABLED': '0'}):
            with self.assertRaises(PermissionError): self.call()
            self.assertIsNone(self.manager.issue('alice', 'd'*32, fixtures.PROJECT, fixtures.POLICY))
        for policy in (dict(fixtures.POLICY, networkMode='internet'), dict(fixtures.POLICY, profile='general')):
            self.assertIsNone(self.manager.issue('alice', 'd'*32, fixtures.PROJECT, policy))

    def test_unavailable_runtime_no_secret_read_or_model_approval_api(self):
        self.configure(); self.manager.sessions = None
        for operation in ('sol.open', 'get_secret', 'sol.power', 'sol.deactivate'):
            with self.assertRaises(PermissionError): self.call(operation)
        with self.assertRaises((ValueError, PermissionError)):
            self.manager.dispatch({'action': 'decide-console', 'token': self.token, 'id': 'a_'+'b'*64, 'approve': True}, 'alice')

    def test_invalid_inputs_rejected_before_asking_human(self):
        self.configure(); key = self.open()
        for args in ({'text': '~.'}, {'text': 'hello\n'}, {'key': 'ctrl-alt-delete'}, {'key': []}, {'script': 'read_cookie()'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.call('sol.input', {'sessionId': key, 'requestId': 'b'*32, **args})

    def test_deny_expiry_rotation_and_invalid_owner_approval(self):
        self.configure(); pending = self.call()
        self.approve(pending, approve=False)
        with self.assertRaises(PermissionError): self.call()
        pending = self.call(arguments={'requestId': 'c'*32})
        self.save_credential({'password': 'new-fixture'})
        with self.assertRaises(ValueError): self.approve(pending)

    def test_browser_no_arbitrary_code_cookie_or_navigation_api(self):
        self.configure('bmc-browser')
        result = self.call('browser.open'); key = result['sessionId']
        self.call('browser.capture', {'sessionId': key})
        for operation in ('browser.evaluate', 'browser.cookies', 'browser.goto', 'browser.input', 'kvm.input'):
            with self.assertRaises(PermissionError): self.call(operation, {'sessionId': key})
        self.assertNotIn(fixtures.SECRET, json.dumps(result))

    def test_revoke_during_open_closes_worker_before_return(self):
        self.configure('bmc-browser')
        def factory(*args):
            self.manager.revoke(fixtures.TASK)
            return self.worker
        self.manager.sessions.browser_factory = factory
        with self.assertRaises((PermissionError, OSError)): self.call('browser.open')
        # Failed verification must not leave a secret-authenticated worker alive.
        self.worker.close.assert_called_once()
        self.assertFalse(self.manager.sessions.sessions)


class ConsoleBoundaryTests(unittest.TestCase):
    def test_password_not_in_ipmi_argv_and_fixed_cipher(self):
        values = {'endpoint': 'https://192.168.1.4', 'username': 'fixture', 'password': 'fixture-password'}
        args = connection_sol.command(values, 'sol', 'activate')
        self.assertNotIn(values['password'], args)
        self.assertEqual(args[args.index('-C')+1], '17')
        self.assertEqual(connection_sol.environment(values)['IPMI_PASSWORD'], values['password'])
        for password in ('x'*21, 'bad\x00value'):
            with self.assertRaises(ValueError): connection_sol.command(dict(values, password=password), 'sol', 'activate')

    def test_split_password_never_escapes_stream_filter(self):
        for secret in ('aaaaab', 'SECRET', 'abaaba'):
            text = 'screen '+secret+' boot messages '*10
            for cut in range(1, len(text)):
                one, tail = connection_sol.filter_stream(text[:cut], secret)
                two, _ = connection_sol.filter_stream(tail+text[cut:], secret)
                self.assertNotIn(secret, one+two)
                self.assertIn('[credential withheld]', one+two)

    def test_browser_origin_and_websocket_pins(self):
        browser = connection_browser_worker.Browser.__new__(connection_browser_worker.Browser)
        browser.origin = 'https://192.168.1.4'
        for url in ('https://evil.example', 'https://192.168.1.40', 'http://192.168.1.4',
                    'https://192.168.1.4:444', 'https://user:pass@192.168.1.4'):
            self.assertFalse(browser.allowed(url))
        self.assertTrue(browser.allowed('https://192.168.1.4/html/index.html'))
        self.assertTrue(browser.allowed('wss://192.168.1.4/console', websocket=True))
        self.assertFalse(browser.allowed('ws://192.168.1.4/console', websocket=True))

    def test_preexisting_management_chart_is_never_a_console(self):
        browser = connection_browser_worker.Browser.__new__(connection_browser_worker.Browser)
        browser.origin, browser.kvm = 'https://192.168.1.4', True
        frame = mock.Mock(url='https://192.168.1.4/home')
        page = mock.Mock(frames=[frame])
        browser.context = mock.Mock(pages=[page])
        browser.console_frames_before = {(page, frame.url)}
        self.assertEqual(browser.canvases(), [])
        frame.locator.assert_not_called()


if __name__ == '__main__':
    unittest.main()
