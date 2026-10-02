import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'container'))
import console_feed as feed


class ConsoleFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'feeds'

    def test_snapshot_is_opt_in_bounded_and_not_a_recording(self):
        source = feed.ConsoleFeed('kvm', 'BMC', root=self.root)
        source.update(image=b'\xff\xd8test')
        self.assertNotIn('image', feed.snapshots(self.root, source.id)[0])
        feed.watch(self.root)
        source.update(image=b'\xff\xd8test')
        self.assertIn('image', feed.snapshots(self.root, source.id)[0])
        self.assertNotIn('image', feed.snapshots(self.root)[0])
        source.update(image=b'\xff\xd8second')
        self.assertEqual(len(list(self.root.glob('*.json'))), 1)
        source.close()
        self.assertEqual(feed.snapshots(self.root, source.id)[0]['state'], 'closed')
        self.assertNotIn('image', feed.snapshots(self.root, source.id)[0])

    def test_serial_is_plain_text_and_stale_is_visible(self):
        source = feed.ConsoleFeed('serial', 'SOL', root=self.root)
        feed.watch(self.root)
        source.update(text='<script>not HTML</script>')
        self.assertEqual(feed.snapshots(self.root, source.id)[0]['text'], '<script>not HTML</script>')
        with mock.patch.object(feed.time, 'time', return_value=source.row['updatedAt'] + 20):
            self.assertTrue(feed.snapshots(self.root)[0]['stale'])
            self.assertFalse(source.watched())

    def test_heartbeat_uses_shared_write_access_without_chmod(self):
        feed.ConsoleFeed('browser', 'Shared console', root=self.root)
        with mock.patch.object(feed.os, 'fchmod', side_effect=PermissionError('different file owner')):
            feed.watch(self.root)
            feed.watch(self.root)
        self.assertTrue((self.root / '.watch').is_file())

    def test_symlink_frames_and_paths_are_not_followed(self):
        self.root.mkdir()
        secret = Path(self.tmp.name) / 'private'
        secret.write_text('private')
        (self.root / ('a'*32 + '.json')).symlink_to(secret)
        self.assertEqual(feed.snapshots(self.root), [])
        (self.root / '.watch').symlink_to(secret)
        with self.assertRaises(OSError): feed.watch(self.root)
        self.assertEqual(secret.read_text(), 'private')
        with self.assertRaises(ValueError): feed.snapshots(self.root, '../private')
        linked = Path(self.tmp.name) / 'linked'
        linked.symlink_to(self.root)
        with self.assertRaises(OSError): feed.snapshots(linked)

    def test_owner_isolation_and_no_traversal(self):
        spec = importlib.util.spec_from_file_location('viewer_api_test', Path(__file__).with_name('api_v2.py'))
        api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
        parent = Path(self.tmp.name)
        (parent/'alice').mkdir(); (parent/'bob').mkdir()
        source = feed.ConsoleFeed('browser', 'Alice browser', root=parent/'alice'/'.prime-console')
        with mock.patch.dict(os.environ, {'PRIME_RUNNER_WORKSPACE_ROOT':str(parent)}):
            self.assertEqual(api.console_snapshots('bob', selected=source.id), [])
            self.assertEqual(api.console_snapshots('alice')[0]['id'], source.id)
            for owner in ('..','../alice','/alice'):
                with self.assertRaises(ValueError): api.console_snapshots(owner)

    def test_oversized_and_malformed_data_not_served(self):
        source = feed.ConsoleFeed('browser', 'BMC', root=self.root)
        path = self.root / (source.id + '.json')
        path.write_text('x'*(feed.MAX_BYTES+1))
        self.assertEqual(feed.snapshots(self.root), [])
        path.write_text(json.dumps(dict(source.row, image='not-base64', updatedAt=feed.time.time())))
        self.assertEqual(feed.snapshots(self.root, source.id), [])

    def test_missing_workspace_does_not_break_standalone_tools(self):
        source = feed.ConsoleFeed('browser', 'Standalone', root=self.root/'missing'/'feeds')
        source.update(text='test')
        source.close()
        self.assertFalse(source.watched())

    def test_viewer_has_no_input_and_clears_on_auth_failure(self):
        script = Path(__file__).with_name('console-viewer.js').read_text()
        self.assertIn('textContent=row.text', script)
        self.assertIn('clearScreen(error.message)', script)
        self.assertIn('document.hidden', script)
        self.assertNotIn('method:"POST"', script)
        self.assertNotIn('innerHTML', script)


if __name__ == '__main__': unittest.main()
