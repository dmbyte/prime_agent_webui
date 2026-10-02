import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'container'))
import hosting_auth
import hosting_broker as broker
import hosting_server as static
import task_common


class StaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'disk.iso').write_bytes(bytes(range(256)) * 8)
        (self.root / 'index.html').write_text('public index')
        (self.root / '.env').write_text('private')
        (self.root / 'linked.iso').symlink_to(self.root / 'disk.iso')
        self.server = static.StaticServer(('127.0.0.1', 0), static.StaticHandler)
        self.server.root = str(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method='GET', path='/disk.iso', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_get_head_and_empty_file(self):
        code, headers, body = self.request()
        self.assertEqual((code, len(body), headers['Accept-Ranges']), (200, 2048, 'bytes'))
        self.assertEqual(self.request('HEAD')[2], b'')
        self.assertEqual(self.request('HEAD')[1]['Content-Length'], '2048')
        (self.root / 'empty').touch()
        self.assertEqual(self.request(path='/empty')[2], b'')

    def test_range_suffix_open_ended_unsatisfiable_and_if_range(self):
        for header, size, expected in [('bytes=12-31', 20, 'bytes 12-31/2048'),
                                        ('bytes=-12', 12, 'bytes 2036-2047/2048'),
                                        ('bytes=2040-', 8, 'bytes 2040-2047/2048')]:
            code, headers, body = self.request(headers={'Range': header})
            self.assertEqual((code, len(body), headers['Content-Range']), (206, size, expected))
        for value in ('bytes=2048-', 'bytes=3-1', 'bytes=-0', 'bytes=1-2,5-7', 'invalid'):
            code, headers, body = self.request(headers={'Range': value})
            self.assertEqual((code, headers['Content-Range'], body), (416, 'bytes */2048', b''))
        self.assertEqual(self.request(headers={'Range': 'bytes=1-2', 'If-Range': 'stale'})[0], 200)

    def test_paths_and_writes_denied(self):
        for path in ('/.env', '/%2e%2e/disk.iso', '/linked.iso', '/sub/../disk.iso', '/sub%5cfile', '/%00'):
            self.assertEqual(self.request(path=path)[0], 404, path)
        self.assertEqual(self.request('POST')[0], 501)

    def test_sparse_large_iso_range_does_not_read_whole_file(self):
        with (self.root / 'large.iso').open('wb') as stream:
            stream.seek(5 * 1024 ** 3)
            stream.write(b'END')
        self.assertEqual(self.request(path='/large.iso', headers={'Range': 'bytes=-3'})[2], b'END')


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'tasks' / 'alice'
        (self.workspace / 'hosted' / 'media').mkdir(parents=True)
        self.broker = broker.HostingBroker('alice', self.root, self.root / 'tasks', '127.0.0.1')
        self.project = 'p_' + '1' * 24
        self.token = hosting_auth.issue('alice', 'a' * 32, self.project, {'networkMode': 'lan'}, self.root)
        self.claim = hosting_auth.verify(self.token, 'alice', self.root)

    def call(self, action, **kwargs):
        return self.broker.dispatch(dict(token=self.token, action=action, **kwargs))

    def create(self, **kwargs):
        with patch.object(self.broker, '_start', side_effect=lambda row: row.update(status='running')):
            return self.call('create', name='media', directory='/project/hosted/media', **kwargs)

    def test_capability_owner_tamper_restricted_and_revocation(self):
        self.assertIsNone(hosting_auth.issue('alice', 'b' * 32, None, {'networkMode': 'internet'}, self.root))
        self.assertIsNone(hosting_auth.issue('alice', 'b' * 32, None, {'networkMode': 'full', 'executionMode': 'deny'}, self.root))
        for token, owner in ((self.token[:-1] + ('1' if self.token[-1] != '1' else '2'), 'alice'), (self.token, 'bob')):
            with self.assertRaises(PermissionError):
                hosting_auth.verify(token, owner, self.root)
        hosting_auth.revoke('a' * 32, self.root)
        with self.assertRaises(PermissionError):
            self.call('list')

    def test_project_discovery_foreign_project_and_task_scopes(self):
        row = self.create()
        self.assertEqual(row['scope'], 'project')
        self.assertTrue(broker.visible(row, dict(taskId='b'*32, projectId=self.project)))
        self.assertFalse(broker.visible(row, dict(taskId='b'*32, projectId='p_'+'2'*24)))
        foreign = hosting_auth.issue('alice', 'b'*32, 'p_'+'2'*24, {'networkMode':'lan'}, self.root)
        self.assertEqual(self.broker.dispatch(dict(action='list', token=foreign))['services'], [])
        with self.assertRaises(LookupError):
            self.broker.dispatch(dict(action='stop', id=row['id'], token=foreign))
        row['scope'] = 'task'
        self.assertFalse(broker.visible(row, dict(taskId='b'*32, projectId=self.project)))

    def test_source_scope_and_command_validation(self):
        (self.workspace / 'hosted' / 'link').symlink_to(self.workspace / 'hosted' / 'media')
        for source in ('/project', '/etc', '/project/hosted/../private', '/project/hosted/link', '/project/hosted/media/'):
            with self.assertRaises(ValueError):
                broker.source_directory(self.workspace, source)
        for kwargs in ({'ttlHours': 0}, {'scope': 'global'}, {'kind': 'app', 'command': 'node app.js'}, {'ttlHours': float('nan')}):
            with self.assertRaises(ValueError):
                self.create(**kwargs)

    def test_expiry_renew_stop_and_persistence(self):
        row = self.create()
        service_id = row['id']
        result = self.call('renew', id=service_id, ttlHours=48)
        self.assertGreater(result['expiresInSeconds'], 47*3600)
        other = broker.HostingBroker('alice', self.root, self.root/'tasks', '127.0.0.1')
        self.assertEqual(other.rows[service_id]['url'], row['url'])
        self.broker.rows[service_id]['expiresAt'] = time.time() - 1
        with patch.object(self.broker, '_stop') as stop:
            self.broker.maintain()
            stop.assert_called_once()
        self.assertEqual(self.call('list')['services'], [])
        self.assertTrue((self.workspace/'hosted/media').exists())

    def test_spec_minimum_mounts_and_loopback_forward(self):
        (self.root/'openshell-image-digests.json').write_text(json.dumps({'development': {'image': 'local/prime-openshell-development:0.9.5-'+'a'*12}}))
        row = self.create()
        spec = broker.sandbox_spec('alice', self.broker.rows[row['id']], self.root)
        mounts = json.loads(spec['create'][spec['create'].index('--driver-config-json')+1])['docker']['mounts']
        self.assertEqual(mounts, [{'type':'volume', 'source':'prime-alice-workspace', 'target':'/site', 'subpath':'hosted/media', 'read_only':True}])
        self.assertIn('network_policies: {}', spec['policy'].read_text())
        self.assertIn('PRIME_HOST_URL='+row['url'], spec['launch'])
        self.assertNotIn('/run/prime-gateway', spec['policy'].read_text())
        self.assertEqual(spec['forward'][-1], '127.0.0.1:'+str(row['port']))

    def test_stop_failure_retains_registry_for_retry(self):
        row = self.create()
        with patch.object(self.broker, '_stop', side_effect=RuntimeError('cleanup failed')):
            with self.assertRaises(RuntimeError):
                self.call('stop', id=row['id'])
        self.assertEqual(self.call('list')['services'][0]['id'], row['id'])

    def test_expired_capability_denied(self):
        with patch.object(hosting_auth.time, 'time', return_value=time.time()+5*3600):
            with self.assertRaises(PermissionError):
                self.call('list')

    def test_process_exit_marks_failed_and_closes_forwarder(self):
        from unittest.mock import Mock
        row = self.create()
        self.broker.processes[row['id']] = [Mock(poll=lambda: 1)]
        with patch.object(self.broker, '_stop') as stop:
            self.broker.maintain()
            stop.assert_called_once()
        self.assertEqual(self.call('list')['services'][0]['status'], 'failed')

    def test_restart_preserves_url_and_only_recovers_unexpired_rows(self):
        row = self.create()
        other = broker.HostingBroker('alice', self.root, self.root/'tasks', '127.0.0.1')
        with patch.object(other, '_stop'), patch.object(other, '_start') as start:
            other.recover()
            start.assert_called_once()
            self.assertEqual(start.call_args.args[0]['url'], row['url'])
        other.rows[row['id']]['expiresAt'] = time.time()-1
        with patch.object(other, '_stop'), patch.object(other, '_start') as start:
            other.recover()
            start.assert_not_called()
        self.assertEqual(other.rows, {})

    def test_address_selection_rejects_container_and_public_addresses(self):
        interfaces = [dict(ifname='enp1', operstate='UP', addr_info=[dict(local='192.168.1.2', scope='global')]),
                      dict(ifname='docker0', operstate='UP', addr_info=[dict(local='172.17.0.1', scope='global')])]
        with patch.object(broker.subprocess, 'check_output', side_effect=[json.dumps(interfaces), json.dumps([{'prefsrc':'192.168.1.2'}])]):
            self.assertEqual(broker.lan_address(), '192.168.1.2')
        for address in ('127.0.0.1', '172.17.0.1', '8.8.8.8', '0.0.0.0'):
            with patch.object(broker.subprocess, 'check_output', return_value=json.dumps(interfaces)):
                with self.assertRaises(ValueError):
                    broker.lan_address(address)


if __name__ == '__main__':
    unittest.main()
