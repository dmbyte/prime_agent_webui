#!/usr/bin/env python3
"""Run on a different LAN machine against validate-hosting.py's synthetic URLs."""
import argparse
import base64
import http.client
import json
import os
import socket
from urllib.parse import urlsplit


def request(url, method='GET', headers=None):
    parsed = urlsplit(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        connection.request(method, parsed.path or '/', headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--static', required=True)
    parser.add_argument('--app', required=True)
    args = parser.parse_args()
    root = args.static.rstrip('/')
    assert request(root+'/')[2] == b'PRIME_HOSTING_STATIC_PASS\n'
    status, headers, body = request(root+'/fixture.iso', 'HEAD')
    assert status == 200 and int(headers['Content-Length']) > 5*1024**3 and not body
    status, headers, body = request(root+'/fixture.iso', headers={'Range':f'bytes=-{len(b"PRIME_ISO_RANGE_PASS")}'})
    assert status == 206 and body == b'PRIME_ISO_RANGE_PASS'
    assert request(root+'/fixture.iso', headers={'Range':'bytes=99999999999-'})[0] == 416
    for path in ('/.env', '/symlink.iso', '/%2e%2e/.env'):
        assert request(root+path)[0] == 404
    app = json.loads(request(args.app)[2])
    assert app == dict(marker='PRIME_HOSTING_APP_PASS', externalUrl=args.app)
    parsed = urlsplit(args.app)
    with socket.create_connection((parsed.hostname, parsed.port), timeout=10) as connection:
        key = base64.b64encode(os.urandom(16)).decode()
        connection.sendall((f'GET /socket HTTP/1.1\r\nHost: {parsed.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        result = b''
        while b'socket-ok' not in result and len(result) < 8192:
            chunk = connection.recv(4096)
            if not chunk:
                break
            result += chunk
        assert b'101 Switching Protocols' in result and b'\x81\x09socket-ok' in result
    print('LAN checks PASS: static GET, 5-GiB HEAD/range, 416, traversal/dotfile/symlink denial, app external URL, WebSocket frame')


if __name__ == '__main__':
    main()
