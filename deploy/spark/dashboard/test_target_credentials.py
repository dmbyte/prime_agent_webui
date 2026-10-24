"""Synthetic one-to-many credential references; no real accounts or endpoints."""
import json
import os
import time
from unittest import mock

from test_connections import ConnectionTests, PROJECT, TASK, POLICY
import skill_credentials


class TargetCredentialTests(ConnectionTests):
    def setUp(self):
        super().setUp()
        self.fields = [{'id': name, 'label': name} for name in ('endpoint', 'username', 'password')]
        for adapter in ('redfish-readonly', 'bmc-browser', 'bmc-kvm'):
            self.meta['skills']['s_'+adapter] = dict(owner='alice', status='installed', enabled=True,
                credentialRequirements=[dict(id='bmc', label=adapter, adapter=adapter, fields=self.fields)])
        self.save_meta()
        self.requirements = self.manager.requirements('alice')
        self.target_values = dict(endpoint='https://192.168.1.20', username='fixture', password='SYNTHETIC_TARGET_SECRET')
        self.target = self.manager.vault.change('alice', self.requirements,
            dict(action='save-target', name='Test target', values=self.target_values))['key']

    def bind(self, adapter, **changes):
        req = next(r for r in self.requirements if r.get('adapter') == adapter)
        return self.manager.change('alice', dict(self.body, credentialKey=self.target,
            requirementKey=req['key'], **changes))['id']

    def test_one_saved_target_many_reviewed_adapters_and_rotation(self):
        with mock.patch.dict(os.environ, {'PRIME_CONNECTION_CONSOLES_ENABLED': '1'}):
            keys = [self.bind(a) for a in ('redfish-readonly', 'bmc-browser', 'bmc-kvm')]
            stored = self.manager.store._load('alice')
            self.assertEqual({stored[k]['credentialKey'] for k in keys}, {self.target})
            self.assertEqual(len(self.manager.vault._load('alice')), 2)  # one GitHub + one target
            self.manager.revoke(TASK)
            token = self.manager.issue('alice', TASK, PROJECT, POLICY)
            rows = self.manager.dispatch(dict(action='list', token=token), 'alice')['connections']
            self.assertTrue(set(keys) <= {r['id'] for r in rows})
            self.manager.vault.change('alice', [], dict(action='save-target', key=self.target, name='Renamed', values={}, ignoreCertificateErrors=True))
            self.assertFalse(any(self.manager.eligible('alice', r, PROJECT) for k, r in stored.items() if k in keys))
            remaining = self.manager.dispatch(dict(action='list', token=token), 'alice')['connections']
            self.assertFalse(set(keys) & {r['id'] for r in remaining})
            self.assertIs(self.manager.vault._load('alice')[self.target]['ignoreCertificateErrors'], True)

    def test_cross_owner_wrong_adapter_wrong_endpoint_and_scope_denied(self):
        req = next(r for r in self.requirements if r.get('adapter') == 'bmc-browser')
        with self.assertRaises(ValueError): self.bind('github-readonly')
        with self.assertRaises(ValueError): self.bind('bmc-browser', endpoint='https://192.168.1.21')
        self.meta['skills']['s_bmc-browser'].update(scope='project', projectId=PROJECT)
        self.meta['projects'][PROJECT]['skillIds'] = ['s_bmc-browser']; self.save_meta()
        with self.assertRaises(ValueError): self.bind('bmc-browser', projectId=None)
        with self.assertRaises(ValueError):
            self.manager.change('bob', dict(self.body, projectId=None, credentialKey=self.target, requirementKey=req['key']))
        self.assertEqual(self.manager.view('bob')['credentials'], [])
        self.assertEqual(self.manager.vault.view('bob', []), [])

    def test_disable_skill_delete_target_revoke_and_metadata_no_secret(self):
        key = self.bind('bmc-browser'); row = self.manager.store._load('alice')[key]
        self.assertTrue(self.manager.eligible('alice', row, PROJECT))
        self.meta['skills']['s_bmc-browser']['enabled'] = False; self.save_meta()
        self.assertFalse(self.manager.eligible('alice', row, PROJECT))
        self.meta['skills']['s_bmc-browser']['enabled'] = True; self.save_meta()
        public = json.dumps([self.manager.view('alice'), self.manager.vault.view('alice', self.requirements)])
        self.assertNotIn(self.target_values['password'], public)
        self.assertNotIn('"username": "fixture"', public)
        self.manager.vault.change('alice', [], dict(action='delete', key=self.target))
        self.assertFalse(self.manager.eligible('alice', row, PROJECT))

    def test_explicit_import_preserves_source_and_grants_nothing(self):
        req = next(r for r in self.requirements if r.get('adapter') == 'redfish-readonly')
        self.manager.vault.change('alice', self.requirements, dict(action='save', key=req['key'], values=self.target_values))
        before = self.manager.vault._load('alice')[req['key']]
        refs = self.manager.store._load('alice')
        key = self.manager.vault.change('alice', self.requirements, dict(action='save-target', name='Imported', sourceKey=req['key']))['key']
        records = self.manager.vault._load('alice')
        self.assertEqual(records[req['key']], before)
        self.assertEqual(records[key]['values'], before['values'])
        self.assertFalse(records[key]['ignoreCertificateErrors'])
        self.assertEqual(self.manager.store._load('alice'), refs)
        with self.assertRaises(ValueError):
            self.manager.vault.change('bob', [], dict(action='save-target', name='No', sourceKey=req['key']))
        with self.assertRaises(ValueError):
            self.manager.vault.change('alice', [dict(req, scope='project')], dict(action='save-target', name='No', sourceKey=req['key']))

    def test_target_validation_preserves_safe_default(self):
        for changes in ({'owner': 'bob'}, {'name': '\n'}, {'ignoreCertificateErrors': 'true'},
                        {'key': self.req['key']}, {'sourceKey': self.req['key']}, {'values': {'endpoint': 'http://192.168.1.20'}},
                        {'values': {'endpoint': 'https://example.com'}}, {'values': {'password': '\x00'}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.vault.change('alice', self.requirements,
                    dict(dict(action='save-target', name='Test', values=self.target_values), **changes))
        self.assertFalse(self.manager.vault._load('alice')[self.target]['ignoreCertificateErrors'])


# Do not collect imported base tests twice; inherited cases exercise backward compatibility.
del ConnectionTests
