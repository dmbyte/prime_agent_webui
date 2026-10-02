"""Read-only, bounded-memory ISO/static HTTP server; runs ONLY in the sandbox."""
import email.utils
import http.server
import mimetypes
import os
import re
import stat
import threading
from urllib.parse import unquote, urlsplit


def open_public_file(root, url):
    # Resolve each component with openat/O_NOFOLLOW, not resolve-then-open.
    # This also closes symlink replacement races while agents edit the site.
    path = unquote(urlsplit(url).path)
    parts = path.strip('/').split('/') if path.strip('/') else ['index.html']
    if any(not part or part.startswith('.') or '\\' in part or '\x00' in part for part in parts):
        raise PermissionError('Not a public file')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            new = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = new
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PermissionError('Only regular files are published')
        result = os.fdopen(fd, 'rb')
        fd = -1
        return result, parts[-1]
    finally:
        if fd >= 0:
            os.close(fd)


def byte_range(value, size):
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value or '')
    if not match or not any(match.groups()) or size == 0:
        raise ValueError('Unsatisfiable range')
    left, right = match.groups()
    if not left:
        count = int(right)
        if count <= 0:
            raise ValueError('Unsatisfiable range')
        return max(0, size - count), size - 1
    start, end = int(left), min(int(right), size - 1) if right else size - 1
    if start > end or start >= size:
        raise ValueError('Unsatisfiable range')
    return start, end


class StaticHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'PrimeHosting/1'

    def log_message(self, *args):
        pass  # Do not record URLs or query strings in shared logs.

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        try:
            stream, name = open_public_file(self.server.root, self.path)
        except (OSError, ValueError):
            self.send_error(404, 'Not found')
            return
        with stream:
            info = os.fstat(stream.fileno())
            size = info.st_size
            start, end, code = 0, size - 1, 200
            # Only a single range is required for ISO virtual media; multi-range
            # is deliberately rejected. If-Range mismatches send the full file.
            modified = email.utils.formatdate(info.st_mtime, usegmt=True)
            tag = '"%x-%x"' % (info.st_mtime_ns, size)
            range_header = self.headers.get('Range')
            if range_header and self.headers.get('If-Range', tag) in {tag, modified}:
                try:
                    start, end = byte_range(range_header, size)
                    code = 206
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
            self.send_response(code)
            self.send_header('Content-Type', mimetypes.guess_type(name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Last-Modified', modified)
            self.send_header('ETag', tag)
            self.send_header('X-Content-Type-Options', 'nosniff')
            if code == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if body:
                stream.seek(start)
                remaining = end - start + 1
                try:
                    while remaining > 0:
                        chunk = stream.read(min(256 * 1024, remaining))
                        if not chunk:
                            self.close_connection = True
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass


class StaticServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, *args, **kwargs):
        self.clients = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.clients.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.clients.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.clients.release()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(30)
        return connection, address


def serve(root='/site', port=8000):
    server = StaticServer(('127.0.0.1', port), StaticHandler)
    server.root = root
    server.serve_forever()


if __name__ == '__main__':
    serve()
