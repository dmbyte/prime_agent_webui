"""Synthetic end-to-end authorization and no-replay tests; never contacts a BMC."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import connections
import connection_installation as install
from connection_approvals import Approvals
import skill_credentials as credentials

TASK = 'a'*32
PROJECT = 'p_'+'b'*24
SYSTEM = '/redfish/v1/Systems/1'
MEDIA = '/redfish/v1/Managers/1/VirtualMedia/CD'
ISO = 'http://192.168.1.9:8080/installer.iso'


class InstallationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name); self.root = self.home/'config'; self.root.mkdir(mode=0o700)
        self.agent = self.home/'.prime/agent'; self.agent.mkdir(parents=True)
        self.meta = {'projects': {PROJECT: {'owner': 'alice'}},
            'tasks': {TASK: {'owner': 'alice', 'projectId': PROJECT, 'status': 'running'}},
            'skills': {'s_test': {'owner': 'alice', 'status': 'installed', 'enabled': True,
                'credentialRequirements': [{'id': 'bmc', 'label': 'Installation', 'adapter': 'redfish-install',
                    'fields': [{'id': x, 'label': x} for x in ('endpoint', 'username', 'password')]}]}}}
        self.save_meta()
        credentials._write(self.root/'web-auth.json', json.dumps({'users': {'alice': {'enabled': True}, 'bob': {'enabled': True}}}).encode())
        env = mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED': '1', 'PRIME_CREDENTIALS_ENABLED': '1',
                                         'PRIME_CONNECTION_BMC_WRITES_ENABLED': '1'})
        env.start(); self.addCleanup(env.stop)
        if not Path('/proc/self/stat').exists():
            identity = mock.patch.object(connections, 'process_identity', return_value='fixture-process')
            identity.start(); self.addCleanup(identity.stop)
        self.manager = connections.Connections(self.root, self.home)
        self.req = self.manager.requirements('alice')[0]
        self.manager.vault.change('alice', [self.req], {'action': 'save', 'key': self.req['key'],
            'values': {'endpoint': 'https://192.168.1.20', 'username': 'fixture', 'password': 'SYNTHETIC_SECRET'}})
        self.body = {'action': 'save', 'name': 'Installer', 'credentialKey': self.req['key'],
                     'endpoint': 'https://192.168.1.20', 'httpTransport': 'direct',
                     'projectId': PROJECT, 'expiresAt': time.time()+3600, 'enabled': True}
        self.key = self.manager.change('alice', self.body)['id']
        self.token = self.manager.issue('alice', TASK, PROJECT,
            {'profile': 'network-operations', 'networkMode': 'lan', 'executionMode': 'task', 'role': 'user'})
        self.ledger = Approvals(self.root)
        self.data = {
            '/redfish/v1/Systems': {'Members': [{'@odata.id': SYSTEM}]},
            SYSTEM: {'@odata.etag': '"s1"', 'PowerState': 'On',
                'Links': {'ManagedBy': [{'@odata.id': '/redfish/v1/Managers/1'}]},
                'Boot': {'BootSourceOverrideTarget@Redfish.AllowableValues': ['Cd', 'Hdd'],
                         'BootSourceOverrideEnabled': 'Disabled', 'BootSourceOverrideMode': 'UEFI'},
                'Actions': {'#ComputerSystem.Reset': {'target': SYSTEM+'/Actions/ComputerSystem.Reset',
                            'ResetType@Redfish.AllowableValues': ['On', 'GracefulRestart']}}},
            '/redfish/v1/Managers/1': {'VirtualMedia': {'@odata.id': MEDIA.rsplit('/', 1)[0]}},
            MEDIA.rsplit('/', 1)[0]: {'Members': [{'@odata.id': MEDIA}]},
            MEDIA: {'@odata.etag': '"m1"', 'MediaTypes': ['CD'], 'Inserted': False, 'Image': None,
                    'Actions': {'#VirtualMedia.'+action: {'target': MEDIA+'/Actions/VirtualMedia.'+action}
                                for action in ('InsertMedia', 'EjectMedia')}}}
        self.writes = []; self.reads = []

    def save_meta(self):
        (self.agent/'webui-metadata.json').write_text(json.dumps(self.meta))

    def get(self, origin, path, headers):
        self.assertEqual(origin, 'https://192.168.1.20'); self.reads.append(path)
        return copy.deepcopy(self.data[path])

    def send(self, origin, method, path, headers, body, **kw):
        self.writes.append((method, path, copy.deepcopy(body)))
        self.assertIn('If-Match', headers)
        if path.endswith('InsertMedia'):
            self.data[MEDIA].update(body, **{'@odata.etag': '"m2"'})
        elif path.endswith('EjectMedia'):
            self.data[MEDIA].update(Inserted=False, Image=None, **{'@odata.etag': '"m3"'})
        elif method == 'PATCH':
            self.data[SYSTEM]['Boot'].update(body['Boot']); self.data[SYSTEM]['@odata.etag'] = '"s2"'
        return True

    def args(self, n='1'):
        return dict(requestId=n*32, systemId='1', mediaResource=MEDIA, imageUrl=ISO)

    def call(self, op='redfish.media.insert', args=None, owner='alice', sender=None):
        return self.manager.dispatch({'token': self.token, 'action': 'call', 'connection': self.key,
            'operation': op, 'arguments': args if args is not None else self.args()}, owner,
            transport=self.get, write_transport=sender or self.send)

    def approve(self, op='redfish.media.insert', args=None):
        pending = self.call(op, args)
        self.assertTrue(pending['approvalRequired'])
        self.ledger.decide('alice', pending['approvalId'], True, self.manager)
        return pending

    def mount(self):
        self.approve(); return self.call()

    def boot_args(self):
        return dict(requestId='2'*32, systemId='1', mediaRequestId='1'*32, mode='UEFI')

    def boot(self):
        self.mount(); self.approve('redfish.boot.once', self.boot_args())
        return self.call('redfish.boot.once', self.boot_args())

    def test_full_sequence_requires_three_independent_approvals_and_no_replay(self):
        self.approve(); self.assertEqual(self.writes, [])
        self.assertEqual(self.call()['actionReceipt']['state'], 'acknowledged')
        self.approve('redfish.boot.once', self.boot_args()); self.assertEqual(len(self.writes), 1)
        self.call('redfish.boot.once', self.boot_args())
        args = dict(requestId='3'*32, systemId='1', bootRequestId='2'*32, resetType='GracefulRestart')
        self.approve('redfish.boot.restart', args); self.assertEqual(len(self.writes), 2)
        result = self.call('redfish.boot.restart', args)
        self.assertFalse(result['actionReceipt']['effectVerified']); self.assertEqual(len(self.writes), 3)
        self.manager = connections.Connections(self.root, self.home)
        self.reads.clear()
        self.assertEqual(self.call('redfish.boot.restart', args), result)
        self.assertEqual(len(self.writes), 3); self.assertEqual(self.reads, [])
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(self.manager.view('alice')))

    def test_lost_reply_is_durable_unknown_and_cannot_authorize_boot(self):
        self.approve()
        def lost(*args, **kw):
            self.send(*args, **kw); raise TimeoutError('SYNTHETIC_SECRET')
        result = self.call(sender=lost)
        self.assertEqual(result['actionReceipt']['state'], 'unknown')
        self.assertEqual(self.call(), result); self.assertEqual(len(self.writes), 1)
        with self.assertRaises(PermissionError): self.call('redfish.boot.once', self.boot_args())

    def test_etag_change_invalidates_pending_approval(self):
        self.approve(); self.data[MEDIA]['@odata.etag'] = '"changed"'
        with self.assertRaises(PermissionError): self.call()
        self.assertEqual(self.writes, [])

    def test_occupied_media_no_implicit_replace(self):
        self.data[MEDIA]['Inserted'] = True
        with self.assertRaises(install.InstallationPrecondition): self.call()
        self.assertEqual(self.ledger.pending('alice'), [])

    def test_unadvertised_or_foreign_action_rejected(self):
        for action in ({}, {'#VirtualMedia.InsertMedia': {'target': 'https://192.168.1.99/change'}}, []):
            self.data[MEDIA]['Actions'] = action
            with self.assertRaises(install.InstallationPrecondition): self.call()
        self.assertEqual(self.writes, [])

    def test_missing_etag_and_foreign_media_fail_before_approval(self):
        del self.data[MEDIA]['@odata.etag']
        with self.assertRaises(install.InstallationPrecondition): self.call()
        self.data[SYSTEM]['Links']['ManagedBy'] = []
        with self.assertRaises(install.InstallationPrecondition): self.call()
        self.assertEqual(self.ledger.pending('alice'), [])

    def test_invalid_urls_and_force_reset_and_extra_fields(self):
        for url in ('http://127.0.0.1/a.iso', 'http://example.com/a.iso', 'http://192.168.1.20/a.iso',
                    'http://user:pass@192.168.1.9/a.iso', ISO+'?key=secret', ISO+'#x',
                    'http://192.168.1.9/../a.iso', 'http://192.168.1.9/a%2eb.iso'):
            with self.subTest(url=url), self.assertRaises(ValueError): self.call(args=dict(self.args(), imageUrl=url))
        with self.assertRaises(ValueError): self.call(args=dict(self.args(), method='DELETE'))
        with self.assertRaises(ValueError):
            self.call('redfish.boot.restart', dict(requestId='3'*32, systemId='1', bootRequestId='2'*32, resetType='ForceRestart'))
        self.assertEqual(self.writes, [])

    def test_readback_mismatch_and_malformed_allowlist_block_boot(self):
        self.mount()
        self.data[SYSTEM]['Boot']['BootSourceOverrideTarget@Redfish.AllowableValues'] = 'Cd'
        with self.assertRaises(install.InstallationPrecondition): self.call('redfish.boot.once', self.boot_args())
        self.data[SYSTEM]['Boot']['BootSourceOverrideTarget@Redfish.AllowableValues'] = ['Cd']
        for field, value in (('Image', ISO+'wrong'), ('WriteProtected', False), ('Inserted', False)):
            original = self.data[MEDIA][field]; self.data[MEDIA][field] = value
            with self.assertRaises(install.InstallationPrecondition): self.call('redfish.boot.once', self.boot_args())
            self.data[MEDIA][field] = original
        self.assertEqual(len(self.writes), 1)

    def test_restart_requires_readback_and_correct_power_state(self):
        self.boot()
        args = dict(requestId='3'*32, systemId='1', bootRequestId='2'*32, resetType='On')
        with self.assertRaises(install.InstallationPrecondition): self.call('redfish.boot.restart', args)
        self.data[SYSTEM]['PowerState'] = 'Off'
        self.approve('redfish.boot.restart', args)
        self.data[SYSTEM]['Boot']['BootSourceOverrideEnabled'] = 'Disabled'
        with self.assertRaises(install.InstallationPrecondition): self.call('redfish.boot.restart', args)
        self.assertEqual(len(self.writes), 2)

    def test_explicit_eject_and_no_repeat(self):
        self.mount()
        args = dict(requestId='4'*32, systemId='1', mediaResource=MEDIA)
        self.approve('redfish.media.eject', args); self.assertEqual(len(self.writes), 1)
        self.call('redfish.media.eject', args); self.call('redfish.media.eject', args)
        self.assertEqual(len(self.writes), 2); self.assertFalse(self.data[MEDIA]['Inserted'])

    def test_owner_runtime_transport_and_credential_revocation_gates(self):
        with self.assertRaises(PermissionError): self.call(owner='bob')
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_BMC_WRITES_ENABLED': '0'}):
            with self.assertRaises(PermissionError): self.call()
        with self.assertRaises(ValueError): self.manager.change('alice', dict(self.body, httpTransport='openshell'))
        pending = self.approve()
        with self.assertRaises(ValueError): self.ledger.decide('bob', pending['approvalId'], True, self.manager)
        self.manager.vault.change('alice', [self.req], {'action': 'save', 'key': self.req['key'], 'values': {'password': 'ROTATED'}})
        with self.assertRaises(PermissionError): self.call()
        self.assertEqual(self.writes, [])

    def test_task_stop_project_change_and_disabled_account(self):
        for changes in ({'status': 'completed'}, {'projectId': None}, {'owner': 'bob'}):
            original = dict(self.meta['tasks'][TASK]); self.meta['tasks'][TASK].update(changes); self.save_meta()
            with self.assertRaises(PermissionError): self.call()
            self.meta['tasks'][TASK] = original; self.save_meta()
        credentials._write(self.root/'web-auth.json', json.dumps({'users': {'alice': {'enabled': False}}}).encode())
        with self.assertRaises(PermissionError): self.call()

    def test_unknown_receipt_and_changed_nonce_arguments(self):
        self.approve(); self.call(sender=lambda *a, **k: False)
        result = self.call('redfish.receipt', {'requestId': '1'*32})
        self.assertEqual(result['actionReceipt']['state'], 'unknown')
        with self.assertRaises(PermissionError): self.call(args=dict(self.args(), imageUrl=ISO.replace('installer', 'other')))

    def test_target_lock_blocks_parallel_change(self):
        with install.target_lock(self.root, 'https://192.168.1.20'):
            with self.assertRaises(BlockingIOError): self.call()
        self.assertEqual(self.ledger.pending('alice'), [])

    def test_readonly_adapter_never_has_write_operations(self):
        self.assertNotIn('redfish.media.insert', connections.ADAPTERS['redfish-readonly'])
        self.assertFalse(connections.permitted({'adapter': 'redfish-install', 'httpTransport': 'direct'},
            {'profile': 'development', 'networkMode': 'full'}))

    def test_transport_no_redirect_async_claim_or_certificate_bypass(self):
        for status in (200, 204, 202, 302, 400, 500):
            with mock.patch.object(install.http.client, 'HTTPSConnection') as cls:
                client = cls.return_value; client.getresponse.return_value.status = status
                result = install.write_json('https://192.168.1.20', 'POST', MEDIA+'/Actions/VirtualMedia.InsertMedia',
                    {'Authorization': 'synthetic', 'If-Match': '"m1"'}, {'Image': ISO})
                self.assertEqual(result, status in (200, 204)); client.request.assert_called_once()
                self.assertTrue(cls.call_args.kwargs['context'].check_hostname)
                self.assertEqual(cls.call_args.kwargs['timeout'], 10); client.close.assert_called_once()
        with mock.patch.object(install.http.client, 'HTTPSConnection') as cls:
            install.write_json('https://192.168.1.20', 'POST', '/x', {}, {}, ignore_certificate_errors=True)
            self.assertFalse(cls.call_args.kwargs['context'].check_hostname)


if __name__ == '__main__':
    unittest.main()
