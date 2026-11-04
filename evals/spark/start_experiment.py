#!/usr/bin/env python3
"""Start a bounded, guarded experiment as a systemd user unit; never detach bare processes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

from candidate_trial import NAME, trial_name, validate_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--grader-image', required=True)
    parser.add_argument('--candidate', action='store_true', help='Temporarily pause production and try prepared FP4; otherwise control only')
    parser.add_argument('--disable-qp-moe', action='store_true', help='Candidate only: test the documented prefill-kernel fallback')
    parser.add_argument('--trial-name', default=NAME, type=trial_name)
    parser.add_argument('--context', type=int, choices=(131072, 262144))
    parser.add_argument('--gpu-memory-utilization', type=float, default=.73)
    parser.add_argument('--probe', choices=('screen', 'context', 'agent'), default='screen')
    parser.add_argument('--restart-checks', type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    context = args.context or (131072 if args.candidate else 262144)
    validate_settings(context, args.gpu_memory_utilization, args.restart_checks)
    if not args.candidate and context != 262144:
        parser.error('The reference production control remains at 262144; this flag does not reconfigure it')
    if args.disable_qp_moe and not args.candidate:
        parser.error('--disable-qp-moe requires --candidate')
    if not args.candidate and (args.restart_checks or args.gpu_memory_utilization != .73 or args.trial_name != NAME):
        parser.error('Candidate settings cannot change the production control')
    root = args.root.resolve()
    # These paths become systemd ExecStopPost arguments, not a shell command.
    if not re.fullmatch(r'/[A-Za-z0-9_/-]+', str(root)) or len(root.parts) < 4:
        parser.error('Use a dedicated absolute trial root with simple path characters')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.grader_image):
        parser.error('An immutable grader image ID is required')
    harness = root / 'harness'
    for filename in ('maintenance_guard.py', 'run_screen.py', 'candidate_trial.py', 'context_probe.py', 'agent_probe.py', 'agent_fixture.py', 'suite.py', 'code_grader.py', 'candidate.json'):
        if not (harness / filename).is_file():
            parser.error('Incomplete harness export')
    if args.candidate and not (root / 'candidate/recipe/serve/prime-trial-serve.sh').is_file():
        parser.error('Run full staging and prepare_trial first')
    if args.candidate and any((root / filename).exists() for filename in ('restore-production.json', 'restored-production.json', 'results/lifecycle.jsonl')):
        parser.error('Use a fresh trial root; never share recovery markers between runs')
    mode = 'fp4' if args.candidate else 'control'
    stamp = str(int(time.time()))
    unit = f'prime-model-eval-{mode}-{stamp}'
    recovery_token = uuid.uuid4().hex
    command = ['systemd-run', '--user', '--unit=' + unit,
               '--property=RuntimeMaxSec=' + ('10800' if args.probe == 'context' or args.restart_checks else '4500'), '--property=TimeoutStopSec=720',
               '--property=KillMode=mixed']
    if args.probe == 'agent':
        if (root / 'agent-work').exists() or (root / 'agent-runtime.json').exists():
            parser.error('Agent probes require a fresh root')
        command += ['--setenv=PRIME_EVAL_INVOCATION=' + recovery_token]
        if not args.candidate:
            command += ['--property=ExecStopPost=/usr/bin/python3 ' + str(harness / 'agent_probe.py') + ' --root ' + str(root) + ' --cleanup']
    # KillMode=mixed sends TERM only to the guard, which forwards it and keeps
    # admission held during candidate finally/recovery; forced kill is bounded.
    if args.candidate:
        command += ['--property=ExecStopPost=/usr/bin/python3 ' + str(harness / 'candidate_trial.py') + ' --root ' + str(root) + ' --recover --recovery-token ' + recovery_token]
    command += ['/usr/bin/python3', str(harness / 'maintenance_guard.py'), '--', '/usr/bin/python3']
    if args.candidate:
        command += [str(harness / 'candidate_trial.py'), '--root', str(root), '--grader-image', args.grader_image]
        command += ['--recovery-token', recovery_token]
        command += ['--trial-name', args.trial_name, '--context', str(context),
                    '--gpu-memory-utilization', str(args.gpu_memory_utilization),
                    '--probe', args.probe, '--restart-checks', str(args.restart_checks)]
        if args.disable_qp_moe:
            command.append('--disable-qp-moe')
    elif args.probe == 'agent':
        command += [str(harness / 'agent_probe.py'), '--root', str(root), '--port', '30001']
    elif args.probe == 'context':
        command += [str(harness / 'context_probe.py'), '--engine', 'llama', '--port', '30001',
                    '--context', str(context), '--output', str(root / f'results/context-control-{stamp}.jsonl')]
    else:
        command += [str(harness / 'run_screen.py'), '--label', 'iq4-256k-low',
                    '--output', str(root / f'results/control-{stamp}.jsonl'), '--grader-image', args.grader_image]
    subprocess.run(command, check=True)
    print(json.dumps({'unit': unit, 'mode': mode, 'root': str(root)}))


if __name__ == '__main__':
    main()
