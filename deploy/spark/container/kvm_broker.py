#!/usr/bin/env python3
"""Owner-scoped, long-lived HTML5 KVM sessions in dedicated OpenShell sandboxes.

The owner's LAN gateway volume exposes this broker to authorized LAN and Full
network-operations tasks. Browser state stays in an isolated sandbox; this
host process holds no BMC credentials.
"""

from __future__ import annotations

import json
import base64
import os
import re
import signal
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, unquote

import openshell_runner
import task_common
from console_feed import ConsoleFeed


ROOT = Path("/var/lib/prime-runner")
COMMON = ["/usr/bin/openshell", "--gateway", "spark-local"]
LIFETIME = 8 * 3600
IDLE = 45 * 60
MAX_SESSIONS = 2
INPUT_ACTIONS = {"fill", "click", "key", "type_text", "focus_console"}
WORKER_ACTIONS = {"status", "pages", "select_page", "select_frame", "inspect", "capture", *INPUT_ACTIONS}


def validate_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("BMC URL must be HTTP(S) without credentials or fragments")
    parsed = urlparse(value)
    if (
            parsed.scheme not in {"http", "https"} or not parsed.netloc or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("BMC URL must be HTTP(S) without credentials or fragments")
    if unquote(parsed.path).lower().rstrip("/").startswith("/redfish"):
        raise ValueError("Redfish is an API, not a KVM console. Use RedfishClient for API calls, or the BMC web UI URL for KVM.")
    return value


def same_bmc_target(existing: str, requested: str) -> bool:
    old, new = urlparse(existing), urlparse(requested)
    if old.hostname != new.hostname:
        return False
    old_port = old.port or (443 if old.scheme == "https" else 80)
    new_port = new.port or (443 if new.scheme == "https" else 80)
    return ((old.scheme, old_port) == (new.scheme, new_port) or
            (old.scheme == "https" and old_port == 443 and new.scheme == "http" and new_port == 80))


def sandbox_spec(owner: str, session_id: str, manifest: Path = ROOT / "openshell-image-digests.json",
                 policy_root: Path = ROOT / "openshell-policies",
                 worker_root: Path = ROOT / "kvm") -> dict:
    if not task_common.SAFE_USER.fullmatch(owner) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
        raise ValueError("Invalid KVM sandbox owner or ID")
    image = openshell_runner.image_for_profile("network-operations", manifest)
    name = f"pk-{session_id[:16]}"
    policy_root.mkdir(parents=True, exist_ok=True)
    policy = policy_root / f"kvm-{session_id}.yaml"
    lines = [
        "version: 1", "filesystem_policy:", "  include_workdir: true",
        "  read_only:", "    - /usr", "    - /lib", "    - /proc", "    - /etc",
        "    - /opt/prime-kernel", "    - /run/prime-gateway",
        "  read_write:", "    - /tmp", "    - /dev/null", "    - /dev/urandom",
        "    - /dev/random", "    - /dev/shm", "    - /run/prime-kvm-worker",
        "landlock:", "  compatibility: hard_requirement", "network_policies: {}", "",
    ]
    temporary = policy.with_suffix(".tmp")
    temporary.write_text("\n".join(lines))
    os.chmod(temporary, 0o600)
    os.replace(temporary, policy)
    mounts = {"docker": {"mounts": [
        {"type": "volume", "source": f"prime-{owner}-gateway-lan",
         "target": "/run/prime-gateway", "read_only": True},
        {"type": "volume", "source": f"prime-{owner}-kvm",
         "target": "/run/prime-kvm-worker", "read_only": False},
    ]}}
    create = COMMON + ["sandbox", "create", "--name", name, "--from", image,
                       "--policy", str(policy), "--driver-config-json", json.dumps(mounts, separators=(",", ":")),
                       "--cpu", "2", "--memory", "2Gi", "--approval-mode", "manual",
                       "--label", f"prime.owner={owner}", "--label", "prime.kvm=true",
                       "--label", f"prime.kvm-session={session_id}",
                       "--detach", "--no-auto-providers", "--no-tty", "--", "/bin/sleep", "infinity"]
    worker_name = f"worker-{session_id}.sock"
    worker_socket = worker_root / owner / worker_name
    in_sandbox_socket = f"/run/prime-kvm-worker/{worker_name}"
    launch_code = (
        "import subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-m','bmc_html5_kvm','--server',sys.argv[1]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        "start_new_session=True,close_fds=True); print(p.pid)"
    )
    launch = COMMON + ["sandbox", "exec", "--name", name, "--no-tty", "--",
                       "/opt/prime-kernel/bin/python", "-c", launch_code, in_sandbox_socket]
    delete = COMMON + ["sandbox", "delete", name]
    return {"name": name, "policy": policy, "create": create, "launch": launch,
            "workerSocket": worker_socket, "delete": delete}


def _worker_call(path: Path, action: str, timeout: int = 55, **values) -> dict:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(timeout)
    try:
        connection.connect(str(path))
        with connection.makefile("rwb", buffering=0) as stream:
            stream.write(json.dumps({"action": action, **values}, separators=(",", ":")).encode() + b"\n")
            raw = stream.readline(3_500_001)
    finally:
        connection.close()
    if not raw or len(raw) > 3_500_000:
        raise RuntimeError("KVM worker disconnected or exceeded response bound")
    response = json.loads(raw)
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error", "KVM worker failed"))[:400])
    return response.get("result") or {}


@dataclass
class Session:
    session_id: str
    target: str
    spec: dict
    ignore_https_errors: bool = False
    created: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)
    feed: object = None
    closed: bool = False

    def call(self, action: str, **values) -> dict:
        with self.lock:
            result = _worker_call(self.spec["workerSocket"], action, **values)
            self.last_used = time.monotonic()
            return result

    def close(self) -> None:
        with self.lock:
            self.closed = True
            if self.feed is not None:
                self.feed.close()
            try:
                _worker_call(self.spec["workerSocket"], "close", timeout=5)
            except (OSError, RuntimeError, TimeoutError):
                pass
        subprocess.run(self.spec["delete"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40, check=False)
        self.spec["workerSocket"].unlink(missing_ok=True)
        self.spec["policy"].unlink(missing_ok=True)


class KVMBroker:
    def __init__(self, owner: str, root: Path = ROOT):
        if not task_common.SAFE_USER.fullmatch(owner):
            raise ValueError("Invalid KVM owner")
        self.owner, self.root = owner, root
        self.socket_path = root / "gateway" / owner / "lan" / "kvm.sock"
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()
        self.stopping = threading.Event()

    def _new_session(self, url: str, ignore_https_errors: bool) -> dict:
        url = validate_url(url)
        with self.lock:
            for existing in self.sessions.values():
                if (same_bmc_target(existing.target, url) and
                        existing.ignore_https_errors == bool(ignore_https_errors)):
                    existing.last_used = time.monotonic()
                    return {"sessionId": existing.session_id, "target": existing.target,
                            "reused": True, "expiresInSeconds": max(0, int(LIFETIME - (time.monotonic() - existing.created)))}
            if len(self.sessions) >= MAX_SESSIONS:
                raise RuntimeError("KVM session capacity reached. Use KVMClient.list_sessions() and KVMClient.connect(sessionId) to reuse one; do not repeatedly create or close an active console without checking it.")
            session_id = uuid.uuid4().hex
            spec = sandbox_spec(self.owner, session_id, self.root / "openshell-image-digests.json",
                                self.root / "openshell-policies", self.root / "kvm")
            try:
                subprocess.run(spec["create"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               timeout=90, check=True, text=True)
                subprocess.run(spec["launch"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=30, check=True)
                deadline = time.monotonic() + 10
                while not spec["workerSocket"].is_socket() and time.monotonic() < deadline:
                    time.sleep(.1)
                if not spec["workerSocket"].is_socket():
                    raise RuntimeError("KVM worker socket did not become ready")
                session = Session(session_id, url, spec, bool(ignore_https_errors))
                opened = session.call("open", url=url, ignoreHttpsErrors=bool(ignore_https_errors))
                session.target = str(opened.get("url") or url)
                workspace = Path(os.environ.get('PRIME_RUNNER_WORKSPACE_ROOT', f'/home/{self.owner}/prime-agent/tasks')) / self.owner
                session.feed = ConsoleFeed('kvm', 'HTML5 KVM · ' + str(urlparse(url).hostname),
                                           root=workspace / '.prime-console', session_id=session_id)
                self.sessions[session_id] = session
            except BaseException:
                subprocess.run(spec["delete"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40, check=False)
                spec["workerSocket"].unlink(missing_ok=True)
                spec["policy"].unlink(missing_ok=True)
                raise
        return {"sessionId": session_id, "target": url, "expiresInSeconds": LIFETIME}

    def dispatch(self, request: dict) -> dict:
        action = request.get("action")
        if action == "create":
            return self._new_session(request["url"], request.get("ignoreHttpsErrors") is True)
        if action == "list":
            with self.lock:
                return {"sessions": [{"sessionId": s.session_id, "target": s.target,
                                       "ageSeconds": int(time.monotonic() - s.created)}
                                      for s in self.sessions.values()]}
        session_id = request.get("sessionId")
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Invalid KVM session ID")
        with self.lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise LookupError("KVM session is unavailable or expired")
        if action == "close":
            with self.lock:
                self.sessions.pop(session_id, None)
            session.close()
            return {}
        if action not in WORKER_ACTIONS:
            raise ValueError("Unsupported KVM action")
        if action in INPUT_ACTIONS and request.get("confirm") is not True:
            raise PermissionError("KVM input requires explicit confirmation")
        values = {key: value for key, value in request.items() if key not in {"action", "sessionId"}}
        return session.call(action, **values)

    def expire(self) -> None:
        now = time.monotonic()
        with self.lock:
            expired = [key for key, s in self.sessions.items()
                       if now - s.created >= LIFETIME or now - s.last_used >= IDLE]
            sessions = [self.sessions.pop(key) for key in expired]
        for session in sessions:
            session.close()

    def observe(self) -> None:
        """Read-only sampling never extends agent idle time or sends input."""
        while not self.stopping.wait(1):
            with self.lock:
                sessions = list(self.sessions.values())
            for session in sessions:
                feed = session.feed
                if feed is None:
                    continue
                if not feed.watched():
                    feed.update()
                    continue
                if not session.lock.acquire(blocking=False):
                    feed.update(state='busy')
                    continue
                try:
                    if session.closed:
                        continue
                    frame = _worker_call(session.spec['workerSocket'], 'capture', timeout=3, format='jpeg', viewer=True)
                    feed.update(image=base64.b64decode(frame['jpeg'], validate=True))
                except (OSError, ValueError, KeyError, RuntimeError, TimeoutError):
                    feed.update(state='busy')
                finally:
                    session.lock.release()

    def _client(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(65)
            with connection.makefile("rwb", buffering=0) as stream:
                raw = stream.readline(16_385)
                if not raw or len(raw) > 16_384:
                    raise ValueError("KVM request exceeds limit")
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("KVM request must be an object")
                try:
                    result = self.dispatch(request)
                    response = {"ok": True, "result": result}
                except (KeyError, ValueError, PermissionError, LookupError, RuntimeError, TimeoutError) as error:
                    response = {"ok": False, "error": str(error)[:300]}
                stream.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            connection.close()

    def _cleanup_stale(self) -> None:
        # OpenShell 0.1 wraps results in a paged object. Read the inventory
        # before deleting anything so removals cannot shift later pages.
        rows, token, seen = [], "", set()
        while True:
            command = COMMON + ["sandbox", "list", "--page-size", "200", "--output", "json"]
            if token:
                command.extend(["--page-token", token])
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
            payload = json.loads(result.stdout)
            page = payload if isinstance(payload, list) else payload.get("sandboxes") if isinstance(payload, dict) else None
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                raise RuntimeError("OpenShell returned an invalid KVM sandbox inventory")
            rows.extend(page)
            token = payload.get("next_page_token", "") if isinstance(payload, dict) else ""
            if not token:
                break
            if not isinstance(token, str) or token in seen or len(seen) >= 100:
                raise RuntimeError("OpenShell KVM sandbox inventory pagination did not finish")
            seen.add(token)
        for row in rows:
            labels = row.get("labels") or {}
            if labels.get("prime.kvm") == "true" and labels.get("prime.owner") == self.owner:
                name = row.get("name", "")
                if re.fullmatch(r"pk-[a-f0-9]{16}", name):
                    subprocess.run(COMMON + ["sandbox", "delete", name],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=40, check=False)
                    session_id = labels.get("prime.kvm-session", "")
                    if re.fullmatch(r"[a-f0-9]{32}", session_id):
                        (self.root / "openshell-policies" / f"kvm-{session_id}.yaml").unlink(missing_ok=True)
        for path in (self.root / "kvm" / self.owner).glob("worker-*.sock"):
            if re.fullmatch(r"worker-[a-f0-9]{32}\.sock", path.name) and path.is_socket():
                path.unlink()

    def serve(self) -> None:
        self._cleanup_stale()  # Old workers cannot be reattached after a broker restart.
        if self.socket_path.exists():
            if not self.socket_path.is_socket():
                raise RuntimeError("KVM socket path is occupied by a non-socket")
            self.socket_path.unlink()
        previous_umask = os.umask(0o077)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(8)
            server.settimeout(1)
        finally:
            os.umask(previous_umask)

        def stop(_signal, _frame):
            self.stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        observer = threading.Thread(target=self.observe, daemon=True)
        observer.start()
        try:
            while not self.stopping.is_set():
                self.expire()
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._client, args=(connection,), daemon=True).start()
        finally:
            self.stopping.set()
            observer.join(timeout=4)
            server.close()
            with self.lock:
                sessions = list(self.sessions.values())
                self.sessions.clear()
            for session in sessions:
                session.close()
            self.socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    owner = os.environ.get("PRIME_WEB_OWNER", "")
    KVMBroker(owner).serve()
