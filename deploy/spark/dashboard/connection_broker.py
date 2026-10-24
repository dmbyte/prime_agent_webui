#!/usr/bin/env python3
"""Opt-in loopback connection broker; no management or plaintext-read endpoint."""
import json
import os
import signal
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import connections
from connection_sol import IPMIUnavailable


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
        except connections.UnsupportedCertificatePolicy:
            status, result = 400, {'error': 'Native OpenShell HTTP does not support this saved certificate exception. Use verified TLS, or explicitly select Direct trusted broker for this connection in Settings. No fallback was attempted.'}
        except IPMIUnavailable as error:
            status, result = 502, {'error': str(error)}
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
    manager = connections.Connections()
    connections.console_adapters()  # Reject an invalid allowlist before serving.
    stopping = threading.Event()
    if os.environ.get('PRIME_CONNECTION_HTTP_TRANSPORT', 'direct') not in ('direct', 'openshell'):
        raise SystemExit('Unsupported connection HTTP transport')
    native = None
    if (os.environ.get('PRIME_CONNECTION_HTTP_TRANSPORT', 'direct') == 'openshell'
            or os.environ.get('PRIME_CONNECTION_CONSOLES_ENABLED') == '1'):
        from connection_native import NativeRuntime
        native = NativeRuntime(manager.root/'connection-runtime', os.environ['PRIME_CONNECTION_IMAGE_MANIFEST'])
        native.reap(startup=True)
        if os.environ.get('PRIME_CONNECTION_HTTP_TRANSPORT') == 'openshell':
            manager.native = native
        if os.environ.get('PRIME_CONNECTION_CONSOLES_ENABLED') == '1':
            from connection_sessions import Sessions
            manager.sessions = Sessions(manager, native)
        def reap():
            while not stopping.wait(5):
                try:
                    if manager.sessions:
                        manager.sessions.reap()
                    native.reap()
                except Exception:
                    print('{"event":"connection_cleanup_failed"}', flush=True)
        threading.Thread(target=reap, daemon=True).start()
    server = Server(('127.0.0.1', 8767), manager)
    def stop(*_):
        stopping.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    finally:
        stopping.set()
        server.server_close()
        if manager.sessions:
            manager.sessions.reap(all_sessions=True)
        if native:
            native.reap(startup=True)
