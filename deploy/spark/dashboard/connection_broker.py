#!/usr/bin/env python3
"""Opt-in loopback connection broker; no management or plaintext-read endpoint."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import connections


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, manager=None):
        self.manager = manager or connections.Connections()
        self.capacity = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def do_POST(self):
        status, result = 403, {'error': 'Connection operation denied'}
        task_id = None
        try:
            if self.path != '/connections' or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            length = int(self.headers.get('Content-Length', '0'))
            if not 2 <= length <= 4096 or self.headers.get_content_type() != 'application/json':
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            result = self.server.manager.dispatch(body, self.headers.get('X-Prime-Connection-Owner', ''))
            task_id = body['token'].split('.')[0]
            status = 200
        except PermissionError:
            pass
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            status, result = 400, {'error': 'Connection request unavailable or invalid; check Settings'}
        except Exception:
            # Never serialize upstream exceptions, headers, request data or secrets.
            status, result = 502, {'error': 'Connection read failed; check access, expiry and TLS trust'}
        print(json.dumps({'event': 'connection_read', 'taskId': task_id, 'status': status}), flush=True)
        raw = json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)


if __name__ == '__main__':
    if os.environ.get('PRIME_CONNECTIONS_ENABLED') != '1':
        raise SystemExit('Connection runtime is not enabled')
    Server(('127.0.0.1', 8767)).serve_forever()
