#!/usr/bin/env python3
import socket
import sys
import json
import os
import io
from email.message import Message
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "container"))
import model_gateway


class ModelGatewayNetworkTests(unittest.TestCase):
    def addresses(self, mode):
        rows = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.2.3.4", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        with mock.patch.object(model_gateway.socket, "getaddrinfo", return_value=rows):
            return model_gateway.allowed_address("example.test", mode)

    def test_internet_is_public_only(self):
        self.assertEqual(self.addresses("internet"), ["8.8.8.8"])

    def test_lan_is_private_only(self):
        self.assertEqual(self.addresses("lan"), ["10.2.3.4"])

    def test_full_allows_public_and_private_but_not_host_loopback(self):
        self.assertEqual(self.addresses("full"), ["8.8.8.8", "10.2.3.4"])


class ModelGatewayCredentialTests(unittest.TestCase):
    def connection_reply(self, raw):
        handler = object.__new__(model_gateway.Handler)
        handler.server = mock.Mock(prime_user='alice')
        handler.command, handler.path = 'POST', '/connections'
        request = b'{"action":"call","token":"synthetic"}'
        handler.rfile = io.BytesIO(request)
        handler.headers = Message(); handler.headers['Content-Length'] = str(len(request))
        handler.send_json = mock.Mock()
        response = mock.Mock(status=200); response.read.return_value = raw
        with mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED':'1'}), mock.patch.object(model_gateway.http.client,'HTTPConnection') as cls:
            cls.return_value.getresponse.return_value = response
            handler.proxy()
            response.read.assert_called_once_with(1_000_001)
            cls.return_value.close.assert_called_once()
        return handler.send_json.call_args.args

    def test_private_capture_larger_than_metadata_limit_is_preserved(self):
        import base64
        body = {'mimeType':'image/png','image':base64.b64encode(b'x'*700000).decode()}
        self.assertEqual(self.connection_reply(json.dumps(body).encode()), (200,body))

    def test_private_capture_envelope_remains_bounded(self):
        status, body = self.connection_reply(b'x'*1_000_001)
        self.assertEqual(status,502)
        self.assertEqual(body,{'error':'Connection response exceeded limit'})

    def test_invalid_capture_json_is_not_forwarded(self):
        self.assertEqual(self.connection_reply(b'not JSON'), (502,{'error':'Connection broker unavailable'}))

    def test_large_capture_crosses_real_broker_http_and_gateway_socket(self):
        import http.client
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        payload = {'mimeType':'image/png','image':'synthetic-'*90000}
        observed = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                observed.append(self.headers.get('X-Prime-Connection-Owner'))
                raw = json.dumps(payload).encode()
                self.send_response(200); self.send_header('Content-Length',str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
        original = http.client.HTTPConnection
        upstream = ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        upstream_thread = threading.Thread(target=upstream.serve_forever,daemon=True); upstream_thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory)/'gateway.sock')
                gateway = model_gateway.Server(path,'synthetic-owner')
                thread = threading.Thread(target=gateway.serve_forever,daemon=True); thread.start()
                class UnixClient(original):
                    def connect(self):
                        self.sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                        self.sock.settimeout(5); self.sock.connect(path)
                def routed(host,port,**kwargs):
                    self.assertEqual((host,port),('127.0.0.1',8767))
                    return original('127.0.0.1',upstream.server_port,**kwargs)
                client = UnixClient('localhost',timeout=5)
                try:
                    with mock.patch.dict(os.environ,{'PRIME_CONNECTIONS_ENABLED':'1'}), mock.patch.object(model_gateway.http.client,'HTTPConnection',side_effect=routed):
                        client.request('POST','/connections',b'{"token":"synthetic","action":"list"}',
                            {'Content-Type':'application/json','X-Prime-Connection-Owner':'spoofed'})
                        response = client.getresponse()
                        self.assertEqual(response.status,200)
                        self.assertEqual(json.loads(response.read()),payload)
                    self.assertEqual(observed,['synthetic-owner'])
                finally:
                    client.close(); gateway.shutdown(); gateway.server_close(); thread.join(2)
        finally:
            upstream.shutdown(); upstream.server_close(); upstream_thread.join(2)

    def test_connection_route_overwrites_spoofed_owner_and_never_forwards_cookies(self):
        handler = object.__new__(model_gateway.Handler)
        handler.server = mock.Mock(prime_user='alice')
        handler.command, handler.path = 'POST', '/connections'
        raw = b'{"action":"list","token":"fixture"}'
        handler.rfile = io.BytesIO(raw)
        handler.headers = Message()
        for key, value in {'Content-Length': str(len(raw)), 'X-Prime-Connection-Owner': 'bob', 'Cookie': 'secret-cookie'}.items():
            handler.headers[key] = value
        handler.send_json = mock.Mock()
        response = mock.Mock(status=200); response.read.return_value = b'{"connections":[]}'
        with mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED': '1'}), mock.patch.object(model_gateway.http.client, 'HTTPConnection') as cls:
            cls.return_value.getresponse.return_value = response
            handler.proxy()
            self.assertEqual(cls.call_args.args, ('127.0.0.1', 8767))
            self.assertEqual(cls.return_value.request.call_args.args[3], {'Content-Type': 'application/json', 'X-Prime-Connection-Owner': 'alice'})
            handler.send_json.assert_called_once_with(200, {'connections': []})
        with mock.patch.dict(os.environ, {'PRIME_CONNECTIONS_ENABLED': '0'}):
            handler.proxy()
            self.assertEqual(handler.send_json.call_args.args[0], 403)

    def test_reused_refresh_token_has_actionable_safe_error(self):
        class Response:
            status = 401
            def read(self, _limit):
                return json.dumps({"error": {"code": "refresh_token_reused", "message": "secret upstream detail"}}).encode()
        class Connection:
            def request(self, *_args, **_kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "credentials/global/auth.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"openai-codex": {"access": "a", "refresh": "r", "accountId": "id", "expires": 1}}))
            os.chmod(path, 0o600)
            with mock.patch.object(model_gateway, "ROOT", root), mock.patch.object(model_gateway.http.client, "HTTPSConnection", return_value=Connection()):
                with self.assertRaisesRegex(model_gateway.CodexCredentialError, "run /login"):
                    model_gateway.credential("alice")


if __name__ == "__main__":
    unittest.main()
