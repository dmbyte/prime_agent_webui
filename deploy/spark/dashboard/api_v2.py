#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.parse
import uuid
import zipfile
import tarfile
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prime_dashboard_legacy", Path(__file__).with_name("api.py"))
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)

META = legacy.HOME / ".prime/agent/webui-metadata.json"
LEDGER = legacy.HOME / ".prime/agent/webui-usage-ledger.jsonl"
TASK_LOGS = legacy.HOME / ".prime/agent/webui-task-logs"
UPDATE_STATUS_DIR = legacy.HOME / ".prime/agent/update-status"
USER_TRASH = legacy.HOME / ".prime/agent/user-trash"
MAX_NATIVE_TASKS = 4
MAX_TASK_SECONDS = 30 * 60
TASKS = {}
TASK_LOCK = threading.Lock()
META_LOCK = threading.Lock()

NEMOTRON_ROUTE = ("spark-nemotron", "nemotron-3.5-lightning")
QWEN_ROUTE = ("spark-qwen", "qwen3.6-35b-a3b")
QWEN_SPECIALIST_PATTERNS = (
    r"\b(image|photo|screenshot|diagram|chart|graph|png|jpe?g|webp|pdf)\b",
    r"\b(3d[ -]?print|cad|stl|step|mesh|slicer|printability|manufactur(?:e|ing)|clearance|enclosure|geometry|thermal|cfd)\b",
    r"\b(portfolio|stock|equity|earnings|valuation|day[ -]?trad(?:e|ing)|trade setup|technical analysis|options|risk[- ]adjusted|drawdown|correlation|position sizing|financial statement|balance sheet|cash flow)\b",
    r"\b(code review|security review|architecture review|independent review|second opinion|adversarial review|critique|refactor|debug)\b",
)


def model_details(provider, model):
    return next((row for row in legacy.model_catalog() if row["provider"] == provider and row["model"] == model), {})


def route_task(message, settings=None):
    settings = settings or legacy.settings_view()
    selected = (settings["provider"], settings["model"])
    enabled = set(settings.get("enabledModels") or [])
    qwen_enabled = "/".join(QWEN_ROUTE) in enabled
    value = str(message).casefold()
    explicit_qwen = bool(re.search(r"(?:\b(?:use|route|delegate|send)\b.{0,24}\bqwen\b|\bqwen\b.{0,24}\b(?:subagent|model)\b|/qwen\b)", value))
    explicit_nemotron = bool(re.search(r"(?:\b(?:use|route|keep)\b.{0,24}\bnemotron\b|/nemotron\b)", value))
    specialist = next((pattern for pattern in QWEN_SPECIALIST_PATTERNS if re.search(pattern, value)), None)
    if explicit_nemotron:
        provider, model = NEMOTRON_ROUTE
        return {"provider": provider, "model": model, "routingMode": "explicit", "routeReason": "User explicitly requested Nemotron."}
    if explicit_qwen:
        if qwen_enabled:
            provider, model = QWEN_ROUTE
            return {"provider": provider, "model": model, "routingMode": "explicit", "routeReason": "User explicitly requested Qwen."}
        return {"provider": selected[0], "model": selected[1], "routingMode": "fallback", "routeReason": "Qwen was requested but is disabled; using the selected default."}
    if selected == NEMOTRON_ROUTE and specialist:
        if qwen_enabled:
            provider, model = QWEN_ROUTE
            return {"provider": provider, "model": model, "routingMode": "automatic", "routeReason": "Qwen specialist route matched this task."}
        return {"provider": selected[0], "model": selected[1], "routingMode": "fallback", "routeReason": "A Qwen specialist route matched, but Qwen is disabled."}
    return {"provider": selected[0], "model": selected[1], "routingMode": "default", "routeReason": "Using the selected default model."}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def valid_id(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", str(value)))


def metadata():
    return legacy.read_json(META, {"conversations": {}, "retentionDays": 30})


def save_metadata(data):
    with META_LOCK:
        legacy.atomic_json(META, data)


def conversation_owner(session_id):
    rows = metadata().get("conversations", {})
    if session_id in rows:
        return rows[session_id].get("owner", "dbyte")
    try:
        return rows.get(legacy.session_path(session_id).stem, {}).get("owner", "dbyte")
    except ValueError:
        return "dbyte"


def require_conversation_owner(session_id, user):
    if conversation_owner(session_id) != user:
        raise ValueError("Conversation not found")


def usage_for_user(user):
    paths = []
    for row in legacy.session_catalog():
        if conversation_owner(row["id"]) != user:
            continue
        try:
            paths.append(legacy.session_path(row["id"]))
        except ValueError:
            pass
    return legacy.usage_summary(paths)


def conversation_catalog(query="", include_archived=False, user="dbyte"):
    rows = legacy.session_catalog()
    data = metadata().get("conversations", {})
    result = []
    query = query.casefold().strip()
    for row in rows:
        try:
            storage_id = legacy.session_path(row["id"]).stem
        except ValueError:
            storage_id = row["id"]
        extra = data.get(row["id"], data.get(storage_id, {}))
        if extra.get("owner", "dbyte") != user:
            continue
        row.update({"pinned": bool(extra.get("pinned")), "archived": bool(extra.get("archived"))})
        if extra.get("thinking"):
            row["thinking"] = extra["thinking"]
        if extra.get("routeProvider") == row.get("provider") and extra.get("routeModel") == row.get("model"):
            row.update({"routingMode": extra.get("routingMode"), "routeReason": extra.get("routeReason")})
        details = model_details(row.get("provider"), row.get("model"))
        row.update({"contextWindow": details.get("contextWindow"), "maxTokens": details.get("maxTokens")})
        if extra.get("title"):
            row["topic"] = str(extra["title"])[:96]
        if row["archived"] and not include_archived:
            continue
        if query and query not in f"{row['topic']} {row['id']} {row.get('model', '')}".casefold():
            continue
        result.append(row)
    pinned = [row for row in result if row["pinned"]]
    normal = [row for row in result if not row["pinned"]]
    pinned.sort(key=lambda row: legacy.parse_timestamp(row.get("modified")), reverse=True)
    normal.sort(key=lambda row: legacy.parse_timestamp(row.get("modified")), reverse=True)
    return pinned + normal


def message_text(parts):
    values = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") in {"text", "reasoning"} and part.get("text"):
            values.append(str(part["text"]))
    return "\n".join(values)


def conversation_messages(session_id, user="dbyte"):
    if not valid_id(session_id):
        raise ValueError("Invalid conversation identifier")
    require_conversation_owner(session_id, user)
    try:
        path = legacy.session_path(session_id)
    except ValueError as error:
        raise ValueError("Conversation not found") from error
    rows = []
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
                if entry.get("type") != "message":
                    continue
                message = entry.get("message") or {}
                role = str(message.get("role") or "")
                if role not in {"user", "assistant", "toolResult"}:
                    continue
                parts = message.get("content") or []
                text = message_text(parts)
                tools = [str(part.get("name") or part.get("toolName")) for part in parts if isinstance(part, dict) and part.get("type") == "toolCall"]
                if not text and not tools and role != "toolResult":
                    continue
                usage = message.get("usage") or {}
                rows.append({
                    "id": str(message.get("id") or entry.get("id") or uuid.uuid4().hex),
                    "role": "tool" if role == "toolResult" else role,
                    "text": text or (f"Completed {message.get('toolName', 'tool')}" if role == "toolResult" else ""),
                    "tools": tools,
                    "timestamp": message.get("timestamp") or entry.get("timestamp"),
                    "usage": {"input": usage.get("input", 0), "output": usage.get("output", 0), "cacheRead": usage.get("cacheRead", 0), "total": usage.get("totalTokens", 0)},
                })
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return rows[-400:]


def prime_env():
    env = os.environ.copy()
    env["PATH"] = f"{legacy.PRIME_BIN}:{env.get('PATH', '')}"
    return env


def task_snapshot(user=None):
    with TASK_LOCK:
        rows = []
        for task_id, task in TASKS.items():
            if user is not None and task.get("owner", "dbyte") != user:
                continue
            row = {key: value for key, value in task.items() if key not in {"process"}}
            if row.get("status") == "running":
                row["elapsedSeconds"] = round(time.time() - row["startedEpoch"], 1)
            rows.append(row)
        return sorted(rows, key=lambda row: row["started"], reverse=True)[:50]


def append_ledger(task, status, output=""):
    record = {"at": now_iso(), "taskId": task["id"], "owner": task.get("owner", "dbyte"), "sessionId": task.get("sessionId"), "provider": task.get("provider"), "model": task.get("model"), "status": status, "elapsedSeconds": round(time.time() - task["startedEpoch"], 2)}
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
            usage = value.get("usage") or (value.get("message") or {}).get("usage") or {}
            if usage:
                record["usage"] = {key: usage.get(key, 0) for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}
                record["cost"] = (usage.get("cost") or {}).get("total", 0)
                break
        except (json.JSONDecodeError, AttributeError):
            continue
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    os.chmod(LEDGER, 0o600)


def ledger_summary():
    rows = []
    try:
        with LEDGER.open(errors="replace") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return {"nativeRequests": len(rows), "recent": rows[-50:]}


def monitor_task(task_id, before):
    with TASK_LOCK:
        task = TASKS[task_id]
        process = task["process"]
    try:
        output, _ = process.communicate(timeout=MAX_TASK_SECONDS)
        status = "completed" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        output, _ = process.communicate(timeout=10)
        status = "timed_out"
    after = {path.stem for path in legacy.SESSIONS.glob("*.jsonl")}
    created = sorted(after - before, key=lambda value: (legacy.SESSIONS / f"{value}.jsonl").stat().st_mtime, reverse=True)
    with TASK_LOCK:
        task = TASKS[task_id]
        if not task.get("sessionId") and created:
            task["sessionId"] = created[0]
        task.update({"status": status, "finished": now_iso(), "elapsedSeconds": round(time.time() - task["startedEpoch"], 1)})
        log_path = TASK_LOGS / f"{task_id}.log"
        TASK_LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
        sanitized = re.sub(r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{20,}", "[REDACTED_API_KEY]", output[-200000:])
        sanitized = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+", r"\1[REDACTED]", sanitized)
        log_path.write_text(sanitized)
        os.chmod(log_path, 0o600)
        task["logAvailable"] = True
        append_ledger(task, status, output)
        if task.get("sessionId"):
            store_task_route(task)
    legacy.audit("native_task_finished", task=task_id, session=task.get("sessionId"), status=status)


def store_task_route(task):
    with META_LOCK:
        data = metadata()
        row = data.setdefault("conversations", {}).setdefault(task["sessionId"], {})
        row.update({
            "thinking": task.get("thinking"),
            "routeProvider": task.get("provider"),
            "routeModel": task.get("model"),
            "routingMode": task.get("routingMode"),
            "routeReason": task.get("routeReason"),
            "owner": task.get("owner", "dbyte"),
        })
        legacy.atomic_json(META, data)


def launch_task(message, session_id=None, fork=False, thinking=None, owner="dbyte"):
    message = str(message).strip()
    if not message or len(message) > 100000:
        raise ValueError("Message must contain between 1 and 100,000 characters")
    if session_id and not valid_id(session_id):
        raise ValueError("Invalid conversation identifier")
    if session_id:
        require_conversation_owner(session_id, owner)
    with TASK_LOCK:
        active = sum(1 for row in TASKS.values() if row["status"] == "running")
        if active >= MAX_NATIVE_TASKS:
            raise RuntimeError("Four native tasks are already running")
    settings = legacy.settings_view()
    if thinking is None and session_id:
        thinking = metadata().get("conversations", {}).get(session_id, {}).get("thinking")
    thinking = str(thinking or settings["thinking"])
    if thinking not in legacy.THINKING:
        raise ValueError("Unsupported thinking level")
    route = route_task(message, settings)
    details = model_details(route["provider"], route["model"])
    command = [str(legacy.PRIME_AGENT), "--cwd", str(legacy.HOME / "prime-dgx-agent"), "--mode", "json", "--print", "--provider", route["provider"], "--model", route["model"], "--thinking", thinking]
    if session_id:
        command.extend(["--fork" if fork else "--resume", session_id])
    command.extend(["--", message])
    before = {path.stem for path in legacy.SESSIONS.glob("*.jsonl")}
    task_id = uuid.uuid4().hex
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=legacy.HOME / "prime-dgx-agent", env=prime_env(), start_new_session=True)
    task = {"id": task_id, "sessionId": session_id if not fork else None, "owner": owner, "topic": legacy.safe_topic(message) or "Native task", **route, "thinking": thinking, "contextWindow": details.get("contextWindow"), "maxTokens": details.get("maxTokens"), "status": "running", "started": now_iso(), "startedEpoch": time.time(), "pid": process.pid, "process": process, "logAvailable": False}
    with TASK_LOCK:
        TASKS[task_id] = task
    if task.get("sessionId"):
        store_task_route(task)
    threading.Thread(target=monitor_task, args=(task_id, before), daemon=True).start()
    legacy.audit("native_task_started", task=task_id, session=session_id)
    return {key: value for key, value in task.items() if key != "process"}


def stop_native_task(task_id, owner="dbyte"):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task or task.get("owner", "dbyte") != owner or task["status"] != "running":
            raise ValueError("Task is no longer running")
        process = task["process"]
    os.killpg(process.pid, signal.SIGTERM)
    return {"stopping": True, "id": task_id}


def update_conversation(session_id, action, value=None, user="dbyte"):
    if not valid_id(session_id):
        raise ValueError("Conversation not found")
    legacy.session_path(session_id)
    require_conversation_owner(session_id, user)
    data = metadata()
    row = data.setdefault("conversations", {}).setdefault(session_id, {})
    if action == "pin":
        row["pinned"] = bool(value)
    elif action == "archive":
        row["archived"] = bool(value)
    elif action == "rename":
        title = re.sub(r"\s+", " ", str(value)).strip()[:96]
        if not title:
            raise ValueError("Title is required")
        subprocess.run([str(legacy.PRIME_AGENT), "rename", session_id, title, "--json"], timeout=12, check=False, capture_output=True, env=prime_env())
        row["title"] = title
    else:
        raise ValueError("Unsupported conversation action")
    save_metadata(data)
    return {"id": session_id, **row}


def upload_rows(user="dbyte"):
    rows = []
    if not legacy.UPLOADS.exists():
        return rows
    for path in legacy.UPLOADS.rglob("*"):
        try:
            if not path.is_file() or path.name.startswith("."):
                continue
            relative = path.relative_to(legacy.UPLOADS).as_posix()
            if metadata().get("files", {}).get(relative, {}).get("owner", "dbyte") != user:
                continue
            stat = path.stat()
            rows.append({"id": base64.urlsafe_b64encode(relative.encode()).decode().rstrip("="), "name": path.name.split("-", 1)[-1], "path": str(path), "sizeBytes": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"})
        except OSError:
            continue
    return sorted(rows, key=lambda row: row["modified"], reverse=True)


def upload_path(file_id, user=None):
    try:
        relative = base64.urlsafe_b64decode(file_id + "=" * (-len(file_id) % 4)).decode()
    except Exception as error:
        raise ValueError("Invalid file identifier") from error
    path = (legacy.UPLOADS / relative).resolve()
    if legacy.UPLOADS.resolve() not in path.parents or not path.is_file():
        raise ValueError("File not found")
    if user is not None and metadata().get("files", {}).get(relative, {}).get("owner", "dbyte") != user:
        raise ValueError("File not found")
    return path


def register_upload(path, owner):
    relative = Path(path).resolve().relative_to(legacy.UPLOADS.resolve()).as_posix()
    with META_LOCK:
        data = metadata()
        data.setdefault("files", {})[relative] = {"owner": owner, "createdAt": now_iso()}
        legacy.atomic_json(META, data)


def purge_user_cache(username):
    username = str(username)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", username) or username == "dbyte":
        raise ValueError("The initial administrator cache cannot be deleted here")
    with TASK_LOCK:
        if any(row.get("owner") == username and row.get("status") == "running" for row in TASKS.values()):
            raise RuntimeError("Stop the user's active tasks before deleting their cache")
    data = metadata()
    owned_sessions = [sid for sid, row in data.get("conversations", {}).items() if row.get("owner", "dbyte") == username]
    recovery = USER_TRASH / username / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    recovery.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(USER_TRASH, 0o700); os.chmod(USER_TRASH / username, 0o700)
    moved_sessions = moved_files = moved_logs = 0
    for session_id in owned_sessions:
        try:
            source = legacy.session_path(session_id)
            os.replace(source, recovery / source.name)
            moved_sessions += 1
        except ValueError:
            pass
    for relative, row in list(data.get("files", {}).items()):
        if row.get("owner", "dbyte") != username:
            continue
        source = (legacy.UPLOADS / relative).resolve()
        if source.is_file() and legacy.UPLOADS.resolve() in source.parents:
            target = recovery / "uploads" / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, target); moved_files += 1
        data["files"].pop(relative, None)
    for session_id in owned_sessions:
        data.get("conversations", {}).pop(session_id, None)
    with TASK_LOCK:
        owned_tasks = [task_id for task_id, row in TASKS.items() if row.get("owner", "dbyte") == username]
    for task_id in owned_tasks:
        source = TASK_LOGS / f"{task_id}.log"
        if source.is_file():
            target = recovery / "task-logs" / source.name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, target)
            moved_logs += 1
    save_metadata(data)
    legacy.audit("user_cache_deleted", user=username, sessions=moved_sessions, files=moved_files, logs=moved_logs)
    return {"user": username, "sessions": moved_sessions, "files": moved_files, "logs": moved_logs, "recoverable": True}


def inspect_archive(path):
    names = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist()[:2000]:
                names.append(info.filename)
                if info.is_dir():
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Archives containing symbolic links are not accepted")
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for info in archive.getmembers()[:2000]:
                names.append(info.name)
                if info.issym() or info.islnk():
                    raise ValueError("Archives containing links are not accepted")
    for name in names:
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Archive contains an unsafe path")
    return len(names)


def admin_status():
    services = {}
    for name in ("prime-auth", "prime-dashboard-api", "prime-web", "vllm-nemotron35", "vllm-qwen36"):
        result = subprocess.run(["systemctl", "--user", "is-active", name], capture_output=True, text=True, timeout=4)
        services[name] = result.stdout.strip() or "unknown"
    disk = shutil.disk_usage(legacy.HOME)
    return {"services": services, "updates": update_status(), "disk": {"total": disk.total, "used": disk.used, "free": disk.free}, "uploads": {"used": legacy.upload_storage_bytes(), "limit": legacy.MAX_UPLOAD_STORAGE_BYTES, "files": len(upload_rows()), "retentionDays": int(metadata().get("retentionDays", 30))}, "tasks": {"running": sum(1 for row in task_snapshot() if row["status"] == "running"), "limit": MAX_NATIVE_TASKS}, "certificate": {"authorityDownload": "/prime-webui-ca.crt", "trustedAfterInstall": True}, "generatedAt": now_iso()}


def update_status():
    rows = {}
    for kind, unit in (("agent", "prime-update-agent.service"), ("webui", "prime-update-webui.service")):
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=ActiveState,SubState"],
            capture_output=True, text=True, timeout=5,
        )
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        persisted = legacy.read_json(UPDATE_STATUS_DIR / f"{kind}.json", {})
        rows[kind] = {
            "active": values.get("ActiveState") in {"active", "activating"},
            "ran": bool(persisted.get("ran")),
            "state": values.get("SubState") or values.get("ActiveState") or "unknown",
            "result": persisted.get("result") or "unknown",
            "exitCode": int(persisted.get("exitCode") or 0),
            "updatedAt": persisted.get("updatedAt"),
        }
    return rows


def start_update(kind, confirmation):
    units = {"agent": "prime-update-agent.service", "webui": "prime-update-webui.service"}
    unit = units.get(str(kind))
    if not unit or confirmation != f"update-{kind}":
        raise ValueError("Explicit update confirmation is required")
    status = update_status().get(kind, {})
    if status.get("active"):
        raise RuntimeError("That update is already running")
    subprocess.run(["systemctl", "--user", "reset-failed", unit], capture_output=True, timeout=5, check=False)
    result = subprocess.run(["systemctl", "--user", "start", "--no-block", unit], capture_output=True, timeout=5)
    if result.returncode:
        raise RuntimeError("The update service could not be started")
    legacy.audit("update_started", kind=kind)
    return {"started": True, "kind": kind, "unit": unit}


def apply_retention(days):
    days = int(days)
    if not 1 <= days <= 365:
        raise ValueError("Retention must be between 1 and 365 days")
    data = metadata()
    data["retentionDays"] = days
    save_metadata(data)
    cutoff = time.time() - days * 86400
    removed = 0
    for row in upload_rows():
        path = upload_path(row["id"])
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    legacy.audit("upload_retention_applied", days=days, removed=removed)
    return {"retentionDays": days, "removed": removed}


def csrf_ok(headers):
    parsed = SimpleCookie()
    try:
        parsed.load(headers.get("Cookie", ""))
    except Exception:
        return False
    cookie = parsed.get("prime_csrf")
    header = headers.get("X-Prime-CSRF", "")
    return bool(cookie and header and hmac_compare(cookie.value, header))


def hmac_compare(left, right):
    import hmac
    return hmac.compare_digest(left, right)


class Handler(legacy.Handler):
    def request_user(self):
        value = self.headers.get("X-Prime-User", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", value):
            raise ValueError("Authenticated user is required")
        return value

    def require_admin(self):
        if self.headers.get("X-Prime-Role") != "admin":
            raise ValueError("Administrator access is required")
        return self.request_user()

    def send_bytes(self, status, body, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{re.sub(r"[^A-Za-z0-9_.-]", "_", filename)}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        try:
            if path == "/api/state":
                user = self.request_user()
                self.send_json(200, {"settings": legacy.settings_view(), "models": legacy.model_catalog(), "usage": usage_for_user(user), "requestLedger": {"nativeRequests": 0, "recent": []}, "sessions": conversation_catalog(query.get("q", [""])[0], query.get("archived", ["0"])[0] == "1", user), "telemetry": legacy.telemetry(), "nativeTasks": task_snapshot(user), "identity": {"user": user, "role": self.headers.get("X-Prime-Role", "user")}})
            elif path == "/api/conversations/messages":
                self.send_json(200, {"messages": conversation_messages(query.get("id", [""])[0], self.request_user())})
            elif path == "/api/conversations/export":
                session_id = query.get("id", [""])[0]
                rows = conversation_messages(session_id, self.request_user())
                text = "\n\n".join(f"## {row['role'].title()}\n\n{row['text']}" for row in rows).encode()
                self.send_bytes(200, text, "text/markdown; charset=utf-8", f"prime-{session_id}.md")
            elif path == "/api/tasks":
                self.send_json(200, {"tasks": task_snapshot(self.request_user()), "prime": {"tasks": []}})
            elif path == "/api/tasks/log":
                task_id = query.get("id", [""])[0]
                log = TASK_LOGS / f"{task_id}.log"
                task = next((row for row in task_snapshot(self.request_user()) if row["id"] == task_id), None)
                if not task or not re.fullmatch(r"[a-f0-9]{32}", task_id) or not log.is_file():
                    raise ValueError("Task log not found")
                self.send_bytes(200, log.read_bytes(), "text/plain; charset=utf-8", f"task-{task_id}.log")
            elif path == "/api/files":
                rows = upload_rows(self.request_user())
                self.send_json(200, {"files": rows, "usedBytes": sum(row["sizeBytes"] for row in rows), "limitBytes": legacy.MAX_UPLOAD_STORAGE_BYTES})
            elif path == "/api/files/content":
                file = upload_path(query.get("id", [""])[0], self.request_user())
                if file.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("Preview is limited to 10 MiB")
                guessed = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                safe_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain", "text/csv", "application/json"}
                content_type = guessed if guessed in safe_types else "application/octet-stream"
                self.send_bytes(200, file.read_bytes(), content_type)
            elif path == "/api/admin":
                self.require_admin()
                self.send_json(200, admin_status())
            else:
                super().do_GET()
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except OSError:
            self.send_json(500, {"error": "Request could not be completed"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        v2 = {"/api/settings", "/api/tasks/start", "/api/tasks/stop", "/api/conversations/update", "/api/conversations/delete", "/api/conversations/duplicate", "/api/files/delete", "/api/admin/restart", "/api/admin/retention", "/api/admin/update", "/api/admin/user-cache", "/api/files/upload"}
        if path not in v2:
            if not csrf_ok(self.headers):
                self.send_json(403, {"error": "CSRF validation failed"})
                return
            return super().do_POST()
        if self.headers.get("Origin") not in legacy.ALLOWED_ORIGINS or not csrf_ok(self.headers):
            self.send_json(403, {"error": "Request validation failed"})
            return
        try:
            user = self.request_user()
            length = int(self.headers.get("Content-Length", "0"))
            if path == "/api/files/upload":
                encoded_name = self.headers.get("X-Prime-Filename", "")
                if self.headers.get_content_type() != "application/octet-stream" or not encoded_name:
                    raise ValueError("Invalid upload request")
                result = legacy.save_upload(self.rfile, length, encoded_name)
                register_upload(result["path"], user)
                saved = Path(result["path"])
                try:
                    result["archiveEntries"] = inspect_archive(saved)
                except ValueError:
                    saved.unlink(missing_ok=True)
                    raise
                self.send_json(201, {"file": result})
                return
            if length < 2 or length > 110000 or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid JSON request")
            payload = json.loads(self.rfile.read(length))
            if path == "/api/settings":
                self.require_admin()
                self.send_json(200, {"settings": legacy.save_settings(payload)})
            elif path == "/api/tasks/start":
                self.send_json(202, {"task": launch_task(payload.get("message"), payload.get("sessionId"), thinking=payload.get("thinking"), owner=user)})
            elif path == "/api/tasks/stop":
                self.send_json(200, stop_native_task(str(payload.get("id", "")), user))
            elif path == "/api/conversations/update":
                self.send_json(200, update_conversation(str(payload.get("id", "")), str(payload.get("action", "")), payload.get("value"), user))
            elif path == "/api/conversations/delete":
                session_id = str(payload.get("id", ""))
                require_conversation_owner(session_id, user)
                self.send_json(200, legacy.delete_conversation(session_id))
            elif path == "/api/conversations/duplicate":
                self.send_json(202, {"task": launch_task("Continue this fork with a concise recap of the inherited context.", str(payload.get("id", "")), True, owner=user)})
            elif path == "/api/files/delete":
                file = upload_path(str(payload.get("id", "")), user)
                file.unlink()
                self.send_json(200, {"deleted": True})
            elif path == "/api/admin/restart":
                self.require_admin()
                service = str(payload.get("service", ""))
                allowed = {"prime-web", "vllm-nemotron35", "vllm-qwen36"}
                if service not in allowed or payload.get("confirm") != service:
                    raise ValueError("Explicit service confirmation is required")
                result = subprocess.run(["systemctl", "--user", "restart", service], timeout=30, capture_output=True)
                if result.returncode:
                    raise RuntimeError("Service restart failed")
                self.send_json(200, {"restarted": service})
            elif path == "/api/admin/retention":
                self.require_admin()
                if payload.get("confirm") != "delete-expired-uploads":
                    raise ValueError("Explicit retention confirmation is required")
                self.send_json(200, apply_retention(payload.get("days")))
            elif path == "/api/admin/update":
                self.require_admin()
                self.send_json(202, start_update(str(payload.get("kind", "")), payload.get("confirm")))
            elif path == "/api/admin/user-cache":
                self.require_admin()
                if payload.get("confirm") != f"delete-cache-{payload.get('username', '')}":
                    raise ValueError("Explicit cache deletion confirmation is required")
                self.send_json(200, purge_user_cache(payload.get("username")))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
        except RuntimeError as error:
            self.send_json(409, {"error": str(error)})


if __name__ == "__main__":
    legacy.BoundedThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
