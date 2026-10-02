#!/usr/bin/env python3
"""Opt-in, recoverable migration of host Prime defaults to Qwen-only.

Does not stop services or overwrite conversation/project effort overrides.
Run as the WebUI owner after copying the updated model service files.
"""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main():
    root = Path.home() / '.prime/agent'
    backup = root / ('qwen-only-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700, parents=True)
    recipe = json.loads(Path(__file__).with_name('models.json').read_text())
    for name in ('models.json', 'settings.json'):
        path = root / name
        if path.exists():
            shutil.copy2(path, backup / name)
            data = json.loads(path.read_text())
        else:
            data = {}
        if name == 'models.json':
            data.setdefault('providers', {})['spark-qwen'] = recipe['providers']['spark-qwen']
        else:
            data.update(defaultProvider='spark-qwen', defaultModel='qwen3.8-flash-next',
                        defaultThinkingLevel='low', webuiThinkingMode='auto')
            enabled = set(data.get('enabledModels', []))
            enabled.discard('spark-nemotron/nemotron-3.5-lightning')
            enabled.add('spark-qwen/qwen3.8-flash-next')
            data['enabledModels'] = sorted(enabled)
        with tempfile.NamedTemporaryFile(mode='w', dir=root, prefix='.qwen-only-', delete=False) as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            temporary = Path(stream.name)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'Qwen-only defaults installed; previous settings retained in {backup}')


if __name__ == '__main__':
    main()
