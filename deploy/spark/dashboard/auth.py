#!/usr/bin/env python3
import hmac
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import PAM

SESSION_COOKIE = "prime_session"
CSRF_COOKIE = "prime_csrf"
ABSOLUTE_SECONDS = 12 * 60 * 60
IDLE_SECONDS = 30 * 60
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW = 10 * 60
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()


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


def pam_authenticate(username, password):
    def conversation(_auth, questions, _data):
        answers = []
        for _question, prompt_type in questions:
            if prompt_type == PAM.PAM_PROMPT_ECHO_ON:
                answers.append((username, 0))
            elif prompt_type == PAM.PAM_PROMPT_ECHO_OFF:
                answers.append((password, 0))
            else:
                answers.append(("", 0))
        return answers
    auth = PAM.pam()
    auth.start("prime-agent-session")
    auth.set_item(PAM.PAM_USER, username)
    auth.set_item(PAM.PAM_CONV, conversation)
    try:
        auth.authenticate()
        auth.acct_mgmt()
        return True
    except PAM.error:
        return False


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
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self.send_response(401)
                self.end_headers()
        elif self.path == "/auth/status":
            row = session_for(self.headers.get("Cookie"))
            self.json(200 if row else 401, {"authenticated": bool(row), "user": row and row["user"], "idleSeconds": IDLE_SECONDS})
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
        allowed_user = os.environ.get("PRIME_AUTH_USER", "dbyte")
        okay = hmac.compare_digest(username, allowed_user) and bool(password)
        if okay:
            okay = pam_authenticate(username, password)
        password = ""
        if not okay:
            failed(ip)
            time.sleep(1)
            self.json(401, {"error": "Invalid username or password"})
            return
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now = time.time()
        with LOCK:
            SESSIONS[token] = {"user": username, "created": now, "seen": now, "expires": now + ABSOLUTE_SECONDS}
            ATTEMPTS.pop(ip, None)
        session_cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age={ABSOLUTE_SECONDS}; Secure; HttpOnly; SameSite=Strict"
        csrf_cookie = f"{CSRF_COOKIE}={csrf}; Path=/; Max-Age={ABSOLUTE_SECONDS}; Secure; SameSite=Strict"
        self.json(200, {"authenticated": True, "user": username, "csrf": csrf}, [session_cookie, csrf_cookie])

    def log_message(self, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8764), Handler).serve_forever()
