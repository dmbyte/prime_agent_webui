#!/usr/bin/env python3
"""Derive a fail-closed loopback-only launcher from the exact reviewed recipe.

Never executes it. Generated launcher remains alongside the original so relative
patch paths stay valid. Verified upstream artifacts are not modified.
"""
import argparse
import hashlib
import json
from pathlib import Path

SERVE_SHA256 = '3557943f04a4d0541d5e78a4709056b46ad9278c102bb7c20a349aaae58eac9f'


def transform(source):
    replacements = {
        'docker rm -f "$NAME" >/dev/null 2>&1 || true':
            'if docker inspect "$NAME" >/dev/null 2>&1; then echo "Trial container already exists; refusing replacement" >&2; exit 1; fi',
        'docker run -d --name "$NAME"':
            'docker run -d --name "$NAME" --user "$(id -u):$(id -g)" -e HOME=/cache/home -e XDG_CACHE_HOME=/cache --label prime.model-eval=fp4-20261103 --memory=98g --memory-swap=98g --cap-drop=ALL --security-opt=no-new-privileges',
        '--gpus all --ipc host --network host --shm-size=16g':
            '--gpus all --ipc private --network bridge -p "127.0.0.1:$PORT:$PORT" --shm-size=16g',
        '-e HF_HUB_DISABLE_TELEMETRY=1':
            '-e HF_HUB_DISABLE_TELEMETRY=1 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Reviewed launcher structure changed')
        source = source.replace(old, new)
    return source


def prepare(root):
    manifest = json.loads(Path(__file__).with_name('candidate.json').read_text())
    receipt = json.loads((root / 'prime-stage-receipt.json').read_text())
    if receipt['revision'] != manifest['revision'] or receipt['metadata_only'] or receipt['image'] != manifest['image']:
        raise ValueError('Full verified staging receipt required')
    source = root / 'recipe/serve/serve.sh'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SERVE_SHA256:
        raise ValueError('Unexpected upstream launcher')
    destination = source.with_name('prime-trial-serve.sh')
    with destination.open('x') as out:
        out.write(transform(raw.decode()))
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(prepare(args.root.resolve()))
