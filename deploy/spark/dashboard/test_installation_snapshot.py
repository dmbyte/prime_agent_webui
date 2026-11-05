import copy
import json
import unittest
from unittest import mock

import connections
import connection_native


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.row = {'adapter': 'redfish-readonly', 'endpoint': 'https://192.168.1.9'}
        self.values = {'endpoint': self.row['endpoint'], 'username': 'fixture', 'password': 'fixture-secret'}
        self.system = '/redfish/v1/Systems/System.1'
        self.manager = '/redfish/v1/Managers/iDRAC.1'
        self.collection = self.manager+'/VirtualMedia'
        self.media = self.collection+'/CD'
        self.data = {
            '/redfish/v1/Systems': {'Members': [{'@odata.id': self.system}]},
            self.system: {'PowerState': 'On', 'Boot': {'BootSourceOverrideEnabled': 'Once',
                'BootSourceOverrideTarget': 'Cd', 'BootSourceOverrideMode': 'UEFI'},
                'Links': {'ManagedBy': [{'@odata.id': self.manager}]}},
            self.manager: {'VirtualMedia': {'@odata.id': self.collection}},
            self.collection: {'Members': [{'@odata.id': self.media}]},
            self.media: {'Inserted': True, 'WriteProtected': True, 'ConnectedVia': 'URI', 'MediaTypes': ['CD'],
                'Image': 'http://user:fixture-secret@host/private.iso', 'SerialNumber': 'private-serial', 'Oem': {}}}
        self.transport = mock.Mock(side_effect=lambda origin, path, headers: copy.deepcopy(self.data[path]))

    def call(self, arguments=None):
        return connections.perform(self.row, self.values, 'redfish.installation',
                                   {'systemId': 'System.1'} if arguments is None else arguments, self.transport)

    def test_discover_requires_selection_and_projects_only_safe_fields(self):
        self.assertEqual(self.call({}), {'systemIds': ['System.1']})
        self.transport.reset_mock()
        result = self.call()
        self.assertEqual(result['boot'], {'enabled': 'Once', 'target': 'Cd', 'mode': 'UEFI'})
        self.assertTrue(result['media'][0]['inserted'])
        self.assertTrue(result['media'][0]['imageConfigured'])
        self.assertIs(result['effectVerified'], False)
        self.assertEqual(result['mediaStatus'], 'observed')
        self.assertEqual(self.transport.call_count, 5)
        for forbidden in ('fixture-secret', 'private-serial', 'private.iso', 'Oem'):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_system_media_preferred_no_arbitrary_manager_reads(self):
        collection = self.system+'/VirtualMedia'
        self.data[self.system]['VirtualMedia'] = {'@odata.id': collection}
        self.data[collection] = {'Members': []}
        self.assertEqual(self.call()['media'], [])
        self.assertEqual(self.transport.call_count, 3)

    def test_missing_and_unknown_are_not_false_success(self):
        self.data[self.system] = {'Boot': {'BootSourceOverrideTarget': 'OEM-private'}}
        result = self.call()
        self.assertEqual(result['mediaStatus'], 'not-advertised')
        self.assertEqual(result['boot']['target'], 'Unknown')
        self.assertEqual(result['powerState'], 'Unknown')

    def test_invalid_inputs_and_unobserved_system_rejected(self):
        for value in ({'systemId': '../Managers'}, {'systemId': 'other'}, {'systemId': '..'},
                      {'systemId': 'System.1', 'reset': True}, {'systemId': 1}, {'url': 'http://evil'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.call(value)

    def test_no_foreign_links_pagination_traversal_duplicate_or_incomplete(self):
        for path in ('https://evil/1', '//evil/1', '/redfish/v1/Managers/../x',
                     '/redfish/v1/Managers/a%2fb', '/redfish/v1/Managers/..'):
            self.data[self.system]['Links']['ManagedBy'] = [{'@odata.id': path}]
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.call()
        for data in ({'Members': [], 'Members@odata.nextLink': '/next'},
                     {'Members': [], 'Members@odata.count': 2},
                     {'Members': [{'@odata.id': self.system}]*2}, {'Members': [None]}):
            with self.assertRaises(ValueError):
                connections.redfish_members(data, '/redfish/v1/Systems')

    def test_media_link_never_followed_outside_selected_source(self):
        for path in ('https://evil', '/redfish/v1/Managers/other/VirtualMedia', None, 17):
            self.data[self.manager]['VirtualMedia']['@odata.id'] = path
            self.transport.reset_mock()
            with self.assertRaises(ValueError): self.call()
            self.assertEqual(self.transport.call_count, 3)

    def test_native_profile_remains_get_only_and_target_bound(self):
        origin, paths, _, _ = connection_native.http_binding(self.row, self.values)
        profile = connection_native.profile('fixture', origin, paths)
        rules = profile['endpoints'][0]['rules']
        self.assertEqual({r['allow']['method'] for r in rules}, {'GET'})
        self.assertEqual(profile['endpoints'][0]['allowed_ips'], ['192.168.1.9/32'])

    def test_only_exact_same_origin_trailing_slash_redirect(self):
        response = mock.Mock(status=308)
        response.getheader.side_effect = lambda key, default=None: self.media+'/' if key == 'Location' else default
        final = mock.Mock(status=200)
        final.getheader.side_effect = lambda key, default=None: 'application/json' if key == 'Content-Type' else default
        final.read1.side_effect = [b'{}', b'']
        with mock.patch.object(connections.http.client, 'HTTPSConnection') as cls:
            cls.return_value.getresponse.side_effect = [response, final]
            self.assertEqual(connections.get_json(self.row['endpoint'], self.media, {}), {})
            self.assertEqual(cls.return_value.request.call_args.args, ('GET', self.media+'/'))


if __name__ == '__main__':
    unittest.main()
