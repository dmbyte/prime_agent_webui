#!/usr/bin/env python3
"""Host administrator lifecycle controls, unavailable inside task containers."""
import argparse
import json
import socket
import task_common

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--owner', required=True)
parser.add_argument('action', choices=['list', 'logs', 'stop', 'renew'])
parser.add_argument('id', nargs='?')
parser.add_argument('--hours', type=int, default=24)
args = parser.parse_args()
if not task_common.SAFE_USER.fullmatch(args.owner):
    parser.error('Invalid owner')
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(180)
    connection.connect(f'/var/lib/prime-runner/hosting/{args.owner}/admin.sock')
    connection.sendall(json.dumps(dict(action=args.action, id=args.id, ttlHours=args.hours)).encode() + b'\n')
    with connection.makefile('rb') as stream:
        reply = json.loads(stream.readline(131073))
print(json.dumps(reply, indent=2))
raise SystemExit(0 if reply.get('ok') else 1)
