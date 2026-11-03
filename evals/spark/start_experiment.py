#!/usr/bin/env python3
"""Start a bounded, guarded experiment as a systemd user unit; never detach bare processes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--grader-image', required=True)
    parser.add_argument('--candidate', action='store_true', help='Temporarily pause production and try prepared FP4; otherwise control only')
    parser.add_argument('--disable-qp-moe', action='store_true', help='Candidate only: test the documented prefill-kernel fallback')
    args = parser.parse_args()
    if args.disable_qp_moe and not args.candidate:
        parser.error('--disable-qp-moe requires --candidate')
    root = args.root.resolve()
    # These paths become systemd ExecStopPost arguments, not a shell command.
    if not re.fullmatch(r'/[A-Za-z0-9_/-]+', str(root)) or len(root.parts) < 4:
        parser.error('Use a dedicated absolute trial root with simple path characters')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.grader_image):
        parser.error('An immutable grader image ID is required')
    harness = root / 'harness'
    for filename in ('maintenance_guard.py', 'run_screen.py', 'candidate_trial.py', 'suite.py', 'code_grader.py', 'candidate.json'):
        if not (harness / filename).is_file():
            parser.error('Incomplete harness export')
    if args.candidate and not (root / 'candidate/recipe/serve/prime-trial-serve.sh').is_file():
        parser.error('Run full staging and prepare_trial first')
    mode = 'fp4' if args.candidate else 'control'
    stamp = str(int(time.time()))
    unit = f'prime-model-eval-{mode}-{stamp}'
    command = ['systemd-run', '--user', '--unit=' + unit,
               '--property=RuntimeMaxSec=4500', '--property=TimeoutStopSec=720',
               '--property=KillMode=mixed']
    # KillMode=mixed sends TERM only to the guard, which forwards it and keeps
    # admission held during candidate finally/recovery; forced kill is bounded.
    if args.candidate:
        command += ['--property=ExecStopPost=/usr/bin/python3 ' + str(harness / 'candidate_trial.py') + ' --root ' + str(root) + ' --recover']
    command += ['/usr/bin/python3', str(harness / 'maintenance_guard.py'), '--', '/usr/bin/python3']
    if args.candidate:
        command += [str(harness / 'candidate_trial.py'), '--root', str(root), '--grader-image', args.grader_image]
        if args.disable_qp_moe:
            command.append('--disable-qp-moe')
    else:
        command += [str(harness / 'run_screen.py'), '--label', 'iq4-256k-low',
                    '--output', str(root / f'results/control-{stamp}.jsonl'), '--grader-image', args.grader_image]
    subprocess.run(command, check=True)
    print(json.dumps({'unit': unit, 'mode': mode, 'root': str(root)}))


if __name__ == '__main__':
    main()
