#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import secrets
import stat
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SESSION_COOKIE = "prime_session"
CSRF_COOKIE = "prime_csrf"
ABSOLUTE_SECONDS = 12 * 60 * 60
IDLE_SECONDS = 30 * 60
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW = 10 * 60
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_BYTES = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()
KDF_LOCK = threading.Lock()


def cookies(header):
    parsed = SimpleCookie()
    try:
        parsed.load(header or "")
    except Exception:
        return {}
    return {key: morsel.value for key, morsel in parsed.items()}


def client_ip(headers, address):
    forwarded = headers.get("X-Real-IP", "")
    return forwarded if forwarded else address[0]


def session_for(header, touch=True):
    token = cookies(header).get(SESSION_COOKIE, "")
    now = time.time()
    with LOCK:
        row = SESSIONS.get(token)
        if not row or now > row["expires"] or now - row["seen"] > IDLE_SECONDS:
            SESSIONS.pop(token, None)
            return None
        if touch:
            row["seen"] = now
        return dict(row)


def permitted(ip):
    now = time.time()
    with LOCK:
        rows = [value for value in ATTEMPTS.get(ip, []) if now - value < ATTEMPT_WINDOW]
        ATTEMPTS[ip] = rows
        return len(rows) < MAX_ATTEMPTS


def failed(ip):
    with LOCK:
        ATTEMPTS.setdefault(ip, []).append(time.time())


def credential_path():
    configured = os.environ.get("PRIME_AUTH_CREDENTIAL", "")
    return Path(configured).expanduser() if configured else Path.home() / ".config/prime-agent/web-auth.json"


def load_credential():
    try:
        path = credential_path()
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("version") != 1:
            return None
        salt = base64.b64decode(value["salt"], validate=True)
        digest = base64.b64decode(value["hash"], validate=True)
        if len(salt) != 16 or len(digest) != SCRYPT_BYTES:
            return None
        if value.get("n") != SCRYPT_N or value.get("r") != SCRYPT_R or value.get("p") != SCRYPT_P:
            return None
        return {"username": str(value["username"]), "salt": salt, "hash": digest}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_users():
    path = credential_path()
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077: return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") == 2 and isinstance(raw.get("users"), dict): return raw
    except (OSError, ValueError, TypeError, json.JSONDecodeError): return None
    value = load_credential()
    if not value: return None
    return {"version": 2, "users": {value["username"]: {
        "role": "admin", "enabled": True, "createdAt": int(time.time()),
        "salt": raw["salt"], "hash": raw["hash"], "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
    }}}


def atomic_users(value):
    path = credential_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".web-auth.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass


def password_record(password):
    encoded = str(password).encode("utf-8")
    if len(str(password)) < 12 or len(encoded) > 1024:
        raise ValueError("Password must contain 12–1024 UTF-8 bytes")
    salt = secrets.token_bytes(16)
    with KDF_LOCK:
        digest = hashlib.scrypt(encoded, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_BYTES, maxmem=SCRYPT_MAXMEM)
    return {"salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(digest).decode(), "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}


def authenticate(username, password):
    store = load_users()
    raw = (store or {}).get("users", {}).get(username)
    if not raw or not raw.get("enabled", True):
        return False
    try:
        record = {"salt": base64.b64decode(raw["salt"], validate=True), "hash": base64.b64decode(raw["hash"], validate=True)}
    except (KeyError, ValueError, TypeError): return False
    encoded = password.encode("utf-8")
    if not encoded or len(encoded) > 1024:
        return False
    try:
        with KDF_LOCK:
            candidate = hashlib.scrypt(
                encoded,
                salt=record["salt"],
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
                dklen=SCRYPT_BYTES,
                maxmem=SCRYPT_MAXMEM,
            )
    except (OSError, ValueError):
        return False
    return hmac.compare_digest(candidate, record["hash"])


def session_admin(header):
    row = session_for(header)
    return row if row and row.get("role") == "admin" else None


def csrf_valid(headers, row):
    supplied = headers.get("X-Prime-CSRF", "")
    return bool(supplied and row and hmac.compare_digest(supplied, row.get("csrf", "")))


def user_rows():
    store = load_users() or {"users": {}}
    return [{"username": name, "role": row.get("role", "user"), "enabled": bool(row.get("enabled", True)), "createdAt": row.get("createdAt")} for name, row in sorted(store["users"].items())]


def manage_user(action, body, actor):
    username = str(body.get("username", "")).strip()
    if not __import__("re").fullmatch(r"[A-Za-z0-9_.-]{2,32}", username): raise ValueError("Invalid username")
    store = load_users() or {"version": 2, "users": {}}
    users = store["users"]
    if action == "add":
        if username in users: raise ValueError("User already exists")
        role = str(body.get("role", "user"));
        if role not in {"admin", "user"}: raise ValueError("Invalid role")
        users[username] = {**password_record(body.get("password", "")), "role": role, "enabled": True, "createdAt": int(time.time())}
    elif action == "reset":
        if username not in users: raise ValueError("User not found")
        users[username].update(password_record(body.get("password", "")))
    elif action == "change":
        if username not in users: raise ValueError("User not found")
        role = str(body.get("role", users[username].get("role", "user")))
        if role not in {"admin", "user"}: raise ValueError("Invalid role")
        if username == actor and role != "admin": raise ValueError("You cannot remove your own admin role")
        users[username]["role"] = role; users[username]["enabled"] = bool(body.get("enabled", True))
    elif action == "delete":
        if username == actor: raise ValueError("You cannot delete your own account")
        if username not in users: raise ValueError("User not found")
        del users[username]
    else: raise ValueError("Unsupported user action")
    if not any(row.get("role") == "admin" and row.get("enabled", True) for row in users.values()): raise ValueError("At least one enabled administrator is required")
    atomic_users(store)
    with LOCK:
        for token, row in list(SESSIONS.items()):
            if row.get("user") == username: SESSIONS.pop(token, None)
    return {"users": user_rows()}


class Handler(BaseHTTPRequestHandler):
    server_version = "PrimeAuth"
    sys_version = ""

    def json(self, status, value, cookies_out=()):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for value in cookies_out:
            self.send_header("Set-Cookie", value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/auth/check":
            row = session_for(self.headers.get("Cookie"))
            if row:
                self.send_response(204)
                self.send_header("X-Prime-User", row["user"])
                self.send_header("X-Prime-Role", row.get("role", "user"))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self.send_response(401)
                self.end_headers()
        elif self.path == "/auth/status":
            row = session_for(self.headers.get("Cookie"))
            self.json(200 if row else 401, {"authenticated": bool(row), "configured": bool(load_users()), "user": row and row["user"], "role": row and row.get("role"), "idleSeconds": IDLE_SECONDS})
        elif self.path == "/auth/admin/users":
            row = session_admin(self.headers.get("Cookie"))
            self.json(200, {"users": user_rows()}) if row else self.json(403, {"error": "Administrator access required"})
        else:
            self.json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/auth/logout":
            token = cookies(self.headers.get("Cookie")).get(SESSION_COOKIE, "")
            with LOCK:
                SESSIONS.pop(token, None)
            expired = "Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict"
            self.json(200, {"authenticated": False}, [f"{SESSION_COOKIE}=; {expired}", f"{CSRF_COOKIE}=; Path=/; Max-Age=0; Secure; SameSite=Strict"])
            return
        if self.path == "/auth/admin/users":
            row = session_admin(self.headers.get("Cookie"))
            if not row or not csrf_valid(self.headers, row):
                self.json(403, {"error": "Administrator validation failed"}); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 4096 or self.headers.get_content_type() != "application/json": raise ValueError("Invalid request")
                body = json.loads(self.rfile.read(length))
                self.json(200, manage_user(str(body.get("action", "")), body, row["user"]))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.json(400, {"error": str(error)})
            return
        if self.path != "/auth/login":
            self.json(404, {"error": "Not found"})
            return
        ip = client_ip(self.headers, self.client_address)
        if not permitted(ip):
            self.json(429, {"error": "Too many failed attempts. Try again later."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError
            body = json.loads(self.rfile.read(length))
            username = str(body.get("username", ""))
            password = str(body.get("password", ""))
        except (ValueError, TypeError, json.JSONDecodeError):
            self.json(400, {"error": "Invalid login request"})
            return
        okay = bool(password) and authenticate(username, password)
        password = ""
        if not okay:
            if not load_users():
                self.json(503, {"error": "WebUI password is not configured"})
                return
            failed(ip)
            time.sleep(1)
            self.json(401, {"error": "Invalid username or password"})
            return
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now = time.time()
        role = (load_users() or {}).get("users", {}).get(username, {}).get("role", "user")
        with LOCK:
            SESSIONS[token] = {"user": username, "role": role, "csrf": csrf, "created": now, "seen": now, "expires": now + ABSOLUTE_SECONDS}
            ATTEMPTS.pop(ip, None)
        session_cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age={ABSOLUTE_SECONDS}; Secure; HttpOnly; SameSite=Strict"
        csrf_cookie = f"{CSRF_COOKIE}={csrf}; Path=/; Max-Age={ABSOLUTE_SECONDS}; Secure; SameSite=Strict"
        self.json(200, {"authenticated": True, "user": username, "csrf": csrf}, [session_cookie, csrf_cookie])

    def log_message(self, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8764), Handler).serve_forever()
