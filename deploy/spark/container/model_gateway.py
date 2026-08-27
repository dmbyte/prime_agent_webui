#!/usr/bin/env python3
"""Credential-holding Unix-socket proxy for isolated Prime task containers."""
import http.client, ipaddress, json, os, select, socket, socketserver, stat, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(os.environ.get("PRIME_GATEWAY_ROOT", "/var/lib/prime-runner"))
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TARGETS = {"spark-nemotron": ("http", "127.0.0.1", 30000), "spark-qwen": ("http", "127.0.0.1", 30001)}
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host", "authorization", "chatgpt-account-id", "originator"}
_credential_locks = {}
_credential_locks_guard = threading.Lock()

def secure_json(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("Credential file ownership or mode is unsafe")
    if info.st_size < 2 or info.st_size > 1024 * 1024:
        raise RuntimeError("Credential file size is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("Credential file changed while opening")
        with os.fdopen(descriptor, "r") as stream:
            descriptor = -1
            return json.load(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)

def credential_lock(user):
    with _credential_locks_guard:
        return _credential_locks.setdefault(user, threading.Lock())

def credential(user, force_refresh=False):
    with credential_lock(user):
        personal = ROOT / "credentials/users" / user / "auth.json"
        path = personal if personal.exists() else ROOT / "credentials/global/auth.json"
        data = secure_json(path)
        row = data.get("openai-codex") or {}
        if not all(row.get(key) for key in ("access", "refresh", "accountId")):
            raise RuntimeError("Codex credential is incomplete")
        if force_refresh or row.get("expires", 0) <= int(time.time() * 1000) + 60000:
            body = urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":row["refresh"],"client_id":CLIENT_ID})
            conn = http.client.HTTPSConnection("auth.openai.com", timeout=30)
            conn.request("POST", "/oauth/token", body, {"Content-Type":"application/x-www-form-urlencoded"})
            response = conn.getresponse(); payload = json.loads(response.read(1024 * 1024)); conn.close()
            if response.status != 200 or not all(payload.get(key) for key in ("access_token", "refresh_token", "expires_in")):
                raise RuntimeError("Codex credential refresh failed")
            row.update(access=payload["access_token"], refresh=payload["refresh_token"], expires=int(time.time()*1000)+int(payload["expires_in"])*1000)
            temporary = path.with_name(path.name + ".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(data, stream, separators=(",", ":")); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        return dict(row)

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self): self.safe_proxy()
    def do_GET(self): self.safe_proxy()
    def log_message(self, *_): pass
    def safe_proxy(self):
        try:
            self.proxy()
        except (BrokenPipeError, ConnectionError):
            self.close_connection = True
        except Exception:
            if not self.wfile.closed:
                try: self.send_error(502, "Model gateway request failed")
                except (BrokenPipeError, ConnectionError): pass
            self.close_connection = True
    def proxy(self):
        user = self.server.prime_user
        parts = self.path.lstrip("/").split("/", 1)
        if len(parts) != 2 or parts[0] not in {*TARGETS, "openai-codex"}: return self.send_error(404)
        provider, path = parts
        length = int(self.headers.get("Content-Length", "0"))
        if length > 32 * 1024 * 1024: return self.send_error(413)
        body = self.rfile.read(length) if length else None
        headers = {k:v for k,v in self.headers.items() if k.lower() not in HOP}
        if provider == "openai-codex":
            auth = credential(user); scheme, host, port = "https", "chatgpt.com", 443
            path = "/backend-api/codex/" + path.removeprefix("codex/")
            headers.update({"Authorization":f"Bearer {auth['access']}","chatgpt-account-id":auth["accountId"],"originator":"pi","OpenAI-Beta":"responses=experimental"})
        else: scheme, host, port = TARGETS[provider]
        conn = (http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection)(host, port, timeout=300)
        conn.request(self.command, "/" + path, body, headers); response = conn.getresponse()
        if provider == "openai-codex" and response.status == 401:
            response.read(1024 * 1024); conn.close()
            auth = credential(user, force_refresh=True)
            headers.update({"Authorization":f"Bearer {auth['access']}","chatgpt-account-id":auth["accountId"]})
            conn = http.client.HTTPSConnection(host, port, timeout=300)
            conn.request(self.command, "/" + path, body, headers); response = conn.getresponse()
        self.send_response(response.status)
        for key,value in response.getheaders():
            if key.lower() not in HOP: self.send_header(key,value)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        while True:
            chunk=response.read1(65536)
            if not chunk: break
            self.wfile.write(chunk); self.wfile.flush()
        conn.close()

class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    def __init__(self, path, user): self.prime_user=user; super().__init__(path, Handler)

def allowed_address(host, mode):
    try: rows=socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror: return []
    result=[]
    for row in rows:
        address=ipaddress.ip_address(row[4][0])
        forbidden=address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved
        if forbidden or (mode == "internet" and address.is_private): continue
        result.append(row[4][0])
    return result

class ProxyHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line=self.rfile.readline(8193)
        if not line or len(line)>8192: return
        try: method,target,version=line.decode("ascii").strip().split(" ",2)
        except ValueError: return
        headers={}
        while True:
            row=self.rfile.readline(8193)
            if row in {b"\r\n",b"\n",b""}: break
            key,value=row.decode("iso-8859-1").split(":",1); headers[key.strip().lower()]=value.strip()
        if method == "CONNECT": host,_,port_text=target.rpartition(":"); port=int(port_text or 443)
        else:
            parsed=urllib.parse.urlsplit(target)
            if parsed.scheme not in {"http","https"}: return
            host=parsed.hostname or ""; port=parsed.port or (443 if parsed.scheme=="https" else 80)
        addresses=allowed_address(host,self.server.prime_mode)
        if not addresses or port < 1 or port > 65535:
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"); return
        try: upstream=socket.create_connection((addresses[0],port),timeout=20)
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n"); return
        if method == "CONNECT": self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            path=urllib.parse.urlsplit(target).path or "/"; query=urllib.parse.urlsplit(target).query
            if query: path += "?"+query
            upstream.sendall(f"{method} {path} {version}\r\nHost: {host}\r\nConnection: close\r\n".encode())
            for key,value in headers.items():
                if key not in {"host","connection","proxy-connection","proxy-authorization"}: upstream.sendall(f"{key}: {value}\r\n".encode("iso-8859-1"))
            upstream.sendall(b"\r\n")
            content_length=int(headers.get("content-length","0"))
            if content_length:
                if content_length > 32 * 1024 * 1024: return
                upstream.sendall(self.rfile.read(content_length))
        sockets=[self.connection,upstream]
        while True:
            readable,_,_=select.select(sockets,[],[],300)
            if not readable: break
            for source in readable:
                data=source.recv(65536)
                if not data: return
                (upstream if source is self.connection else self.connection).sendall(data)

class ProxyServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    def __init__(self,path,mode): self.prime_mode=mode; super().__init__(path,ProxyHandler)

def main():
    users = [value for value in os.environ.get("PRIME_GATEWAY_USERS", "dbyte").split(",") if value]
    servers=[]; active=set()
    def activate(user):
      if user in active or not container_user(user): return
      active.add(user)
      for mode in ("restricted","internet","lan","full"):
        directory=ROOT/"gateway"/user/mode; directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        sock=directory/"model.sock"; sock.unlink(missing_ok=True)
        server=Server(str(sock), user); os.chmod(sock,0o600); servers.append(server)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        if mode in {"internet","lan"}:
            proxy_sock=directory/"network.sock"; proxy_sock.unlink(missing_ok=True)
            proxy=ProxyServer(str(proxy_sock),mode); os.chmod(proxy_sock,0o600); servers.append(proxy)
            threading.Thread(target=proxy.serve_forever,daemon=True).start()
    def container_user(value):
        import re
        return bool(re.fullmatch(r"[A-Za-z0-9_.-]{2,32}",str(value)))
    while True:
        discovered=set(users)
        user_root=ROOT/"users"
        if user_root.is_dir(): discovered.update(p.name for p in user_root.iterdir() if p.is_dir())
        for user in discovered: activate(user)
        time.sleep(1)
if __name__ == "__main__": main()
