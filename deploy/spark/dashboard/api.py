#!/usr/bin/env python3
import json
import glob
import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
SETTINGS = HOME / ".prime/agent/settings.json"
SESSIONS = HOME / ".prime/agent/sessions"
SESSION_TRASH = HOME / ".prime/agent/session-trash"
UPLOADS = HOME / "prime-dgx-agent/uploads"
MODEL_CONFIG = HOME / ".prime/agent/models.json"
OPENAI_ENV = HOME / ".config/prime-agent/openai.env"
PLANNED_MODELS = [{"provider": "openai", "model": "gpt-5.4"}]
ALLOWED_ORIGINS = {
    "https://172.16.253.231:8443",
    "https://127.0.0.1:8443",
    "https://localhost:8443",
    "https://spark-c562:8443",
}
MODELS = {
    "spark-nemotron": {"nemotron-3.5-lightning"},
    "spark-qwen": {"qwen3.6-35b-a3b"},
    "openai": {"gpt-5.4"},
}
THINKING = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
CPU_LOCK = threading.Lock()
CPU_SAMPLE = None
MODEL_LOCK = threading.Lock()
MODEL_CACHE = {"at": 0, "rows": []}
ACTIVITY_LOCK = threading.Lock()
ACTIVITY_CACHE = {"at": 0, "tasks": []}
UPLOAD_LOCK = threading.Lock()
DELETE_LOCK = threading.Lock()
PRIME_BIN = HOME / ".local/share/prime-agent-node/current/bin"
PRIME_AGENT = PRIME_BIN / "prime-agent"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_UPLOAD_STORAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_API_THREADS = 16
SOCKET_TIMEOUT_SECONDS = 120


def audit(event, **fields):
    record = {"event": event, "at": datetime.now(timezone.utc).isoformat(), **fields}
    print(json.dumps(record, separators=(",", ":"), default=str), file=sys.stderr, flush=True)


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def settings_view():
    data = read_json(SETTINGS, {})
    compaction = data.get("compaction", {})
    enabled_models = [str(value) for value in data.get("enabledModels", []) if isinstance(value, str)]
    return {
        "provider": data.get("defaultProvider", "spark-nemotron"),
        "model": data.get("defaultModel", "nemotron-3.5-lightning"),
        "thinking": data.get("defaultThinkingLevel", "low"),
        "reserveTokens": compaction.get("reserveTokens", 8192),
        "keepRecentTokens": compaction.get("keepRecentTokens", 12000),
        "enabledProviders": sorted({value.split("/", 1)[0] for value in enabled_models if "/" in value}),
    }


def model_catalog():
    catalog = []
    enabled_models = set(read_json(SETTINGS, {}).get("enabledModels") or [])
    data = read_json(MODEL_CONFIG, {})
    for provider, definition in (data.get("providers") or {}).items():
        models = definition.get("models") or []
        if isinstance(models, dict):
            models = [{"id": model_id} for model_id in models]
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = model.get("id") or model.get("model") or model.get("name")
            if model_id:
                catalog.append({"provider": provider, "model": str(model_id), "configured": True})
    catalog.extend(discovered_prime_models())
    existing = {f"{row['provider']}/{row['model']}" for row in catalog}
    for row in PLANNED_MODELS:
        if f"{row['provider']}/{row['model']}" not in existing:
            catalog.append({**row, "configured": openai_env_configured()})
    unique = {f"{row['provider']}/{row['model']}": row for row in catalog}
    for key, row in unique.items():
        row["enabled"] = key in enabled_models
    return sorted(unique.values(), key=lambda row: (row["provider"], row["model"]))


def discovered_prime_models():
    now = time.monotonic()
    with MODEL_LOCK:
        if now - MODEL_CACHE["at"] < 60:
            return list(MODEL_CACHE["rows"])
        rows = []
        try:
            env = os.environ.copy()
            env["PATH"] = f"{PRIME_BIN}:{env.get('PATH', '')}"
            result = subprocess.run(
                [str(PRIME_AGENT), "model", "list"], capture_output=True, text=True,
                timeout=12, check=True, env=env,
            )
            for line in (result.stdout + "\n" + result.stderr).splitlines():
                fields = line.split()
                if len(fields) < 2 or fields[0] in {"provider", "Warning:"}:
                    continue
                provider, model = fields[:2]
                if re.fullmatch(r"[A-Za-z0-9_.-]{2,64}", provider) and re.fullmatch(r"[A-Za-z0-9_.:-]{2,128}", model):
                    rows.append({"provider": provider, "model": model, "configured": True})
        except (OSError, subprocess.SubprocessError):
            rows = list(MODEL_CACHE["rows"])
        MODEL_CACHE.update({"at": now, "rows": rows})
        return list(rows)


def openai_env_configured():
    return os.environ.get("PRIME_OPENAI_CONFIGURED") == "1"


def save_settings(payload):
    provider = str(payload.get("provider", ""))
    model = str(payload.get("model", ""))
    thinking = str(payload.get("thinking", ""))
    reserve = int(payload.get("reserveTokens", 0))
    recent = int(payload.get("keepRecentTokens", 0))
    enabled_providers = payload.get("enabledProviders")
    catalog = [row for row in model_catalog() if row.get("configured")]
    available = {(row["provider"], row["model"]) for row in catalog}
    configured_providers = {row["provider"] for row in catalog}
    if not isinstance(enabled_providers, list) or not enabled_providers:
        raise ValueError("At least one provider must be enabled")
    enabled_providers = {str(value) for value in enabled_providers}
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{2,64}", value) for value in enabled_providers):
        raise ValueError("Invalid provider name")
    if not enabled_providers <= configured_providers:
        raise ValueError("Unknown or unconfigured provider")
    if (provider, model) not in available:
        raise ValueError("Unsupported provider/model pairing")
    if provider not in enabled_providers:
        raise ValueError("The default model provider must remain enabled")
    if thinking not in THINKING:
        raise ValueError("Unsupported thinking level")
    if not 2048 <= reserve <= 32768 or not 2048 <= recent <= 32768:
        raise ValueError("Compaction values must be between 2,048 and 32,768")
    if reserve + recent > 57344:
        raise ValueError("Reserved plus recent tokens must not exceed 57,344")
    data = read_json(SETTINGS, {})
    data["defaultProvider"] = provider
    data["defaultModel"] = model
    data["defaultThinkingLevel"] = thinking
    data["enabledModels"] = sorted(
        f"{row['provider']}/{row['model']}" for row in catalog
        if row["provider"] in enabled_providers
    )
    data.setdefault("compaction", {})["reserveTokens"] = reserve
    data["compaction"]["keepRecentTokens"] = recent
    atomic_json(SETTINGS, data)
    return settings_view()


def parse_timestamp(value):
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 10_000_000_000 else float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0
    return 0


def usage_summary():
    now = time.time()
    local_now = datetime.now().astimezone()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    windows = {"today": today_start, "30d": now - 30 * 86400, "all": 0}
    totals = {name: defaultdict(lambda: defaultdict(float)) for name in windows}
    latest_context = defaultdict(int)
    calls = 0
    usage_paths = list(SESSIONS.glob("*.jsonl")) + list(SESSION_TRASH.glob("*.jsonl"))
    for path in usage_paths:
        try:
            handle = path.open(errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                    message = entry.get("message") or {}
                    usage = message.get("usage")
                    provider = message.get("provider")
                    if message.get("role") != "assistant" or not usage or not provider:
                        continue
                    timestamp = parse_timestamp(entry.get("timestamp"))
                    model = message.get("model") or "unknown"
                    calls += 1
                    latest_context[f"{provider}/{model}"] = max(
                        latest_context[f"{provider}/{model}"], int(usage.get("totalTokens", 0))
                    )
                    for window, start in windows.items():
                        if timestamp < start:
                            continue
                        row = totals[window][f"{provider}/{model}"]
                        row["input"] += float(usage.get("input", 0))
                        row["output"] += float(usage.get("output", 0))
                        row["cacheRead"] += float(usage.get("cacheRead", 0))
                        row["cacheWrite"] += float(usage.get("cacheWrite", 0))
                        row["tokens"] += float(usage.get("totalTokens", 0))
                        row["cost"] += float((usage.get("cost") or {}).get("total", 0))
                        row["calls"] += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    result = {}
    for window, providers in totals.items():
        result[window] = {
            provider: {key: round(value, 8) for key, value in row.items()}
            for provider, row in sorted(providers.items())
        }
    return {
        "windows": result,
        "latestContext": latest_context,
        "sessionFiles": len(usage_paths),
        "recordedCalls": calls,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def session_catalog():
    sessions = []
    try:
        paths = sorted(SESSIONS.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        paths = []
    for path in paths:
        session_id = path.stem
        created = None
        provider = None
        model = None
        try:
            stat = path.stat()
            topic = None
            last_chat = None
            with path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if entry.get("type") == "session":
                        session_id = str(entry.get("id") or session_id)
                        created = entry.get("timestamp")
                    elif entry.get("type") == "model_change":
                        provider = entry.get("provider")
                        model = entry.get("modelId")
                    elif entry.get("type") == "message":
                        message = entry.get("message") or {}
                        last_chat = message.get("timestamp") or entry.get("timestamp") or last_chat
                        if topic is None and message.get("role") == "user":
                            parts = message.get("content") or []
                            text = " ".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("type") == "text")
                            topic = safe_topic(text)
            if (topic or "").strip().casefold() == "attach":
                continue
            sessions.append({
                "id": session_id,
                "topic": topic or "Untitled conversation",
                "created": created,
                "modified": last_chat or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "provider": provider,
                "model": model,
                "sizeBytes": stat.st_size,
            })
            if len(sessions) >= 40:
                break
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return sessions


def safe_topic(text):
    value = re.sub(r"\s+", " ", str(text)).strip()
    if not value:
        return None
    sensitive = re.compile(
        r"(?i)(api[ _-]?key|password|passphrase|client[ _-]?secret|authorization\s*:|bearer\s+|private[ _-]?key|sk-[a-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|[A-Za-z0-9+/]{40,}={0,2})"
    )
    if sensitive.search(value):
        return "Sensitive conversation"
    value = re.sub(r"[\x00-\x1f\x7f]", "", value)
    return value[:96].rstrip(" ,.;:-") + ("…" if len(value) > 96 else "")


def live_session_ids():
    env = os.environ.copy()
    env["PATH"] = f"{PRIME_BIN}:{env.get('PATH', '')}"
    try:
        result = subprocess.run(
            [str(PRIME_AGENT), "list", "--all", "--json"], capture_output=True,
            text=True, timeout=12, check=True, env=env,
        )
        raw = result.stdout[result.stdout.find("{"):]
        rows = json.loads(raw).get("sessions") or []
        return {
            str(row.get("sessionId") or row.get("id")) for row in rows
            if row.get("lifecycle") == "live"
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise RuntimeError("Could not verify whether the conversation is active") from error


def delete_conversation(session_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", session_id):
        raise ValueError("Invalid conversation identifier")
    with DELETE_LOCK:
        if session_id in live_session_ids():
            raise RuntimeError("Stop and close the active conversation before deleting it")
        source = SESSIONS / f"{session_id}.jsonl"
        if not source.is_file():
            raise ValueError("Conversation no longer exists")
        # Recheck immediately before the atomic move to reduce the resume/delete race.
        if session_id in live_session_ids():
            raise RuntimeError("Conversation became active; deletion was cancelled")
        SESSION_TRASH.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(SESSION_TRASH, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = SESSION_TRASH / f"{session_id}.{stamp}.jsonl"
        os.replace(source, target)
    audit("conversation_deleted", session=session_id)
    return {"deleted": True, "recoverable": True, "id": session_id}


def upload_storage_bytes():
    total = 0
    try:
        for path in UPLOADS.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        pass
    return total


def safe_upload_name(value):
    name = Path(urllib.parse.unquote(value)).name
    name = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "upload"
    suffix = Path(name).suffix[:20]
    stem = Path(name).stem[: max(1, 120 - len(suffix))]
    while len(f"{stem}{suffix}".encode("utf-8")) > 180 and len(stem) > 1:
        stem = stem[:-1]
    return f"{stem}{suffix}"


def _save_upload_locked(stream, content_length, encoded_name):
    if content_length < 1:
        raise ValueError("The selected file is empty")
    if content_length > MAX_UPLOAD_BYTES:
        raise ValueError("Files must be 100 MiB or smaller")
    if upload_storage_bytes() + content_length > MAX_UPLOAD_STORAGE_BYTES:
        raise ValueError("The private upload area has reached its 2 GiB limit")
    filename = safe_upload_name(encoded_name)
    day = datetime.now().astimezone().strftime("%Y-%m-%d")
    directory = UPLOADS / day
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(UPLOADS, 0o700)
    os.chmod(directory, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=directory)
    digest = hashlib.sha256()
    remaining = content_length
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Upload ended before the complete file arrived")
                handle.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        target = directory / f"{uuid.uuid4().hex[:12]}-{filename}"
        os.replace(temporary, target)
        return {
            "name": filename,
            "path": str(target),
            "sizeBytes": content_length,
            "sha256": digest.hexdigest(),
        }
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def save_upload(stream, content_length, encoded_name):
    # Hold the reservation for the complete stream so concurrent uploads cannot
    # all pass the aggregate quota check against the same starting size.
    with UPLOAD_LOCK:
        result = _save_upload_locked(stream, content_length, encoded_name)
    audit("file_uploaded", size=result["sizeBytes"], sha256=result["sha256"])
    return result


def background_activity():
    now = time.monotonic()
    with ACTIVITY_LOCK:
        if now - ACTIVITY_CACHE["at"] < 4:
            return {"tasks": list(ACTIVITY_CACHE["tasks"]), "generatedAt": datetime.now(timezone.utc).isoformat()}
        tasks = []
        try:
            env = os.environ.copy()
            env["PATH"] = f"{PRIME_BIN}:{env.get('PATH', '')}"
            result = subprocess.run(
                [str(PRIME_AGENT), "list", "--all", "--json"], capture_output=True,
                text=True, timeout=12, check=True, env=env,
            )
            raw = result.stdout[result.stdout.find("{"):]
            sessions = json.loads(raw).get("sessions") or []
            for session in sessions:
                if session.get("lifecycle") != "live" or session.get("activity") in {None, "idle"}:
                    continue
                session_id = str(session.get("sessionId") or session.get("id") or "")
                if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", session_id):
                    continue
                model = session.get("model") or {}
                topic, events = activity_events(session_id)
                tasks.append({
                    "id": session_id,
                    "topic": topic or "Background task",
                    "activity": str(session.get("activity") or "working"),
                    "model": f"{model.get('provider', '')}/{model.get('id', '')}".strip("/"),
                    "thinking": session.get("thinkingLevel"),
                    "messageCount": int(session.get("messageCount") or 0),
                    "modified": session.get("modified"),
                    "events": events,
                })
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
            tasks = list(ACTIVITY_CACHE["tasks"])
        ACTIVITY_CACHE.update({"at": now, "tasks": tasks})
        return {"tasks": list(tasks), "generatedAt": datetime.now(timezone.utc).isoformat()}


def stop_activity(session_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", session_id):
        raise ValueError("Invalid task identifier")
    active_ids = {task["id"] for task in background_activity()["tasks"]}
    if session_id not in active_ids:
        raise ValueError("Task is no longer active")
    env = os.environ.copy()
    env["PATH"] = f"{PRIME_BIN}:{env.get('PATH', '')}"
    try:
        subprocess.run(
            [str(PRIME_AGENT), "stop", session_id], capture_output=True, text=True,
            timeout=15, check=True, env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Prime did not confirm the stop in time") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError("Prime could not stop this task") from error
    with ACTIVITY_LOCK:
        ACTIVITY_CACHE.update({"at": 0, "tasks": []})
    audit("task_stopped", session=session_id)
    return {"stopped": True, "id": session_id}


def activity_events(session_id):
    topic = None
    events = deque(maxlen=14)
    previous_status = None
    try:
        with (SESSIONS / f"{session_id}.jsonl").open(errors="replace") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type")
                    message = entry.get("message") or {}
                    timestamp = message.get("timestamp") or entry.get("timestamp")
                    if entry_type == "message" and message.get("role") == "user":
                        if topic is None:
                            parts = message.get("content") or []
                            text = " ".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("type") == "text")
                            topic = safe_topic(text)
                        events.append({"at": timestamp, "kind": "input", "label": "Task input received"})
                    elif entry_type == "message" and message.get("role") == "assistant":
                        tools = [str(part.get("name") or part.get("toolName") or "tool") for part in (message.get("content") or []) if isinstance(part, dict) and part.get("type") == "toolCall"]
                        label = "Running " + ", ".join(tools[:3]) if tools else "Response updated"
                        events.append({"at": timestamp, "kind": "work", "label": label, "tokens": int((message.get("usage") or {}).get("totalTokens") or 0)})
                    elif entry_type == "message" and message.get("role") == "toolResult":
                        events.append({"at": timestamp, "kind": "tool", "label": f"Completed {message.get('toolName') or 'tool'}"})
                    elif entry_type == "model_change":
                        events.append({"at": timestamp, "kind": "model", "label": f"Model: {entry.get('provider', '')}/{entry.get('modelId', '')}".strip("/")})
                    elif entry_type == "agent_status":
                        status = str((entry.get("status") or {}).get("taskState") or "")
                        if status and status != previous_status:
                            events.append({"at": timestamp, "kind": "status", "label": status.replace("_", " ").title()})
                            previous_status = status
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    except OSError:
        pass
    return topic, list(events)


def cpu_percent():
    global CPU_SAMPLE
    try:
        fields = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        total = sum(fields)
    except (OSError, ValueError, IndexError):
        return None
    with CPU_LOCK:
        previous = CPU_SAMPLE
        CPU_SAMPLE = (idle, total)
    if not previous or total <= previous[1]:
        return None
    return round(100 * (1 - (idle - previous[0]) / (total - previous[1])), 1)


def max_temperature(pattern, required_type=None):
    values = []
    for name in glob.glob(pattern):
        path = Path(name)
        try:
            if required_type:
                sensor_type = path.parent.joinpath("name").read_text().strip().lower()
                if required_type not in sensor_type:
                    continue
            value = float(path.read_text().strip())
            values.append(value / 1000 if value > 1000 else value)
        except (OSError, ValueError):
            continue
    return round(max(values), 1) if values else None


def telemetry():
    memory_percent = memory_used = memory_total = None
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            meminfo[key] = int(value.split()[0]) * 1024
        memory_total = meminfo["MemTotal"]
        memory_used = memory_total - meminfo["MemAvailable"]
        memory_percent = round(memory_used / memory_total * 100, 1)
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        pass
    gpu_percent = gpu_temp = power_watts = None
    try:
        result = subprocess.run(
            ["/usr/bin/nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=True,
        )
        values = [value.strip() for value in result.stdout.splitlines()[0].split(",")]
        parsed = [None if value in {"[N/A]", "N/A", ""} else round(float(value), 1) for value in values]
        gpu_percent, gpu_temp, power_watts = parsed
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    return {
        "cpuPercent": cpu_percent(),
        "gpuPercent": gpu_percent,
        "memoryPercent": memory_percent,
        "memoryUsedBytes": memory_used,
        "memoryTotalBytes": memory_total,
        "cpuTempC": max_temperature("/sys/class/thermal/thermal_zone*/temp"),
        "gpuTempC": gpu_temp,
        "systemTempC": max_temperature("/sys/class/hwmon/hwmon*/temp*_input", "nvme"),
        "powerWatts": power_watts,
        "sources": {"cpuTemp": "ACPI thermal max", "systemTemp": "NVMe sensor max", "power": "GPU board"},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PrimeDashboard"
    sys_version = ""

    def setup(self):
        self.request.settimeout(SOCKET_TIMEOUT_SECONDS)
        super().setup()

    def send_json(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/api/state":
            self.send_json(200, {"settings": settings_view(), "models": model_catalog(), "usage": usage_summary(), "sessions": session_catalog(), "telemetry": telemetry()})
        elif self.path == "/api/telemetry":
            self.send_json(200, {"telemetry": telemetry()})
        elif self.path == "/api/activity":
            self.send_json(200, background_activity())
        elif self.path == "/api/health":
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        allowed = {"/api/settings", "/api/activity/stop", "/api/conversations/delete", "/api/files/upload"}
        if self.path not in allowed:
            self.send_json(404, {"error": "Not found"})
            return
        if self.headers.get("Origin") not in ALLOWED_ORIGINS or self.headers.get("X-Prime-Dashboard") != "1":
            self.send_json(403, {"error": "Origin rejected"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path == "/api/files/upload":
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Upload content type must be application/octet-stream")
                encoded_name = self.headers.get("X-Prime-Filename", "")
                if not encoded_name or len(encoded_name) > 512:
                    raise ValueError("A valid filename is required")
                self.send_json(201, {"file": save_upload(self.rfile, length, encoded_name)})
                return
            if length < 1 or length > 8192:
                raise ValueError("JSON request must be between 1 and 8,192 bytes")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Request content type must be application/json")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/activity/stop":
                self.send_json(200, stop_activity(str(payload.get("id", ""))))
            elif self.path == "/api/conversations/delete":
                self.send_json(200, delete_conversation(str(payload.get("id", ""))))
            else:
                self.send_json(200, {"settings": save_settings(payload)})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            audit("request_rejected", path=self.path, reason=str(error), client=self.client_address[0])
            self.send_json(400, {"error": str(error)})
        except RuntimeError as error:
            audit("request_conflict", path=self.path, reason=str(error), client=self.client_address[0])
            self.send_json(409, {"error": str(error)})
        except (OSError, socket.timeout) as error:
            audit("request_failed", path=self.path, reason=type(error).__name__, client=self.client_address[0])
            self.send_json(500, {"error": "Request could not be completed"})

    def log_message(self, format, *args):
        return


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, server_address, handler):
        self._slots = threading.BoundedSemaphore(MAX_API_THREADS)
        super().__init__(server_address, handler)

    def process_request(self, request, client_address):
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


if __name__ == "__main__":
    BoundedThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
