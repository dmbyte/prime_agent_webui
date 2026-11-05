import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).parents[2]/'deploy/spark/vllm-qwen38/start.py'
spec = importlib.util.spec_from_file_location('fp4_runtime',path)
runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)


class FP4RuntimeTests(unittest.TestCase):
    def test_iq4_launcher_refuses_running_fp4_before_mutating_docker(self):
        import os
        import subprocess
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); binary=root/'bin'; binary.mkdir()
            source=Path(__file__).parents[2]/'deploy/spark/llama-qwen38/start.sh'
            shutil.copyfile(source,root/'start.sh'); (root/'llama.env').write_text('')
            fake=binary/'docker'
            fake.write_text('#!/bin/sh\nif [ "$1" = inspect ] && [ "$2" = vllm-qwen38 ]; then echo true; else echo unexpected >&2; exit 99; fi\n')
            fake.chmod(0o755)
            result=subprocess.run(['bash',str(root/'start.sh')],capture_output=True,text=True,
                env=os.environ|{'PATH':str(binary)+':'+os.environ['PATH']})
            self.assertEqual(result.returncode,1)
            self.assertIn('FP4 is running',result.stderr)
            self.assertNotIn('unexpected',result.stderr)

    def test_missing_container_is_case_insensitive_but_daemon_errors_fail(self):
        from types import SimpleNamespace
        for error in ('error: no such object: vllm-qwen38','Error: No such object: vllm-qwen38'):
            with patch.object(runtime,'docker',return_value=SimpleNamespace(returncode=1,stderr=error)):
                self.assertIsNone(runtime.inspect('vllm-qwen38'))
        with patch.object(runtime,'docker',return_value=SimpleNamespace(returncode=1,stderr='Cannot connect to Docker daemon')):
            with self.assertRaises(RuntimeError): runtime.inspect('vllm-qwen38')

    def test_idle_metrics_support_only_complete_known_engine_families(self):
        from maintenance_guard import idle_metrics
        idle_metrics('llamacpp:requests_processing 0\nllamacpp:requests_deferred 0\n')
        idle_metrics('vllm:num_requests_running{model_name="qwen"} 0\nvllm:num_requests_waiting{model_name="qwen"} 0\n')
        for value in ('', 'vllm:num_requests_running 0\n',
                'vllm:num_requests_running 1\nvllm:num_requests_waiting 0\n',
                'llamacpp:requests_processing NaN\nllamacpp:requests_deferred 0\n'):
            with self.assertRaises(RuntimeError): idle_metrics(value)

    def test_unreviewed_launcher_denied(self):
        with self.assertRaises(ValueError): runtime.launcher(b'changed','a'*64)

    def test_runtime_transform_keeps_hardening_and_changes_only_ownership(self):
        source = b'synthetic pinned recipe'
        import hashlib
        with patch.object(runtime,'SERVE_SHA256',hashlib.sha256(source).hexdigest()), \
                patch.object(runtime,'transform',return_value='--cap-drop=ALL --label prime.model-eval=fp4-20261103 --network bridge'):
            result = runtime.launcher(source,'a'*64)
        self.assertIn('--cap-drop=ALL',result)
        self.assertIn('--network bridge',result)
        self.assertIn('--restart unless-stopped',result)
        self.assertIn('prime.inference=qwen-fp4',result)
        self.assertNotIn('prime.model-eval',result)

    def test_incomplete_staging_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); model=root/'model'; model.mkdir()
            (root/'runtime.json').write_text(json.dumps({'model_dir':str(model),'cache_dir':str(root/'cache')}))
            (model/'prime-stage-receipt.json').write_text(json.dumps({'revision':runtime.REVISION,
                'image':runtime.EXPECTED_IMAGE,'metadata_only':True}))
            with self.assertRaises(ValueError): runtime.configuration(root)

    def test_arbitrary_launch_flags_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'runtime.json').write_text(json.dumps({'model_dir':'/tmp/a/model','cache_dir':'/tmp/a/cache','flags':'--network host'}))
            with self.assertRaises(ValueError): runtime.configuration(root)


if __name__=='__main__': unittest.main()
