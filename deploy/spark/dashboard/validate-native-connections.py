#!/usr/bin/env python3
"""Explicit synthetic-only external canary for native OpenShell substitution.

Run on the Spark as the trusted host operator, with a private staging directory
and reviewed image manifest. Contacts only https://httpbin.org with generated
dummy credentials, creates/deletes pc-* resources, never reads the user vault.
"""
import argparse
import base64
import json
from pathlib import Path
import secrets
import time
from unittest import mock
import connection_native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-synthetic-external-canary', action='store_true', required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    runtime = connection_native.NativeRuntime(args.state, args.manifest)
    runtime.reap(startup=True)
    secret = 'prime-synthetic-'+secrets.token_hex(16)
    for style, path, value in [('bearer', '/bearer', secret),
                              ('basic', '/headers', base64.b64encode(('fixture:'+secret).encode()).decode())]:
        with mock.patch.object(connection_native, 'http_binding', return_value=('https://httpbin.org', [path], value, style)):
            with runtime.lease({'adapter': 'github-readonly'}, {'token': value}, time.time()+120) as lease:
                result = lease.get_json('https://httpbin.org', path, {})
                if style == 'bearer':
                    assert result.get('authenticated') is True and result.get('token') == value
                else:
                    assert result.get('headers', {}).get('Authorization') == 'Basic '+value
                try:
                    lease.get_json('https://httpbin.org', '/get', {})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Out-of-scope path accepted')
                # Only compare a digest, never stream the real test token into the
                # operation sandbox or print it in test output.
                code = "import os,hashlib,json; print(json.dumps({'digest':hashlib.sha256(os.environ['PRIME_UPSTREAM_TOKEN'].encode()).hexdigest()}))"
                raw = runtime.run(['sandbox', 'exec', '--name', lease.name, '--no-login-shell', '--no-tty', '--',
                                   connection_native.PYTHON, '-c', code])
                import hashlib
                assert json.loads(raw)['digest'] != hashlib.sha256(value.encode()).hexdigest()
                # A gateway-side expiry must deny use even while the worker lives.
                runtime.run(['provider', 'update', lease.name, '--credential-expires-at',
                             'PRIME_UPSTREAM_TOKEN='+str(int((time.time()-1)*1000))])
                # An intentionally expired credential cannot become "ready" for
                # new processes; --wait is not a revocation acknowledgement.
                deadline = time.monotonic()+20
                while True:
                    try:
                        lease.get_json('https://httpbin.org', path, {})
                    except RuntimeError:
                        break
                    if time.monotonic() >= deadline:
                        raise AssertionError('Expired provider still authenticated')
                    time.sleep(1)
        print('PASS: '+style+' substitution, placeholder isolation, path denial, expiry and cleanup', flush=True)
    assert not list(args.state.glob('pc-*.json'))


if __name__ == '__main__': main()
