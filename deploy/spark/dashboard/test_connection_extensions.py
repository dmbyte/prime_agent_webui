import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import connection_approvals
import connection_browser_worker
import connection_browser
import connection_http_worker
import connection_native
import connection_sessions
import connection_sol
import connections
import skill_credentials
import test_connections as fixtures


class NativeTests(unittest.TestCase):
    def test_updater_restarts_only_an_already_active_connection_broker(self):
        import subprocess
        source = (Path(__file__).parents[1]/'update/update-webui.sh').read_text()
        block = 'if systemctl --user is-active --quiet prime-connection-broker.service; then'
        block += source.split(block, 1)[1].split('\nfi', 1)[0]+'\nfi\n'
        for active, restart_code in ((0, 0), (3, 0), (0, 42)):
            with self.subTest(active=active, restart_code=restart_code):
                stub = ('set -e\nsystemctl() { if [ "$2" = is-active ]; then return '+str(active)
                    +'; fi; printf "%s\\n" "$*"; return '+str(restart_code)+'; }\n')
                result = subprocess.run(['bash', '-c', stub+block], capture_output=True, text=True)
                self.assertEqual(result.stdout, '--user restart prime-connection-broker.service\n' if active == 0 else '')
                self.assertEqual(result.returncode, restart_code if active == 0 else 0)

    def test_browser_policy_uses_ip_pinned_connect_not_dns_only_tcp(self):
        runtime=mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            runtime.root=Path(directory)
            runtime.image.return_value='fixture-image'
            with mock.patch.object(connection_browser.subprocess,'Popen',side_effect=RuntimeError('stop after policy')):
                with self.assertRaises(RuntimeError):
                    connection_browser.BrowserSession(runtime,'pc-'+'1'*16,
                        {'endpoint':'https://192.168.1.4','username':'fixture','password':'synthetic'},'browser',time.time()+60)
            call=runtime.run.call_args.args[0]
            self.assertIn('--policy',call)
            # cleanup removes the policy file, so intercept its write to inspect.
        source=Path(connection_browser.__file__).read_text()
        self.assertNotIn("'protocol': 'tcp'",source)
        self.assertIn("'tls': 'skip'",source)
        self.assertIn("'allowed_ips': [host+'/32']",source)
        worker=Path(connection_browser_worker.__file__).read_text()
        self.assertIn("os.environ.get('HTTPS_PROXY')",worker)
        self.assertIn("'proxy': {'server': proxy}",worker)

    def test_private_browser_activation_does_not_enable_ipmi(self):
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_CONSOLES_ENABLED':'1',
                                         'PRIME_CONNECTION_CONSOLE_ADAPTERS':'bmc-browser,bmc-kvm'}):
            self.assertTrue(connections.permitted({'adapter':'bmc-browser'},fixtures.POLICY))
            self.assertTrue(connections.permitted({'adapter':'bmc-kvm'},fixtures.POLICY))
            self.assertFalse(connections.permitted({'adapter':'ipmi-sol'},fixtures.POLICY))
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_CONSOLES_ENABLED':'1','PRIME_CONNECTION_CONSOLE_ADAPTERS':'unknown'}):
            with self.assertRaises(ValueError): connections.console_adapters()

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

    def test_explicit_direct_choice_preserves_tls_policy_without_native_fallback(self):
        self.manager.native = mock.Mock()
        self.manager.change('alice', dict(self.body, id=self.key, httpTransport='direct'))
        self.manager.change('alice', dict(self.body, id=self.key))  # Older client must preserve the explicit choice.
        self.assertEqual(self.manager.store._load('alice')[self.key]['httpTransport'], 'direct')
        self.manager.revoke(fixtures.TASK)
        self.token = self.manager.issue('alice', fixtures.TASK, fixtures.PROJECT, fixtures.POLICY)
        request = {'action':'call','token':self.token,'connection':self.key,'operation':'github.repository','arguments':{'repository':'fixture/repo'}}
        with mock.patch.object(connections,'get_json',return_value={'private':True}) as direct:
            self.assertEqual(self.manager.dispatch(request,'alice'), {'repository':'fixture/repo','private':True})
            self.assertIs(direct.call_args.kwargs['ignore_certificate_errors'], False)
        self.manager.native.lease.assert_not_called()

    def test_explicit_native_unavailable_cannot_fall_back_or_be_task_selected(self):
        self.manager.change('alice', dict(self.body, id=self.key, httpTransport='openshell'))
        self.manager.revoke(fixtures.TASK)
        token = self.manager.issue('alice', fixtures.TASK, fixtures.PROJECT, fixtures.POLICY)
        request = {'action':'call','token':token,'connection':self.key,'operation':'github.repository','arguments':{'repository':'fixture/repo'}}
        with mock.patch.object(connections,'get_json') as direct:
            with self.assertRaises(PermissionError): self.manager.dispatch(request,'alice')
            with self.assertRaises(ValueError): self.manager.dispatch(dict(request,httpTransport='direct'),'alice')
            direct.assert_not_called()

    def test_transport_validation_and_console_do_not_accept_http_override(self):
        for invalid in ('auto', True, [], None):
            with self.assertRaises(ValueError): self.manager.change('alice',dict(self.body,httpTransport=invalid))
        self.configure('bmc-browser')
        with self.assertRaises(ValueError): self.manager.change('alice',dict(self.body,httpTransport='direct'))

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
    def test_native_worker_allows_only_exact_redfish_slash_canonicalization(self):
        from urllib.request import Request
        handler = connection_http_worker.NoRedirect()
        source = Request('https://192.168.1.4/redfish/v1/Systems',headers={'Authorization':'Basic placeholder'})
        result = handler.redirect_request(source,None,308,'',{},source.full_url+'/')
        self.assertEqual(result.full_url,source.full_url+'/')
        self.assertEqual(result.get_header('Authorization'),'Basic placeholder')
        for url in ('https://evil.example/redfish/v1/Systems/','http://192.168.1.4/redfish/v1/Systems/',source.full_url+'/?x=1',source.full_url+'/other'):
            self.assertIsNone(handler.redirect_request(source,None,308,'',{},url))
        source = Request('https://api.github.com/repos/a/b')
        self.assertIsNone(handler.redirect_request(source,None,308,'',{},source.full_url+'/'))

    def test_direct_transport_canonical_redirect_is_bounded_and_origin_pinned(self):
        import io
        def response(status, location=None):
            item = mock.Mock(status=status)
            item.getheader.side_effect = lambda name, default=None: {'Location':location,'Content-Type':'application/json','Content-Encoding':'identity'}.get(name, default)
            item.read1.side_effect = io.BytesIO(b'{"Members":[]}').read
            return item
        with mock.patch.object(connections.http.client,'HTTPSConnection') as factory:
            first, second = mock.Mock(), mock.Mock()
            first.getresponse.return_value=response(308,'/redfish/v1/Systems/')
            second.getresponse.return_value=response(200)
            factory.side_effect=[first,second]
            self.assertEqual(connections.get_json('https://192.168.1.4','/redfish/v1/Systems',{}),{'Members':[]})
            self.assertEqual(second.request.call_args.args[:2],('GET','/redfish/v1/Systems/'))
        for location in ('https://evil.example/redfish/v1/Systems/','/redfish/v1/Systems/other','//evil.example/'):
            with mock.patch.object(connections.http.client,'HTTPSConnection') as factory:
                factory.return_value.getresponse.return_value=response(308,location)
                with self.assertRaises(ValueError): connections.get_json('https://192.168.1.4','/redfish/v1/Systems',{})
                self.assertEqual(factory.call_count,1)

    def test_ipmi_diagnostics_are_fixed_and_never_echo_upstream(self):
        for message, expected in ((b'no matching cipher suite SECRET', 'cipher 17'),
                                  (b'RAKP 2 HMAC is invalid SECRET', 'authentication'),
                                  (b'privilege level error SECRET', 'privilege'),
                                  (b'unknown SECRET', 'Secure IPMI')):
            result = connection_sol.status_failure(message)
            self.assertIn(expected, result)
            self.assertNotIn('SECRET', result)

    def test_sol_does_not_accept_keys_before_verified_activation(self):
        sol = connection_sol.SOL.__new__(connection_sol.SOL)
        sol.master, sol.connected = 1, False
        sol.process = mock.Mock(); sol.process.poll.return_value = None
        with mock.patch.object(connection_sol.os, 'write') as write:
            with self.assertRaises(ValueError): sol.send({'sessionId':'test','requestId':'a'*32,'key':'enter'})
            write.assert_not_called()

    def test_sol_activation_acknowledgement_survives_split_reads(self):
        import codecs
        sol = connection_sol.SOL.__new__(connection_sol.SOL)
        sol.master, sol.password, sol.connected = 42, 'ab', False
        sol.tail = sol.screen = sol.handshake_tail = ''
        sol.decoder = codecs.getincrementaldecoder('utf8')('replace')
        sol.process = mock.Mock(); sol.process.poll.return_value = None
        for chunk, connected in ((b'[SOL Session oper', False), (b'ational. Use ~? for help]', True)):
            with mock.patch.object(connection_sol.select, 'select', side_effect=[([42],[],[]),([],[],[])]), mock.patch.object(connection_sol.os, 'read', return_value=chunk):
                self.assertEqual(sol.read()['connected'], connected)

    def test_login_frame_requires_one_same_origin_unambiguous_form(self):
        browser = connection_browser_worker.Browser.__new__(connection_browser_worker.Browser)
        browser.origin = 'https://192.168.1.4'
        frame = mock.Mock(url=browser.origin+'/login.html')
        frame.locator.return_value.count.return_value = 1
        other = mock.Mock(url='https://evil.example/login')
        browser.page = mock.Mock(frames=[other,frame])
        self.assertIs(browser.login_frame(), frame)
        other.locator.assert_not_called()
        browser.page.frames = [frame,frame]
        with self.assertRaises(ValueError): browser.login_frame()
        browser.page.frames = [frame]
        frame.locator.return_value.count.return_value = 2
        with self.assertRaises(ValueError): browser.login_frame()

    def test_login_waits_for_username_field_during_frame_load(self):
        browser = connection_browser_worker.Browser.__new__(connection_browser_worker.Browser)
        browser.origin = 'https://192.168.1.4'
        frame = mock.Mock(url=browser.origin+'/login.html')
        frame.locator.return_value.count.side_effect = [1, 0, 1, 1]
        browser.page = mock.Mock(frames=[frame])
        self.assertIs(browser.login_frame(), frame)
        browser.page.wait_for_timeout.assert_called_once_with(100)

    def test_password_not_in_ipmi_argv_and_fixed_cipher(self):
        values = {'endpoint': 'https://192.168.1.4', 'username': 'fixture', 'password': 'fixture-password'}
        args = connection_sol.command(values, 'sol', 'activate')
        self.assertNotIn(values['password'], args)
        self.assertEqual(args[args.index('-C')+1], '17')
        legacy = connection_sol.command(dict(values, ipmiCipherSuite=3), 'chassis', 'power', 'status')
        self.assertEqual(legacy[legacy.index('-C')+1], '3')
        for invalid in (0, 1, True, '3', None):
            with self.assertRaises(ValueError): connection_sol.command(dict(values, ipmiCipherSuite=invalid), 'sol', 'activate')
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
        prior = mock.Mock()
        browser.console_canvases_before = {frame: [prior]}
        node = mock.Mock()
        node.evaluate.return_value = True
        nodes = mock.Mock()
        nodes.count.return_value = 1
        nodes.nth.return_value = node
        frame.locator.side_effect = lambda selector: mock.Mock(count=lambda: 0) if selector.startswith('input') else nodes
        self.assertEqual(browser.canvases(), [])
        node.bounding_box.assert_not_called()
        # A newly inserted canvas in that very same frame is a valid candidate.
        node.evaluate.return_value = False
        node.bounding_box.return_value = {'width': 800, 'height': 600}
        self.assertEqual(browser.canvases(), [node])


if __name__ == '__main__':
    unittest.main()
