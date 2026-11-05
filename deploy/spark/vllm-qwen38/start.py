#!/usr/bin/env python3
"""Start the reviewed FP4 serving profile; preserve containers and fail on drift.

Install beside the reviewed evals/spark/prepare_trial.py.
runtime.json supplies only model_dir/cache_dir, never arbitrary shell flags.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from prepare_trial import SERVE_SHA256, transform

NAME = 'vllm-qwen38'
EXPECTED_IMAGE = 'eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595'
REVISION = 'b22d249d5406c0720a3fdac16ca54f2ac3d8bf4b'


def configuration(root):
    config = json.loads((root/'runtime.json').read_text())
    if not isinstance(config,dict) or set(config) != {'model_dir','cache_dir'}:
        raise ValueError('runtime.json needs only model_dir and cache_dir')
    for key,value in config.items():
        if not isinstance(value,str) or not Path(value).is_absolute() or len(Path(value).resolve().parts)<4:
            raise ValueError('Use dedicated absolute model/cache directories')
        config[key] = str(Path(value).resolve())
    if config['model_dir'] == config['cache_dir']:
        raise ValueError('Model and cache directories must differ')
    receipt = json.loads((Path(config['model_dir'])/'prime-stage-receipt.json').read_text())
    if receipt.get('revision') != REVISION or receipt.get('image') != EXPECTED_IMAGE or receipt.get('metadata_only') is not False:
        raise ValueError('Full verified pinned model staging is required')
    return config


def launcher(source, fingerprint):
    if hashlib.sha256(source).hexdigest() != SERVE_SHA256:
        raise ValueError('Pinned upstream launcher changed')
    script = transform(source.decode())
    label = '--label prime.model-eval=fp4-20261103'
    if script.count(label) != 1: raise ValueError('Reviewed transform changed')
    return script.replace(label, '--restart unless-stopped --label prime.inference=qwen-fp4 '
        '--label prime.runtime-fingerprint='+fingerprint)


def docker(*args, check=True):
    return subprocess.run(['docker',*args],check=check,capture_output=True,text=True,timeout=180)


def inspect(name):
    result = docker('inspect',name,check=False)
    if result.returncode:
        if 'no such object' not in result.stderr.lower() and 'no such container' not in result.stderr.lower():
            raise RuntimeError('Cannot establish container state')
        return None
    return json.loads(result.stdout)[0]


def main(check_only=False):
    root = Path(__file__).resolve().parent
    config = configuration(root)
    model, cache = Path(config['model_dir']), Path(config['cache_dir'])
    source = (model/'recipe/serve/serve.sh').read_bytes()
    profile = dict(config,image=EXPECTED_IMAGE,revision=REVISION,context=262144,utilization=.76,
        sequences=1,batch=8192,mtp=4,qp_moe=0,port=30001,memory='98g',version=1,
        launcher_sha256=hashlib.sha256(transform(source.decode()).encode()).hexdigest())
    fingerprint = hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
    script = launcher(source,fingerprint)
    # This launcher never stops/deletes another engine or an existing container.
    current = inspect(NAME)
    if current:
        labels = current['Config'].get('Labels',{})
        if (labels.get('prime.inference') != 'qwen-fp4'
                or labels.get('prime.runtime-fingerprint') != fingerprint
                or current['Config'].get('Image') != EXPECTED_IMAGE):
            raise RuntimeError('Existing FP4 container differs; review it explicitly, never overwrite')
    image=json.loads(docker('image','inspect',EXPECTED_IMAGE).stdout)[0]
    if image.get('Architecture')!='arm64': raise RuntimeError('Reviewed ARM64 image required')
    if check_only:
        print('FP4 preflight passed: pinned configuration/image/launcher and container ownership',flush=True)
        return
    prior = inspect('llama-qwen38')
    if prior and prior['State']['Running']:
        raise RuntimeError('IQ4 is running; use an admitted idle-time switch')
    if current:
        if not current['State']['Running']: docker('start',current['Id'])
    else:
        cache.mkdir(parents=True,exist_ok=True)
        path = model/'recipe/serve'/('prime-production-'+fingerprint[:16]+'.sh')
        if path.exists():
            if path.is_symlink() or path.read_text() != script:
                raise RuntimeError('Derived launcher differs')
        else:
            with path.open('x') as stream: stream.write(script)
        env = {'HOME':os.environ['HOME'],'PATH':os.environ['PATH'], 'NAME':NAME,'IMAGE':EXPECTED_IMAGE,
            'PORT':'30001','MODEL_DIR':str(model),'CACHE_DIR':str(cache),'MAX_MODEL_LEN':'262144',
            'MAX_NUM_SEQS':'1','MAX_NUM_BATCHED_TOKENS':'8192','GPU_MEMORY_UTILIZATION':'0.76',
            'MTP_TOKENS':'4','QP_MOE':'0'}
        subprocess.run(['bash',str(path)],env=env,check=True,timeout=180)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic()+1800
    while time.monotonic()<deadline:
        current = inspect(NAME)
        if not current or not current['State']['Running']:
            raise RuntimeError('FP4 runtime exited')
        try:
            with opener.open('http://127.0.0.1:30001/health',timeout=3) as response:
                if response.status==200:
                    print('FP4 ready: 256K, one slot, local-only endpoint; IQ4 preserved',flush=True)
                    return
        except OSError: pass
        time.sleep(5)
    raise RuntimeError('FP4 health deadline exceeded; inspect logs and use retained IQ4 rollback')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Read-only preflight; never start/stop a container')
    main(parser.parse_args().check)
