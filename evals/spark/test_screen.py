import collections
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import io
import subprocess
import urllib.error
import urllib.request

from code_grader import grade, validate
from run_screen import equivalent, parse_json, chat, NoRedirect, grade_code
from prepare_trial import transform
import maintenance_guard
import candidate_trial
from stage_candidate import safe_path, digest_file
from suite import suite, suite_hash


class ScreeningTests(unittest.TestCase):
    def test_no_redirect_can_escape_loopback(self):
        request = urllib.request.Request('http://127.0.0.1:30001/v1/chat/completions')
        with self.assertRaises(urllib.error.HTTPError):
            NoRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://example.invalid/')

    def test_code_sandbox_explicitly_excludes_gpu_and_mounts(self):
        case = next(c for c in suite() if c.get('kind') == 'code')
        with patch('run_screen.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"passed":true,"reason":"fixture"}', '')) as run:
            self.assertTrue(grade_code(case, {'code': 'def dedupe(records): return records'}, 'sha256:' + 'a'*64)[0])
            command = run.call_args_list[0].args[0]
            for flag in ('--runtime=runc', 'NVIDIA_VISIBLE_DEVICES=void', '--network=none', '--read-only', '--cap-drop=ALL'):
                self.assertIn(flag, command)
            self.assertNotIn('-v', command)
            self.assertNotIn('--gpus', command)

    def test_stream_does_not_store_reasoning(self):
        events = [
            {'choices': [{'delta': {'reasoning_content': 'INTERNAL_NOT_PERSISTED'}}]},
            {'choices': [{'delta': {'content': '{"ok":'}}]},
            {'choices': [{'delta': {'content': 'true}'}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'completion_tokens': 10, 'prompt_tokens': 20}},
        ]
        stream = io.BytesIO(b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events) + b'data: [DONE]\n\n')
        with patch('run_screen.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = stream
            reply, metrics = chat('http://127.0.0.1:30001', 'fixture', [])
        self.assertEqual(reply['content'], '{"ok":true}')
        self.assertNotIn('INTERNAL_NOT_PERSISTED', json.dumps([reply, metrics]))
        self.assertEqual(metrics['usage']['completion_tokens'], 10)

    def test_launcher_fail_closed(self):
        with self.assertRaises(ValueError):
            transform('not the reviewed upstream launcher')

    def test_launcher_keeps_owned_cache_and_isolation(self):
        source = '\n'.join(['docker rm -f "$NAME" >/dev/null 2>&1 || true',
            'docker run -d --name "$NAME"', '--gpus all --ipc host --network host --shm-size=16g',
            '-e HF_HUB_DISABLE_TELEMETRY=1'])
        result = transform(source)
        self.assertIn('--user "$(id -u):$(id -g)"', result)
        self.assertIn('-e HOME=/cache/home', result)
        self.assertIn('--cap-drop=ALL', result)
        self.assertIn('127.0.0.1:$PORT:$PORT', result)
        self.assertNotIn('docker rm -f', result)
        self.assertNotIn('--ipc host', result)
        self.assertNotIn('--network host', result)

    def test_truncated_stream_rejected(self):
        event = {'choices': [{'delta': {'content': '{"ok":true}'}, 'finish_reason': 'stop'}]}
        with patch('run_screen.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'data: ' + json.dumps(event).encode() + b'\n')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                chat('http://127.0.0.1:30001', 'fixture', [])

    def test_active_task_blocks_before_sandbox_probe(self):
        with patch('maintenance_guard.Path.read_text', return_value='{"users":{"synthetic":{}}}'), patch('maintenance_guard.urllib.request.build_opener') as opener, patch('maintenance_guard.subprocess.run') as run:
            opener.return_value.open.return_value = io.BytesIO(b'{"ok":true,"activeTasks":1}')
            with self.assertRaisesRegex(RuntimeError, 'Active task'):
                maintenance_guard.idle()
            run.assert_not_called()

    def test_unrecognized_health_never_implies_idle(self):
        for payload in ({'ok': True}, {'ok': True, 'activeTasks': False}, {'ok': True, 'activeTasks': -1}):
            with patch('maintenance_guard.urllib.request.build_opener') as opener, patch('maintenance_guard.subprocess.run') as run:
                opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
                with self.assertRaises(RuntimeError): maintenance_guard.idle()
                run.assert_not_called()

    def test_recovery_identity_mismatch_does_not_stop_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'restore-production.json').write_text('{"production_id":"original"}')
            with patch('candidate_trial.inspect', return_value={'Id': 'different'}), patch('candidate_trial.docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                    candidate_trial.recover(root)
                docker.assert_not_called()

    def test_recovery_restores_original_and_marks_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'restore-production.json').write_text('{"production_id":"original"}')
            containers = [{'Id': 'original', 'State': {'Running': False}}, {'Id': 'candidate', 'Config': {'Labels': {'prime.model-eval': candidate_trial.LABEL}}}]
            with patch('candidate_trial.inspect', side_effect=containers), patch('candidate_trial.docker') as docker, patch('candidate_trial.healthy', return_value=True):
                candidate_trial.recover(root)
                self.assertEqual(docker.call_args_list[0].args, ('stop', '--time=30', 'candidate'))
                self.assertEqual(docker.call_args_list[1].args, ('start', 'original'))
            self.assertTrue((root / 'restored-production.json').exists())
            self.assertFalse((root / 'restore-production.json').exists())

    def test_frozen_suite(self):
        cases = suite()
        self.assertEqual(len({c['id'] for c in cases}), 100)
        self.assertEqual(collections.Counter(c['domain'] for c in cases), {'infrastructure': 30, 'coding': 25, 'cad': 15, 'social': 15, 'portfolio': 15})
        self.assertEqual(collections.Counter(c['split'] for c in cases), {'development': 80, 'holdout': 20})
        self.assertEqual(suite_hash(), 'b0a0d94c7eea7e6a2a790e499aa191665fcf8fe62d2fe088d0966f072f213555')
        self.assertFalse({c['family'] for c in cases if c['split'] == 'holdout'} & {c['family'] for c in cases if c['split'] == 'development'})

    def test_comparison(self):
        self.assertTrue(equivalent({'n': [10.4]}, {'n': [10.40000000001]}))
        self.assertFalse(equivalent(True, 1))
        self.assertFalse(equivalent(1, True))
        self.assertFalse(equivalent(float('nan'), 1))
        self.assertFalse(equivalent({'a': 1, 'b': 2}, {'a': 1}))

    def test_json(self):
        self.assertEqual(parse_json('```json\n{"a":1}\n```'), {'a': 1})
        for bad in ('NaN', 'Infinity', 'prefix {"a":1}', '{broken}'):
            with self.assertRaises(ValueError):
                parse_json(bad)

    def test_ast_rejections(self):
        for source in ('import os', 'print(1)', 'class X: pass', 'def f():\n return open("x")', 'def f():\n return (1).__class__', '@print\ndef f(): pass', 'def f(a=print(1)): pass'):
            with self.assertRaises(ValueError):
                validate(source, 'f')

    def test_grader_trusted_fixtures(self):
        # Only fixed source in unit tests; model-generated source runs in Docker.
        payload = {'code': 'def f(a):\n return max(0,a)', 'function': 'f', 'tests': [([-1], 0), ([2], 2)]}
        self.assertTrue(grade(payload)['passed'])
        payload['code'] = 'def f(a):\n return 0'
        self.assertFalse(grade(payload)['passed'])
        self.assertFalse(grade({'code': 'def f(a):\n a.clear()\n return []', 'function': 'f', 'tests': [([[1]], [])]})['passed'])

    def test_all_coding_fixture_ground_truth(self):
        references = {
            'dedupe_records': 'def dedupe(records):\n seen=set()\n result=[]\n for record in records:\n  if record["id"] not in seen:\n   seen.add(record["id"])\n   result.append(record)\n return result',
            'versions': 'def newer(a,b):\n x=list(map(int,a.split(".")))\n y=list(map(int,b.split(".")))\n n=max(len(x),len(y))\n return x+[0]*(n-len(x)) > y+[0]*(n-len(y))',
            'budget': 'def output_budget(context,prompt,requested,reserve):\n return max(0,min(requested,context-prompt-reserve))',
            'retry': 'def retryable(status,method,idempotency_key):\n return (status==429 or 500<=status<=599) and (method.upper() in ("GET","HEAD") or bool(idempotency_key))',
            'ranges': 'def clip_range(start,end,size):\n if size==0 or start>=size or end<start:\n  return None\n return [start,min(end,size-1)]',
        }
        for case in suite():
            if case.get('kind') == 'code':
                self.assertTrue(grade({'code': references[case['family']], 'function': case['function'], 'tests': case['tests']})['passed'], case['id'])

    def test_staging_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('../outside', '/etc/passwd', 'folder/../../escape', ''):
                with self.assertRaises(ValueError):
                    safe_path(root, name)
            (root / 'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                safe_path(root, 'link/escape')
            self.assertEqual(safe_path(root, 'nested/config.json'), root / 'nested/config.json')

    def test_staging_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test'
            path.write_bytes(b'abc')
            self.assertTrue(digest_file(path, {'size': 3, 'lfs': {'sha256': hashlib.sha256(b'abc').hexdigest()}}))
            self.assertTrue(digest_file(path, {'size': 3, 'blobId': hashlib.sha1(b'blob 3\0abc').hexdigest()}))
            self.assertFalse(digest_file(path, {'size': 4, 'lfs': {'sha256': hashlib.sha256(b'abc').hexdigest()}}))


if __name__ == '__main__':
    unittest.main()
