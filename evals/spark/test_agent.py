import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import agent_probe


class AgentProbeTests(unittest.TestCase):
    def test_replayed_action_fails_even_after_a_claimed_success(self):
        self.assertTrue(agent_probe.valid_action_counts({'login': 1, 'key': 1}))
        for evidence in ({'login': 1, 'key': 2}, {'login': 1, 'key': 0},
                         {'login': 2, 'key': 1}, {'login': True, 'key': 1}):
            self.assertFalse(agent_probe.valid_action_counts(evidence))

    def test_image_read_rejects_symlinks_and_non_png(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'target'
            target.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            self.assertEqual(agent_probe.read_png(target), target.read_bytes())
            link = Path(directory)/'link'; link.symlink_to(target)
            with self.assertRaises(OSError): agent_probe.read_png(link)
            target.write_bytes(b'not an image')
            with self.assertRaises(ValueError): agent_probe.read_png(target)

    def test_frozen_combined_task(self):
        self.assertEqual(hashlib.sha256(agent_probe.TASK_PROMPT.encode()).hexdigest(),
                         '5892d193493b539f9e44847f49c74e3684a8b7154703076d08b4589dd42119fc')

    def test_proxy_rejects_unreviewed_port(self):
        with self.assertRaises(ValueError): agent_probe.proxy_handler(8765, [])

    def test_cleanup_requires_exact_label_not_nonce_in_other_field(self):
        nonce = 'a' * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'agent-runtime.json').write_text(json.dumps({'nonce': nonce, 'invocation': 'ours'}))
            result = SimpleNamespace(returncode=0, stdout=json.dumps({'name': 'pe-'+nonce[:16], 'description': nonce}), stderr='')
            with patch('agent_probe.subprocess.run', return_value=result) as run:
                with self.assertRaises(RuntimeError): agent_probe.cleanup(root, 'ours')
                self.assertEqual(run.call_count, 1)
                name = run.call_args.args[0][5]
                self.assertLessEqual(len(name), 19)

    def test_cleanup_keeps_marker_if_volume_inventory_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root/'agent-runtime.json'
            marker.write_text(json.dumps({'nonce': 'b'*32, 'invocation': 'ours'}))
            absent = SimpleNamespace(returncode=1, stdout='', stderr='Sandbox not found')
            unavailable = SimpleNamespace(returncode=1, stdout='', stderr='Cannot connect to Docker daemon')
            with patch('agent_probe.subprocess.run', side_effect=[absent, unavailable]):
                with self.assertRaises(RuntimeError): agent_probe.cleanup(root, 'ours')
            self.assertTrue(marker.exists())

    def test_foreign_cleanup_cannot_touch_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'agent-runtime.json').write_text(json.dumps({'nonce': 'a'*32, 'invocation': 'other'}))
            with patch('agent_probe.subprocess.run') as run:
                agent_probe.cleanup(root, 'ours')
                run.assert_not_called()
            self.assertTrue((root/'agent-runtime.json').exists())

    def test_invalid_identity_cannot_be_used_for_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'agent-runtime.json').write_text(json.dumps({'nonce': '../user', 'invocation': 'ours'}))
            with patch('agent_probe.subprocess.run') as run:
                with self.assertRaises(ValueError): agent_probe.cleanup(root, 'ours')
                run.assert_not_called()

    def test_sandbox_exec_is_nonlogin_and_scoped(self):
        with patch('agent_probe.command') as run:
            agent_probe.sandbox_exec('pe-fixture', ['id'])
            args = run.call_args.args[0]
            self.assertIn('--no-login-shell', args)
            self.assertEqual(args[args.index('--name')+1], 'pe-fixture')
            self.assertNotIn('sudo', args)


if __name__ == '__main__': unittest.main()
