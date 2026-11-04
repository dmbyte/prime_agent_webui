import unittest
from unittest.mock import patch

from context_probe import MARKERS, fit_prompt, messages, token_count, validate_result
from candidate_trial import trial_name, validate_settings, recover, trial, LABEL
from pathlib import Path
import tempfile
import os
import subprocess
import start_experiment


class ContextTests(unittest.TestCase):
    def test_control_cannot_be_mislabelled_as_128k(self):
        argv = ['start_experiment.py', '--root', '/home/test/control', '--grader-image', 'sha256:' + 'a'*64,
                '--context', '131072', '--probe', 'context']
        with patch('sys.argv', argv), patch('start_experiment.subprocess.run') as run, patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                start_experiment.main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_trial_settings_bounded(self):
        validate_settings(262144, .76, 1)
        self.assertEqual(trial_name('prime-eval-context-256k'), 'prime-eval-context-256k')
        for bad in ('llama-qwen38', '../prime-eval-test', 'prime-eval-x;false'):
            with self.assertRaises(ValueError):
                trial_name(bad)
        for context, utilization, restarts in ((524288, .76, 1), (262144, .9, 1), (262144, .76, 3), (262144, float('nan'), 0)):
            with self.assertRaises(ValueError):
                validate_settings(context, utilization, restarts)

    def test_recovery_uses_recorded_trial_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'restore-production.json').write_text('{"production_id":"original","trial_name":"prime-eval-new"}')
            containers = [{'Id': 'original', 'State': {'Running': False}},
                          {'Id': 'new', 'Config': {'Labels': {'prime.model-eval': LABEL}}}]
            with patch('candidate_trial.inspect', side_effect=containers) as inspect, patch('candidate_trial.docker') as docker, patch('candidate_trial.healthy', return_value=True):
                recover(root)
                self.assertEqual(inspect.call_args_list[1].args, ('prime-eval-new',))
                self.assertEqual(docker.call_args_list[0].args[-1], 'new')

    def test_failed_context_probe_restores_with_exact_trial_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            containers = [None, {'Id': 'original', 'State': {'Running': True}},
                          {'Id': 'candidate', 'State': {'Running': True}}]
            with patch.dict(os.environ, {'PRIME_EVAL_MAINTENANCE_HELD': '1'}), \
                 patch('candidate_trial.inspect', side_effect=containers), \
                 patch('candidate_trial.healthy', return_value=True), \
                 patch('candidate_trial.docker'), patch('candidate_trial.threading.Thread'), \
                 patch('candidate_trial.signal.signal'), patch('candidate_trial.recover') as recovery, \
                 patch('candidate_trial.subprocess.run', side_effect=[None, subprocess.CalledProcessError(1, 'probe')]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    trial(root, 'sha256:' + 'a'*64, True, name='prime-eval-new',
                          context=262144, utilization=.76, probe='context', restart_checks=1)
                recovery.assert_called_once_with(root, None)
                env = run.call_args_list[0].kwargs['env']
                self.assertEqual((env['MAX_MODEL_LEN'], env['GPU_MEMORY_UTILIZATION'], env['QP_MOE']), ('262144', '0.76', '0'))
                self.assertIn('context_probe.py', ' '.join(run.call_args_list[1].args[0]))
                self.assertIn('prime-eval-new', (root / 'restore-production.json').read_text())

    def test_unowned_recovery_marker_cannot_interrupt_other_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'restore-production.json').write_text('{"production_id":"original","recovery_token":"other-invocation"}')
            with patch('candidate_trial.inspect') as inspect, patch('candidate_trial.docker') as docker:
                recover(root, 'this-invocation')
                inspect.assert_not_called()
                docker.assert_not_called()
            self.assertTrue((root / 'restore-production.json').exists())

    def test_deterministic_distributed_markers(self):
        conversation = messages(100)
        self.assertEqual(conversation, messages(100))
        text = conversation[-1]['content']
        for marker in MARKERS.values():
            self.assertEqual(text.count(marker), 1)
        self.assertLess(text.index(MARKERS['early']), text.index('Record 1:'))
        self.assertLess(text.index('Record 49:'), text.index(MARKERS['middle']))
        self.assertLess(text.index('Record 98:'), text.index(MARKERS['late']))

    def test_budget_fitting(self):
        def count(conversation):
            return conversation[-1]['content'].count('Record ') * 24 + 100
        conversation, counted, rows = fit_prompt(count, 16000)
        self.assertTrue(15744 <= counted <= 16000)
        self.assertEqual(count(conversation), counted)
        self.assertGreater(rows, 3)

    def test_vllm_tokenizer_receives_matching_effort(self):
        with patch('context_probe.post', return_value={'count': 100}) as post:
            self.assertEqual(token_count('http://127.0.0.1:30002', 'vllm', []), 100)
            self.assertEqual(post.call_args.args[2]['chat_template_kwargs'], {'reasoning_effort': 'low'})

    def test_recall_counts_and_finish_fail_closed(self):
        reply = {'content': '{"middle":"BIRCH-9153-TEAL"}'}
        expected = {'middle': MARKERS['middle']}
        timing = {'usage': {'prompt_tokens': 250000}, 'finish_reason': 'stop'}
        validate_result(reply, timing, expected, 250000, 262144)
        for metric in ({'usage': {'prompt_tokens': 128000}, 'finish_reason': 'stop'},
                       {'usage': {'prompt_tokens': 250000}, 'finish_reason': 'length'},
                       {'usage': {}, 'finish_reason': 'stop'}):
            with self.assertRaises(ValueError):
                validate_result(reply, metric, expected, 250000, 262144)
        with self.assertRaises(ValueError):
            validate_result(reply, timing, expected, 250000, 131072)
        with self.assertRaises(ValueError):
            validate_result({'content': '{}'}, timing, expected, 250000, 262144)


if __name__ == '__main__':
    unittest.main()
