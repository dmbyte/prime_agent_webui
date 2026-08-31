#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import select
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

POLICY_SPEC = importlib.util.spec_from_file_location("prime_task_policy", Path(__file__).with_name("task_policy.py"))
task_policy = importlib.util.module_from_spec(POLICY_SPEC)
POLICY_SPEC.loader.exec_module(task_policy)

RUNNER_SPEC = importlib.util.spec_from_file_location("prime_container_runner", Path(__file__).with_name("container_runner.py"))
container_runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(container_runner)

META = legacy.HOME / ".prime/agent/webui-metadata.json"
ROUTING_RULES = legacy.HOME / ".prime/agent/webui-routing-rules.json"
LEDGER = legacy.HOME / ".prime/agent/webui-usage-ledger.jsonl"
TASK_LOGS = legacy.HOME / ".prime/agent/webui-task-logs"
UPDATE_STATUS_DIR = legacy.HOME / ".prime/agent/update-status"
USER_TRASH = legacy.HOME / ".prime/agent/user-trash"
MAX_NATIVE_TASKS = 4
MAX_TASK_SECONDS = 30 * 60
TASKS = {}
TASK_LOCK = threading.Lock()
SESSION_CACHE = {}
SESSION_CACHE_LOCK = threading.Lock()
META_LOCK = threading.Lock()
LEDGER_LOCK = threading.Lock()
EXECUTION_GRANTS = {}
EXECUTION_GRANT_LOCK = threading.Lock()
INITIAL_ADMIN = os.environ.get("PRIME_INITIAL_ADMIN", "dbyte")

NEMOTRON_ROUTE = ("spark-nemotron", "nemotron-3.5-lightning")
QWEN_ROUTE = ("spark-qwen", "qwen3.6-35b-a3b")
CODEX_ROUTE = ("openai-codex", "gpt-5.6-sol")
ROUTING_SCOPES = {"always", "nemotron-default"}


def default_routing_rules():
    return [
        {"id": "explicit-nemotron", "name": "Explicit Nemotron", "enabled": True, "priority": 1000, "scope": "always", "provider": NEMOTRON_ROUTE[0], "model": NEMOTRON_ROUTE[1], "triggers": ["use nemotron", "route to nemotron", "/nemotron"]},
        {"id": "explicit-codex", "name": "Explicit Codex / ChatGPT", "enabled": True, "priority": 990, "scope": "always", "provider": CODEX_ROUTE[0], "model": CODEX_ROUTE[1], "triggers": ["use codex", "ask codex", "route to codex", "delegate to codex", "use chatgpt", "ask chatgpt", "/codex", "/chatgpt"]},
        {"id": "explicit-qwen", "name": "Explicit Qwen", "enabled": True, "priority": 980, "scope": "always", "provider": QWEN_ROUTE[0], "model": QWEN_ROUTE[1], "triggers": ["use qwen", "ask qwen", "route to qwen", "delegate to qwen", "/qwen"]},
        {"id": "codex-architecture", "name": "Codex architecture specialist", "enabled": True, "priority": 700, "scope": "nemotron-default", "provider": CODEX_ROUTE[0], "model": CODEX_ROUTE[1], "triggers": ["software architecture", "application architecture", "system architecture", "architecture recommendation", "architect the", "architecture plan"]},
        {"id": "qwen-specialist", "name": "Qwen visual, CAD, finance, and engineering specialist", "enabled": True, "priority": 600, "scope": "nemotron-default", "provider": QWEN_ROUTE[0], "model": QWEN_ROUTE[1], "triggers": ["image", "photo", "screenshot", "diagram", "chart", "graph", "png", "jpeg", "webp", "pdf", "3d print", "cad", "stl", "step", "mesh", "slicer", "printability", "portfolio", "stock", "equity", "earnings", "valuation", "day trading", "trade setup", "technical analysis", "options", "code review", "security review", "independent review", "second opinion", "refactor", "debug"]},
    ]


def normalize_routing_rule(value, existing_id=None):
    if not isinstance(value, dict):
        raise ValueError("Routing rule is required")
    rule_id = str(existing_id or value.get("id") or uuid.uuid4().hex)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", rule_id):
        raise ValueError("Invalid routing rule identifier")
    name = re.sub(r"\s+", " ", str(value.get("name") or "")).strip()[:80]
    provider = str(value.get("provider") or "")
    model = str(value.get("model") or "")
    scope = str(value.get("scope") or "nemotron-default")
    try:
        priority = int(value.get("priority", 500))
    except (TypeError, ValueError) as error:
        raise ValueError("Priority must be a number") from error
    triggers = value.get("triggers")
    if not name or scope not in ROUTING_SCOPES or not 0 <= priority <= 1000:
        raise ValueError("Invalid routing rule name, scope, or priority")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,64}", provider) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", model):
        raise ValueError("Invalid routing target")
    available = {(row["provider"], row["model"]) for row in legacy.model_catalog() if row.get("configured")}
    if (provider, model) not in available:
        raise ValueError("Routing target is not a configured model")
    if not isinstance(triggers, list) or not 1 <= len(triggers) <= 30:
        raise ValueError("Provide between 1 and 30 trigger phrases")
    clean = []
    for trigger in triggers:
        trigger = re.sub(r"\s+", " ", str(trigger)).strip().casefold()
        if not 2 <= len(trigger) <= 80 or "\x00" in trigger:
            raise ValueError("Trigger phrases must contain 2 to 80 characters")
        if trigger not in clean:
            clean.append(trigger)
    return {"id": rule_id, "name": name, "enabled": bool(value.get("enabled", True)), "priority": priority, "scope": scope, "provider": provider, "model": model, "triggers": clean}


def routing_rules():
    value = legacy.read_json(ROUTING_RULES, None)
    rows = value.get("rules") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        return default_routing_rules()
    valid = []
    for row in rows[:50]:
        try:
            valid.append(normalize_routing_rule(row, row.get("id") if isinstance(row, dict) else None))
        except ValueError:
            continue
    return sorted(valid, key=lambda row: (-row["priority"], row["name"].casefold()))


def update_routing_rules(payload):
    action = str(payload.get("action") or "")
    if action == "reset":
        if payload.get("confirm") != "reset-routing-rules":
            raise ValueError("Exact reset confirmation is required")
        rows = default_routing_rules()
    else:
        rows = routing_rules()
        rule_id = str(payload.get("id") or "")
        if action == "delete":
            if payload.get("confirm") != f"delete-routing-rule-{rule_id}":
                raise ValueError("Exact delete confirmation is required")
            if not any(row["id"] == rule_id for row in rows):
                raise ValueError("Routing rule not found")
            rows = [row for row in rows if row["id"] != rule_id]
        elif action in {"add", "update"}:
            existing = next((row for row in rows if row["id"] == rule_id), None)
            if action == "update" and not existing:
                raise ValueError("Routing rule not found")
            rule = normalize_routing_rule(payload.get("rule"), rule_id if existing else None)
            rows = [row for row in rows if row["id"] != rule["id"]]
            rows.append(rule)
        else:
            raise ValueError("Unsupported routing rule action")
    rows = sorted(rows, key=lambda row: (-row["priority"], row["name"].casefold()))
    legacy.atomic_json(ROUTING_RULES, {"version": 1, "rules": rows})
    legacy.audit("routing_rules_updated", action=action, rule=payload.get("id") or "new")
    return {"rules": rows}

PROVIDER_AUTH = legacy.HOME / ".prime/agent/auth.json"
API_KEY_PROVIDERS = (
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ("openai", "OpenAI", "OPENAI_API_KEY"),
    ("prime-inference", "Prime Inference", "PRIME_API_KEY"),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY"),
    ("google", "Google Gemini", "GEMINI_API_KEY"),
    ("mistral", "Mistral", "MISTRAL_API_KEY"),
    ("groq", "Groq", "GROQ_API_KEY"),
    ("cerebras", "Cerebras", "CEREBRAS_API_KEY"),
    ("xai", "xAI", "XAI_API_KEY"),
    ("openrouter", "OpenRouter", "OPENROUTER_API_KEY"),
    ("vercel-ai-gateway", "Vercel AI Gateway", "AI_GATEWAY_API_KEY"),
    ("zai", "ZAI", "ZAI_API_KEY"),
    ("opencode", "OpenCode Zen", "OPENCODE_API_KEY"),
    ("opencode-go", "OpenCode Go", "OPENCODE_API_KEY"),
    ("huggingface", "Hugging Face", "HF_TOKEN"),
    ("fireworks", "Fireworks", "FIREWORKS_API_KEY"),
    ("kimi-coding", "Kimi For Coding", "KIMI_API_KEY"),
    ("moonshotai", "Moonshot AI", "MOONSHOT_API_KEY"),
    ("moonshotai-cn", "Moonshot AI China", "MOONSHOT_API_KEY"),
    ("minimax", "MiniMax", "MINIMAX_API_KEY"),
    ("minimax-cn", "MiniMax China", "MINIMAX_CN_API_KEY"),
    ("xiaomi", "Xiaomi MiMo", "XIAOMI_API_KEY"),
    ("xiaomi-token-plan-cn", "Xiaomi Token Plan China", "XIAOMI_TOKEN_PLAN_CN_API_KEY"),
    ("xiaomi-token-plan-ams", "Xiaomi Token Plan Amsterdam", "XIAOMI_TOKEN_PLAN_AMS_API_KEY"),
    ("xiaomi-token-plan-sgp", "Xiaomi Token Plan Singapore", "XIAOMI_TOKEN_PLAN_SGP_API_KEY"),
)
SUBSCRIPTION_PROVIDERS = (
    ("openai-codex", "ChatGPT Plus/Pro", "OpenAI Codex subscription login"),
    ("anthropic-subscription", "Claude Pro/Max", "Anthropic subscription login"),
    ("github-copilot", "GitHub Copilot", "GitHub or GitHub Enterprise login"),
)


def provider_catalog():
    auth = legacy.read_json(PROVIDER_AUTH, {})
    auth = auth if isinstance(auth, dict) else {}
    extra = legacy.read_json(legacy.PROVIDER_SETTINGS, {})
    extra = extra if isinstance(extra, dict) else {}
    rows = []
    for provider, name, env_name in API_KEY_PROVIDERS:
        configured = provider in auth or (provider == "openai" and legacy.openai_env_configured())
        rows.append({"id": provider, "name": name, "kind": "api-key", "description": f"Built-in Prime provider · {env_name}", "configured": configured, "fields": [{"id": "apiKey", "label": "API key", "secret": True, "required": not configured}]})
    for provider, name, description in SUBSCRIPTION_PROVIDERS:
        auth_key = "anthropic" if provider == "anthropic-subscription" else provider
        rows.append({"id": provider, "name": name, "kind": "subscription", "description": description, "configured": auth_key in auth, "fields": []})
    rows.extend([
        {"id": "azure-openai-responses", "name": "Azure OpenAI", "kind": "cloud", "description": "Azure OpenAI Responses API", "configured": "azure-openai-responses" in auth, "fields": [{"id": "apiKey", "label": "API key", "secret": True, "required": "azure-openai-responses" not in auth}, {"id": "baseUrl", "label": "Base URL", "placeholder": "https://resource.openai.azure.com", "required": True}, {"id": "apiVersion", "label": "API version", "placeholder": "Optional"}, {"id": "deploymentMap", "label": "Deployment name map", "placeholder": "gpt-4o=my-deployment"}]},
        {"id": "cloudflare-ai-gateway", "name": "Cloudflare AI Gateway", "kind": "cloud", "description": "Unified billing or stored BYOK gateway", "configured": "cloudflare-ai-gateway" in auth and bool(extra.get("CLOUDFLARE_ACCOUNT_ID") and extra.get("CLOUDFLARE_GATEWAY_ID")), "fields": [{"id": "apiKey", "label": "Cloudflare API key", "secret": True, "required": "cloudflare-ai-gateway" not in auth}, {"id": "accountId", "label": "Account ID", "required": True}, {"id": "gatewayId", "label": "Gateway ID", "required": True}]},
        {"id": "cloudflare-workers-ai", "name": "Cloudflare Workers AI", "kind": "cloud", "description": "Cloudflare Workers AI models", "configured": "cloudflare-workers-ai" in auth and bool(extra.get("CLOUDFLARE_ACCOUNT_ID")), "fields": [{"id": "apiKey", "label": "Cloudflare API key", "secret": True, "required": "cloudflare-workers-ai" not in auth}, {"id": "accountId", "label": "Account ID", "required": True}]},
        {"id": "amazon-bedrock", "name": "Amazon Bedrock", "kind": "cloud", "description": "AWS profile, IAM credentials, or bearer token", "configured": bool(extra.get("AWS_PROFILE") or extra.get("AWS_BEARER_TOKEN_BEDROCK") or (extra.get("AWS_ACCESS_KEY_ID") and extra.get("AWS_SECRET_ACCESS_KEY"))), "fields": [{"id": "profile", "label": "AWS profile", "placeholder": "Optional"}, {"id": "accessKey", "label": "Access key ID", "placeholder": "Optional"}, {"id": "secretKey", "label": "Secret access key", "secret": True}, {"id": "bearerToken", "label": "Bedrock bearer token", "secret": True}, {"id": "region", "label": "AWS region", "placeholder": "us-east-1"}]},
        {"id": "google-vertex", "name": "Google Vertex AI", "kind": "cloud", "description": "Application Default Credentials or service-account file", "configured": bool(extra.get("GOOGLE_CLOUD_PROJECT") and extra.get("GOOGLE_CLOUD_LOCATION")), "fields": [{"id": "project", "label": "Google Cloud project", "required": True}, {"id": "location", "label": "Google Cloud location", "placeholder": "us-central1", "required": True}, {"id": "credentialsPath", "label": "Service-account JSON path", "placeholder": "Optional existing path on Spark"}]},
        {"id": "custom-openai", "name": "Custom OpenAI-compatible", "kind": "custom", "description": "Ollama, LM Studio, vLLM, or another compatible endpoint", "configured": False, "fields": [{"id": "providerId", "label": "Provider ID", "required": True}, {"id": "baseUrl", "label": "Base URL", "placeholder": "http://127.0.0.1:8000/v1", "required": True}, {"id": "apiKey", "label": "API key", "secret": True}, {"id": "modelId", "label": "Model ID", "required": True}, {"id": "contextWindow", "label": "Context window", "placeholder": "32768", "required": True}, {"id": "maxTokens", "label": "Maximum output tokens", "placeholder": "8192", "required": True}]},
    ])
    return sorted(rows, key=lambda row: row["name"].casefold())


def configure_provider(payload):
    provider = str(payload.get("provider", ""))
    values = payload.get("values")
    if not isinstance(values, dict): raise ValueError("Provider values are required")
    definition = next((row for row in provider_catalog() if row["id"] == provider), None)
    if not definition or definition["kind"] == "subscription": raise ValueError("Use Prime interactive login for this provider")
    clean = {str(key): str(value).strip() for key, value in values.items() if isinstance(value, str)}
    for field in definition["fields"]:
        if field.get("required") and not clean.get(field["id"]): raise ValueError(f"{field['label']} is required")
    auth = legacy.read_json(PROVIDER_AUTH, {})
    auth = auth if isinstance(auth, dict) else {}
    settings = legacy.read_json(legacy.PROVIDER_SETTINGS, {})
    settings = settings if isinstance(settings, dict) else {}
    api_key = clean.get("apiKey")
    if api_key:
        if len(api_key) > 8192 or "\x00" in api_key: raise ValueError("Invalid API key")
        auth[provider] = {"type": "api_key", "key": api_key}
    if definition["kind"] == "api-key" and provider not in auth and not (provider == "openai" and legacy.openai_env_configured()): raise ValueError("API key is required")
    mappings = {
        "azure-openai-responses": {"baseUrl": "AZURE_OPENAI_BASE_URL", "apiVersion": "AZURE_OPENAI_API_VERSION", "deploymentMap": "AZURE_OPENAI_DEPLOYMENT_NAME_MAP"},
        "cloudflare-ai-gateway": {"accountId": "CLOUDFLARE_ACCOUNT_ID", "gatewayId": "CLOUDFLARE_GATEWAY_ID"},
        "cloudflare-workers-ai": {"accountId": "CLOUDFLARE_ACCOUNT_ID"},
        "amazon-bedrock": {"profile": "AWS_PROFILE", "accessKey": "AWS_ACCESS_KEY_ID", "secretKey": "AWS_SECRET_ACCESS_KEY", "bearerToken": "AWS_BEARER_TOKEN_BEDROCK", "region": "AWS_REGION"},
        "google-vertex": {"project": "GOOGLE_CLOUD_PROJECT", "location": "GOOGLE_CLOUD_LOCATION", "credentialsPath": "GOOGLE_APPLICATION_CREDENTIALS"},
    }
    for field, env_name in mappings.get(provider, {}).items():
        if clean.get(field): settings[env_name] = clean[field]
    if provider == "amazon-bedrock" and not (clean.get("profile") or clean.get("bearerToken") or (clean.get("accessKey") and clean.get("secretKey")) or definition["configured"]): raise ValueError("Choose an AWS profile, IAM key pair, or bearer token")
    if provider == "custom-openai":
        custom_id = clean.get("providerId", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,31}", custom_id) or custom_id in {row[0] for row in API_KEY_PROVIDERS}: raise ValueError("Custom provider ID must be unique lowercase letters, numbers, and hyphens")
        parsed = urllib.parse.urlparse(clean.get("baseUrl", ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname: raise ValueError("A valid HTTP(S) base URL is required")
        context = int(clean.get("contextWindow", 0)); maximum = int(clean.get("maxTokens", 0))
        if not 1024 <= context <= 2000000 or not 256 <= maximum <= context: raise ValueError("Invalid context or output token limit")
        env_name = f"PRIME_CUSTOM_{custom_id.upper().replace('-', '_')}_API_KEY"
        if api_key: settings[env_name] = api_key
        models = legacy.read_json(legacy.MODEL_CONFIG, {"providers": {}})
        models.setdefault("providers", {})[custom_id] = {"baseUrl": clean["baseUrl"], "api": "openai-completions", "apiKey": env_name if api_key else "EMPTY", "models": [{"id": clean["modelId"], "contextWindow": context, "maxTokens": maximum}]}
        legacy.atomic_json(legacy.MODEL_CONFIG, models)
        auth.pop(provider, None)
    legacy.atomic_json(PROVIDER_AUTH, auth)
    legacy.atomic_json(legacy.PROVIDER_SETTINGS, settings)
    legacy.MODEL_CACHE["at"] = 0
    legacy.audit("provider_configured", provider=provider, actor="admin")
    return {"provider": provider, "configured": True}


def model_details(provider, model):
    return next((row for row in legacy.model_catalog() if row["provider"] == provider and row["model"] == model), {})


def route_task(message, settings=None):
    settings = settings or legacy.settings_view()
    selected = (settings["provider"], settings["model"])
    enabled = set(settings.get("enabledModels") or [])
    value = str(message).casefold()
    for rule in routing_rules():
        if not rule["enabled"] or rule["scope"] == "nemotron-default" and selected != NEMOTRON_ROUTE:
            continue
        if not any(re.search(rf"(?<!\w){re.escape(trigger)}(?!\w)", value) for trigger in rule["triggers"]):
            continue
        target = (rule["provider"], rule["model"])
        mode = "explicit" if rule["scope"] == "always" else "automatic"
        if "/".join(target) in enabled:
            return {"provider": target[0], "model": target[1], "routingMode": mode, "routeReason": f'Routing rule “{rule["name"]}” matched.'}
        return {"provider": selected[0], "model": selected[1], "routingMode": "fallback", "routeReason": f'Routing rule “{rule["name"]}” matched, but its target is disabled.'}
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


def container_mode():
    return os.environ.get("PRIME_TASK_CONTAINER_IMAGE") == "1"


def session_root(user):
    if not container_mode():
        return legacy.SESSIONS
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", str(user)):
        raise ValueError("Invalid task owner")
    return Path(os.environ.get("PRIME_RUNNER_STORAGE", "/var/lib/prime-runner/users")) / user / "prime/agent/sessions"


def session_trash(user):
    return session_root(user).parent / "trash"


def conversation_owner(session_id):
    rows = metadata().get("conversations", {})
    if session_id in rows:
        return rows[session_id].get("owner", INITIAL_ADMIN)
    return INITIAL_ADMIN


def require_conversation_owner(session_id, user):
    if conversation_owner(session_id) != user:
        raise ValueError("Conversation not found")


def cached_session_catalog(user):
    """Keep state polling available while Prime temporarily protects its tree."""
    try:
        rows = legacy.session_catalog(session_root(user))
    except OSError:
        with SESSION_CACHE_LOCK:
            return [dict(row) for row in SESSION_CACHE.get(user, [])]
    rows = [dict(row) for row in rows]
    with SESSION_CACHE_LOCK:
        SESSION_CACHE[user] = [dict(row) for row in rows]
    return rows


def session_stems(user):
    """Return visible session stems without letting a stale ACL break requests."""
    try:
        return {path.stem for path in session_root(user).glob("*.jsonl")}
    except OSError:
        return set()


def usage_for_user(user):
    paths = []
    root = session_root(user)
    for row in cached_session_catalog(user):
        try:
            paths.append(legacy.session_path(row["id"], root))
        except ValueError:
            pass
    return legacy.usage_summary(paths)


def conversation_catalog(query="", include_archived=False, user=INITIAL_ADMIN):
    root = session_root(user)
    rows = cached_session_catalog(user)
    data = metadata().get("conversations", {})
    result = []
    query = query.casefold().strip()
    for row in rows:
        try:
            storage_id = legacy.session_path(row["id"], root).stem
        except ValueError:
            storage_id = row["id"]
        extra = data.get(row["id"], data.get(storage_id, {}))
        if extra.get("owner", INITIAL_ADMIN) != user:
            continue
        row.update({"pinned": bool(extra.get("pinned")), "archived": bool(extra.get("archived"))})
        if isinstance(extra.get("taskPolicy"), dict):
            row["taskPolicy"] = dict(extra["taskPolicy"])
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


def conversation_messages(session_id, user=INITIAL_ADMIN):
    if not valid_id(session_id):
        raise ValueError("Invalid conversation identifier")
    require_conversation_owner(session_id, user)
    try:
        path = legacy.session_path(session_id, session_root(user))
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
    env = legacy.provider_env()
    env["PATH"] = f"{legacy.PRIME_BIN}:{env.get('PATH', '')}"
    return env


def task_snapshot(user=None):
    with TASK_LOCK:
        rows = []
        for task_id, task in TASKS.items():
            if user is not None and task.get("owner", INITIAL_ADMIN) != user:
                continue
            row = {key: value for key, value in task.items() if key not in {"process", "usage", "rpcResponses", "agentEnded", "liveLogBytes"}}
            if row.get("status") == "running":
                row["elapsedSeconds"] = round(time.time() - row["startedEpoch"], 1)
            rows.append(row)
        return sorted(rows, key=lambda row: row["started"], reverse=True)[:50]


def append_ledger(task, status, output=""):
    record = {"at": now_iso(), "taskId": task["id"], "owner": task.get("owner", INITIAL_ADMIN), "sessionId": task.get("sessionId"), "provider": task.get("provider"), "model": task.get("model"), "status": status, "elapsedSeconds": round(time.time() - task["startedEpoch"], 2)}
    if task.get("usage"):
        usage = task["usage"]
        record["usage"] = {key: usage.get(key, 0) for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}
        record["cost"] = (usage.get("cost") or {}).get("total", 0)
    for line in reversed(output.splitlines()):
        if record.get("usage"):
            break
        try:
            value = json.loads(line)
            usage = value.get("usage") or (value.get("message") or {}).get("usage") or {}
            if usage:
                record["usage"] = {key: usage.get(key, 0) for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}
                record["cost"] = (usage.get("cost") or {}).get("total", 0)
                break
        except (json.JSONDecodeError, AttributeError):
            continue
    with LEDGER_LOCK:
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


def add_task_progress(task, label):
    label = re.sub(r"\s+", " ", str(label)).strip()[:160]
    if not label or (task.get("progressEvents") and task["progressEvents"][-1]["label"] == label):
        return
    task.setdefault("progressEvents", []).append({"at": now_iso(), "label": label})
    task["progressEvents"] = task["progressEvents"][-30:]
    task["progress"] = label


def sanitize_runtime_text(value, limit=1000):
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value or ""))
    value = re.sub(r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{20,}", "[REDACTED_API_KEY]", value)
    value = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def redact_runtime_value(value, key=""):
    normalized = re.sub(r"[^a-z]", "", str(key).lower())
    if normalized in {"thinking", "reasoning", "chainofthought", "thinkingsignature"}:
        return "[PRIVATE_REASONING]"
    if any(token in normalized for token in ("authorization", "apikey", "password", "secret", "refreshtoken", "accesstoken", "cookie")):
        return "[REDACTED]"
    if isinstance(value, dict):
        event_type = str(value.get("type") or "").lower()
        private_part = event_type in {"thinking", "reasoning"} or event_type.startswith("thinking_") or event_type.startswith("reasoning_")
        allowed_private = {"type", "contentindex"}
        return {str(child_key): ("[PRIVATE_REASONING]" if private_part and re.sub(r"[^a-z]", "", str(child_key).lower()) not in allowed_private else redact_runtime_value(child_value, child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [redact_runtime_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_runtime_text(value, 20000)
    return value


def safe_runtime_line(line):
    try:
        return json.dumps(redact_runtime_value(json.loads(line)), separators=(",", ":"), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, ValueError):
        return sanitize_runtime_text(line, 20000)


def append_live_log(task, line):
    line = safe_runtime_line(line)
    if not line:
        return
    size = len(line.encode("utf-8", errors="replace"))
    task.setdefault("liveLog", []).append({"at": now_iso(), "line": line})
    task["liveLogBytes"] = task.get("liveLogBytes", 0) + size
    while len(task["liveLog"]) > 5000 or task["liveLogBytes"] > 2 * 1024 * 1024:
        removed = task["liveLog"].pop(0)["line"]
        task["liveLogBytes"] -= len(removed.encode("utf-8", errors="replace"))


def add_runtime_event(task, kind, label, detail=""):
    row = {"at": now_iso(), "kind": str(kind)[:32], "label": sanitize_runtime_text(label, 200)}
    detail = sanitize_runtime_text(detail)
    if detail:
        row["detail"] = detail
    previous = (task.get("runtimeEvents") or [{}])[-1]
    if row["label"] and (previous.get("kind"), previous.get("label"), previous.get("detail")) != (row["kind"], row["label"], row.get("detail")):
        task.setdefault("runtimeEvents", []).append(row)
        task["runtimeEvents"] = task["runtimeEvents"][-200:]


def apply_task_event(task_id, event):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task or not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "response":
            request_id = str(event.get("id") or "")
            if request_id:
                task.setdefault("rpcResponses", {})[request_id] = event
                task["rpcResponses"] = dict(list(task["rpcResponses"].items())[-20:])
            if not event.get("success", False) and request_id.startswith("prompt-"):
                task["rpcError"] = "Prime rejected the initial prompt"
                add_task_progress(task, "Prime rejected a command")
                add_runtime_event(task, "error", "Command rejected", task["rpcError"])
            data = event.get("data") or {}
            session_id = data.get("sessionId") if isinstance(data, dict) else None
            if valid_id(session_id):
                task["agentSessionId"] = session_id
                if not task.get("sessionId"):
                    task["sessionId"] = session_id
        elif event_type == "session" and valid_id(event.get("id")):
            task["agentSessionId"] = event["id"]
            if not task.get("sessionId"):
                task["sessionId"] = event["id"]
            add_task_progress(task, "Prime connected")
        elif event_type == "agent_start":
            task["agentEnded"] = False
            add_task_progress(task, "Agent started")
            add_runtime_event(task, "agent", "Agent started")
        elif event_type == "agent_end":
            task["agentEnded"] = True
            add_task_progress(task, "Finishing response")
            add_runtime_event(task, "agent", "Agent finished its turn")
        elif event_type == "turn_start":
            add_task_progress(task, "Working on the request")
            add_runtime_event(task, "turn", "Turn started")
        elif event_type in {"message_update", "message_end"}:
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                return
            if message.get("stopReason") == "error" or message.get("errorMessage"):
                error = sanitize_runtime_text(message.get("errorMessage") or "Model request failed")
                task["rpcError"] = error
                add_task_progress(task, "Model request failed")
                add_runtime_event(task, "error", "Model request failed", error)
            for part in message.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    task["liveResponse"] = str(part["text"])[-50000:]
                    add_task_progress(task, "Drafting response")
                elif part.get("type") in {"toolCall", "tool_call"}:
                    name = str(part.get("name") or part.get("toolName") or "tool")
                    add_task_progress(task, f"Using {name}")
                    add_runtime_event(task, "tool", f"Using {name}")
                elif part.get("type") in {"thinking", "reasoning"}:
                    add_runtime_event(task, "reasoning", "Reasoning in progress")
            usage = message.get("usage") or event.get("usage")
            if isinstance(usage, dict) and usage:
                task["usage"] = usage
        elif event_type == "tool_execution_start":
            add_task_progress(task, f"Using {event.get('toolName') or event.get('tool') or 'tool'}")
            add_runtime_event(task, "tool", f"Started {event.get('toolName') or event.get('tool') or 'tool'}")
        elif event_type == "tool_execution_end":
            add_task_progress(task, f"Finished {event.get('toolName') or event.get('tool') or 'tool'}")
            add_runtime_event(task, "tool", f"Finished {event.get('toolName') or event.get('tool') or 'tool'}")
        elif event_type == "auto_retry_start":
            attempt, maximum = int(event.get("attempt") or 0), int(event.get("maxAttempts") or 0)
            error = sanitize_runtime_text(event.get("errorMessage") or "Request failed")
            add_task_progress(task, f"Retrying model request ({attempt}/{maximum})")
            add_runtime_event(task, "retry", f"Retry {attempt} of {maximum}", error)
        elif event_type == "broker_exit":
            task["rpcError"] = "Rootless task broker exited"
            add_task_progress(task, "Isolated task runtime failed")
            add_runtime_event(task, "error", "Isolated task runtime failed")


def monitor_task(task_id, before):
    with TASK_LOCK:
        task = TASKS[task_id]
        process = task["process"]
    deadline = time.monotonic() + MAX_TASK_SECONDS
    log_lines = []
    timed_out = False
    stdin_closed = False
    completed_deadline = None
    while process.poll() is None:
        if time.monotonic() >= deadline:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            break
        if completed_deadline and time.monotonic() >= completed_deadline:
            process.terminate()
            break
        ready, _, _ = select.select([process.stdout], [], [], 1)
        if not ready:
            continue
        line = process.stdout.readline(262145)
        if not line:
            continue
        if len(line) > 262144:
            while line and not line.endswith("\n"):
                line = process.stdout.readline(262145)
            with TASK_LOCK:
                task = TASKS.get(task_id)
                if task:
                    add_task_progress(task, "Discarded an oversized runtime event")
            continue
        with TASK_LOCK:
            current = TASKS.get(task_id)
            if current:
                append_live_log(current, line)
        try:
            apply_task_event(task_id, json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError):
            with TASK_LOCK:
                current = TASKS.get(task_id)
                if current:
                    add_runtime_event(current, "console", "Runtime output", line)
        if len(line) <= 20000:
            log_lines.append(safe_runtime_line(line) + "\n")
            log_lines = log_lines[-200:]
        with TASK_LOCK:
            ended = bool(TASKS.get(task_id, {}).get("agentEnded"))
        if ended and not stdin_closed and process.stdin:
            process.stdin.close()
            process.stdin = None
            stdin_closed = True
            completed_deadline = time.monotonic() + 5
    try:
        remainder, _ = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        remainder, _ = process.communicate(timeout=5)
    for line in remainder.splitlines():
        with TASK_LOCK:
            current = TASKS.get(task_id)
            if current:
                append_live_log(current, line)
        try:
            apply_task_event(task_id, json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError):
            with TASK_LOCK:
                current = TASKS.get(task_id)
                if current:
                    add_runtime_event(current, "console", "Runtime output", line)
        if len(line) <= 20000:
            log_lines.append(safe_runtime_line(line) + "\n")
    output = "".join(log_lines[-200:])
    with TASK_LOCK:
        current = TASKS.get(task_id, {})
        rpc_error = current.get("rpcError")
        agent_ended = bool(current.get("agentEnded"))
    stopped = bool(current.get("stopRequested"))
    status = "timed_out" if timed_out else "stopped" if stopped else "failed" if rpc_error else "completed" if agent_ended or process.returncode == 0 else "failed"
    root = session_root(task.get("owner", INITIAL_ADMIN))
    after = session_stems(task.get("owner", INITIAL_ADMIN))
    try:
        created = sorted(after - before, key=lambda value: (root / f"{value}.jsonl").stat().st_mtime, reverse=True)
    except OSError:
        created = []
    with TASK_LOCK:
        task = TASKS[task_id]
        if not task.get("sessionId") and created:
            task["sessionId"] = created[0]
        task.update({"status": status, "finished": now_iso(), "elapsedSeconds": round(time.time() - task["startedEpoch"], 1)})
        add_task_progress(task, status.replace("_", " ").title())
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
            "owner": task.get("owner", INITIAL_ADMIN),
        })
        if task.get("persistPolicyOnSessionCreate") and isinstance(task.get("policyPreference"), dict):
            row["taskPolicy"] = dict(task["policyPreference"])
        legacy.atomic_json(META, data)


def policy_preference(payload, role):
    payload = payload if isinstance(payload, dict) else {}
    role = task_policy.normalize_role(role)
    profile = str(payload.get("profile") or "general")
    execution = str(payload.get("executionMode") or "prompt")
    network = str(payload.get("networkMode") or "restricted")
    local_paths = task_policy.normalize_local_paths(payload.get("localPaths"), role)
    if profile not in task_policy.PROFILES or execution not in task_policy.EXECUTION_MODES or network not in task_policy.NETWORK_MODES:
        raise ValueError("Unsupported conversation policy")
    if (profile == "network-operations" or network in {"lan", "full"}) and role not in {"power_user", "admin"}:
        raise ValueError("This conversation policy requires power-user or administrator access")
    result = {"profile": profile, "executionMode": execution, "networkMode": network}
    if local_paths:
        result["localPaths"] = local_paths
    return result


def launch_task(message, session_id=None, fork=False, thinking=None, owner=INITIAL_ADMIN, authorization=None, policy=None):
    message = str(message).strip()
    if not message or len(message) > 100000:
        raise ValueError("Message must contain between 1 and 100,000 characters")
    if session_id and not valid_id(session_id):
        raise ValueError("Invalid conversation identifier")
    if session_id:
        require_conversation_owner(session_id, owner)
    prompt_message = message
    if (authorization or {}).get("localPaths"):
        prompt_message += "\n\nThe conversation's selected Spark-local inputs are mounted read-only under /project-files inside the task container."
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
    task_id = uuid.uuid4().hex
    if container_mode():
        command = container_runner.broker_command(task_id, owner, authorization or {}, route["provider"], route["model"], thinking, session_id, fork)
        task_cwd = legacy.HOME
        task_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    else:
        command = [str(legacy.PRIME_AGENT), "--cwd", str(legacy.HOME / "prime-dgx-agent"), "--mode", "rpc", "--provider", route["provider"], "--model", route["model"], "--thinking", thinking]
        if (authorization or {}).get("executionMode") == "deny":
            command.append("--no-tools")
        if session_id:
            command.extend(["--fork" if fork else "--resume", session_id])
        task_cwd = legacy.HOME / "prime-dgx-agent"
        task_env = prime_env()
    before = session_stems(owner)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=task_cwd, env=task_env, start_new_session=True)
    started = now_iso()
    task = {"id": task_id, "sessionId": session_id if not fork else None, "agentSessionId": session_id if session_id and not fork else None, "rpcReady": True, "rpcResponses": {}, "owner": owner, "authorization": authorization or {}, "policyPreference": policy or {}, "persistPolicyOnSessionCreate": not bool(session_id) or fork, "topic": legacy.safe_topic(message) or "Native task", **route, "thinking": thinking, "contextWindow": details.get("contextWindow"), "maxTokens": details.get("maxTokens"), "status": "running", "progress": "Starting Prime", "progressEvents": [{"at": started, "label": "Request received"}], "runtimeEvents": [{"at": started, "kind": "request", "label": "Request received"}], "liveLog": [], "liveLogBytes": 0, "liveResponse": "", "started": started, "startedEpoch": time.time(), "pid": process.pid, "process": process, "logAvailable": False}
    with TASK_LOCK:
        TASKS[task_id] = task
    with META_LOCK:
        data = metadata()
        data.setdefault("tasks", {})[task_id] = {"owner": owner, "createdAt": task["started"]}
        legacy.atomic_json(META, data)
    if task.get("sessionId"):
        store_task_route(task)
    try:
        process.stdin.write(json.dumps({"id": f"state-{task_id}", "type": "get_state"}, separators=(",", ":")) + "\n")
        process.stdin.write(json.dumps({"id": f"prompt-{task_id}", "type": "prompt", "message": prompt_message}, separators=(",", ":")) + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError, ValueError) as error:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        with TASK_LOCK:
            TASKS.pop(task_id, None)
        with META_LOCK:
            data = metadata()
            data.get("tasks", {}).pop(task_id, None)
            legacy.atomic_json(META, data)
        raise RuntimeError("Prime could not accept the initial prompt") from error
    threading.Thread(target=monitor_task, args=(task_id, before), daemon=True).start()
    legacy.audit("native_task_started", task=task_id, session=session_id)
    return {key: value for key, value in task.items() if key not in {"process", "rpcResponses", "agentEnded", "liveLogBytes"}}


def stop_native_task(task_id, owner=INITIAL_ADMIN):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task or task.get("owner", INITIAL_ADMIN) != owner or task["status"] != "running":
            raise ValueError("Task is no longer running")
        process = task["process"]
        if not process.stdin:
            raise ValueError("Task is no longer accepting commands")
    try:
        process.stdin.write('{"type":"abort"}\n')
        process.stdin.flush()
    except (BrokenPipeError, OSError, ValueError) as error:
        raise RuntimeError("Prime is no longer accepting commands") from error
    with TASK_LOCK:
        current = TASKS.get(task_id)
        if current:
            current["stopRequested"] = True
            add_task_progress(current, "Stopping task")
    return {"stopping": True, "id": task_id}


def message_native_task(task_id, message, mode="steer", owner=INITIAL_ADMIN):
    message = str(message).strip()
    if not message or len(message) > 10000:
        raise ValueError("Steering message must contain between 1 and 10,000 characters")
    if mode not in {"steer", "follow-up"}:
        raise ValueError("Unsupported task message mode")
    request_id = f"task-message-{uuid.uuid4().hex}"
    if container_mode():
        prompt_id = f"prompt-{task_id}"
        deadline = time.monotonic() + 10
        initial = None
        while time.monotonic() < deadline:
            with TASK_LOCK:
                current = TASKS.get(task_id)
                if not current or current.get("status") != "running":
                    raise ValueError("Task is no longer running")
                initial = current.get("rpcResponses", {}).get(prompt_id)
            if initial:
                break
            time.sleep(0.02)
        if not initial or not initial.get("success", False):
            raise RuntimeError("Prime has not accepted the initial task yet")
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task or task.get("owner", INITIAL_ADMIN) != owner or task.get("status") != "running":
            raise ValueError("Task is no longer running")
        process = task.get("process")
        if not task.get("rpcReady") or not process or not process.stdin:
            raise RuntimeError("Prime is still connecting; try again in a moment")
    request = {"id": request_id, "type": "steer" if mode == "steer" else "follow_up", "message": message}
    try:
        process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError, ValueError) as error:
        raise RuntimeError("Prime is no longer accepting task messages") from error
    deadline = time.monotonic() + 5
    response = None
    while time.monotonic() < deadline:
        with TASK_LOCK:
            current = TASKS.get(task_id)
            response = (current or {}).get("rpcResponses", {}).get(request_id)
        if response:
            break
        time.sleep(0.02)
    if not response:
        raise RuntimeError("Prime did not acknowledge the task message")
    if not response.get("success", False):
        raise RuntimeError("Prime rejected the task message")
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task:
            task.setdefault("steering", []).append({"at": now_iso(), "mode": mode, "message": message[:1000]})
            task["steering"] = task["steering"][-20:]
            add_task_progress(task, "Steering delivered" if mode == "steer" else "Follow-up queued")
    legacy.audit("native_task_message", task=task_id, mode=mode, owner=owner)
    return {"delivered": True, "id": task_id, "mode": mode}


def update_conversation(session_id, action, value=None, user=INITIAL_ADMIN, role="user"):
    if not valid_id(session_id):
        raise ValueError("Conversation not found")
    legacy.session_path(session_id, session_root(user))
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
        if not container_mode():
            subprocess.run([str(legacy.PRIME_AGENT), "rename", session_id, title, "--json"], timeout=12, check=False, capture_output=True, env=prime_env())
        row["title"] = title
    elif action == "policy":
        row["taskPolicy"] = policy_preference(value, role)
    else:
        raise ValueError("Unsupported conversation action")
    save_metadata(data)
    return {"id": session_id, **row}


def upload_rows(user=INITIAL_ADMIN):
    rows = []
    if not legacy.UPLOADS.exists():
        return rows
    for path in legacy.UPLOADS.rglob("*"):
        try:
            if not path.is_file() or path.name.startswith("."):
                continue
            relative = path.relative_to(legacy.UPLOADS).as_posix()
            if metadata().get("files", {}).get(relative, {}).get("owner", INITIAL_ADMIN) != user:
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
    if user is not None and metadata().get("files", {}).get(relative, {}).get("owner", INITIAL_ADMIN) != user:
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
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", username) or username == INITIAL_ADMIN:
        raise ValueError("The initial administrator cache cannot be deleted here")
    with TASK_LOCK:
        if any(row.get("owner") == username and row.get("status") == "running" for row in TASKS.values()):
            raise RuntimeError("Stop the user's active tasks before deleting their cache")
    data = metadata()
    owned_sessions = [sid for sid, row in data.get("conversations", {}).items() if row.get("owner", INITIAL_ADMIN) == username]
    recovery = USER_TRASH / username / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    recovery.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(USER_TRASH, 0o700); os.chmod(USER_TRASH / username, 0o700)
    moved_sessions = moved_files = moved_logs = 0
    for session_id in owned_sessions:
        try:
            source = legacy.session_path(session_id, session_root(username))
            os.replace(source, recovery / source.name)
            moved_sessions += 1
        except ValueError:
            pass
    for relative, row in list(data.get("files", {}).items()):
        if row.get("owner", INITIAL_ADMIN) != username:
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
        owned_tasks = {task_id for task_id, row in TASKS.items() if row.get("owner", INITIAL_ADMIN) == username}
    owned_tasks.update(task_id for task_id, row in data.get("tasks", {}).items() if row.get("owner", INITIAL_ADMIN) == username)
    for task_id in owned_tasks:
        source = TASK_LOGS / f"{task_id}.log"
        if source.is_file():
            target = recovery / "task-logs" / source.name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, target)
            moved_logs += 1
        data.get("tasks", {}).pop(task_id, None)
    moved_ledger = 0
    with LEDGER_LOCK:
        retained = []
        removed = []
        try:
            for line in LEDGER.read_text(errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    retained.append(line); continue
                (removed if row.get("owner", INITIAL_ADMIN) == username else retained).append(line)
        except OSError:
            pass
        if removed:
            ledger_recovery = recovery / "usage-ledger.jsonl"
            ledger_recovery.write_text("\n".join(removed) + "\n")
            os.chmod(ledger_recovery, 0o600)
            ledger_temp = LEDGER.with_name(f".{LEDGER.name}.{uuid.uuid4().hex}.tmp")
            ledger_temp.write_text("\n".join(retained) + ("\n" if retained else ""))
            os.chmod(ledger_temp, 0o600)
            os.replace(ledger_temp, LEDGER)
            moved_ledger = len(removed)
    save_metadata(data)
    legacy.audit("user_cache_deleted", user=username, sessions=moved_sessions, files=moved_files, logs=moved_logs, ledger=moved_ledger)
    return {"user": username, "sessions": moved_sessions, "files": moved_files, "logs": moved_logs, "usageRecords": moved_ledger, "recoverable": True}


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


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", str(value).strip())
    return tuple(map(int, match.groups())) if match else None


def release_status():
    definitions = {
        "agent": ("PrimeIntellect-ai/prime-agent", "Prime Agent"),
        "webui": ("dmbyte/prime_agent_webui", "Prime WebUI"),
    }
    rows = {}
    for kind, (repository, label) in definitions.items():
        try:
            result = subprocess.run(["gh", "api", f"repos/{repository}/releases/latest"], capture_output=True, text=True, timeout=15, check=True)
            release = json.loads(result.stdout)
            tag = str(release.get("tag_name") or "")[:80]
            name = str(release.get("name") or tag)[:120]
            url = str(release.get("html_url") or "")[:500]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}", tag) or not url.startswith("https://github.com/"):
                raise ValueError("Invalid release metadata")
            if kind == "agent":
                package = legacy.PRIME_BIN.parent / "lib/node_modules/prime-agent/package.json"
                installed = str(legacy.read_json(package, {}).get("version") or "unknown")
                current_version, latest_version = version_tuple(installed), version_tuple(tag)
                available = bool(current_version and latest_version and latest_version > current_version)
            else:
                repo = Path(os.environ.get("PRIME_WEBUI_REPO", legacy.HOME / "prime_agent_webui"))
                current = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
                resolved = subprocess.run(["gh", "api", f"repos/{repository}/commits/{tag}", "--jq", ".sha"], capture_output=True, text=True, timeout=15, check=True).stdout.strip()
                if not re.fullmatch(r"[a-f0-9]{40}", current) or not re.fullmatch(r"[a-f0-9]{40}", resolved): raise ValueError("Invalid release revision")
                ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", resolved, current], capture_output=True, timeout=5).returncode == 0
                available = current != resolved and not ancestor
                installed = name if current == resolved else f"{name}+{current[:7]}" if ancestor else current[:7]
            rows[kind] = {"label": label, "repository": repository, "installed": installed, "latestName": name, "latestTag": tag, "publishedAt": release.get("published_at"), "url": url, "available": available, "checkedAt": now_iso()}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError, TypeError) as error:
            rows[kind] = {"label": label, "repository": repository, "available": False, "error": "Release check unavailable", "checkedAt": now_iso()}
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


def csrf_identity(headers):
    parsed = SimpleCookie()
    try:
        parsed.load(headers.get("Cookie", ""))
    except Exception:
        return ""
    cookie = parsed.get("prime_csrf")
    return cookie.value if cookie else ""


def execution_grant(user, headers):
    key = (user, csrf_identity(headers))
    now = time.time()
    with EXECUTION_GRANT_LOCK:
        for candidate, expires in list(EXECUTION_GRANTS.items()):
            if expires <= now:
                EXECUTION_GRANTS.pop(candidate, None)
        return bool(key[1] and EXECUTION_GRANTS.get(key, 0) > now)


def grant_login_execution(user, headers, confirmation):
    if confirmation != "allow-execution-login":
        raise ValueError("Explicit login-session execution confirmation is required")
    key = (user, csrf_identity(headers))
    if not key[1]:
        raise ValueError("A valid WebUI session is required")
    with EXECUTION_GRANT_LOCK:
        EXECUTION_GRANTS[key] = time.time() + 12 * 60 * 60
    legacy.audit("login_execution_granted", owner=user)
    return {"granted": True, "expiresInSeconds": 12 * 60 * 60}


def task_capabilities(role):
    role = task_policy.normalize_role(role)
    return {
        "role": role,
        "profiles": sorted(task_policy.PROFILES),
        "networkModes": ["restricted", "internet"] + (["lan", "full"] if role in {"power_user", "admin"} else []),
        "executionModes": ["prompt", "task", "login", "deny"],
        "defaults": task_policy.ROLE_DEFAULTS[role].__dict__,
        "maximums": task_policy.ROLE_MAXIMUMS[role].__dict__,
        "packageOverride": role == "admin",
        "localPathAccess": role in {"power_user", "admin"},
        "maxLocalPaths": task_policy.MAX_LOCAL_PATHS,
    }


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
                role = self.headers.get("X-Prime-Role", "user")
                self.send_json(200, {"settings": legacy.settings_view(), "models": legacy.model_catalog(), "usage": usage_for_user(user), "requestLedger": {"nativeRequests": 0, "recent": []}, "sessions": conversation_catalog(query.get("q", [""])[0], query.get("archived", ["0"])[0] == "1", user), "telemetry": legacy.telemetry(), "nativeTasks": task_snapshot(user), "identity": {"user": user, "role": role}, "taskCapabilities": task_capabilities(role)})
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
            elif path == "/api/providers/catalog":
                self.require_admin()
                self.send_json(200, {"providers": provider_catalog()})
            elif path == "/api/admin/releases":
                self.require_admin()
                self.send_json(200, {"releases": release_status()})
            elif path == "/api/admin/routing-rules":
                self.require_admin()
                self.send_json(200, {"rules": routing_rules()})
            else:
                super().do_GET()
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except OSError:
            self.send_json(500, {"error": "Request could not be completed"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        v2 = {"/api/settings", "/api/tasks/start", "/api/tasks/stop", "/api/tasks/message", "/api/tasks/authorization", "/api/conversations/update", "/api/conversations/delete", "/api/conversations/duplicate", "/api/files/delete", "/api/admin/restart", "/api/admin/retention", "/api/admin/update", "/api/admin/user-cache", "/api/admin/routing-rules", "/api/providers/configure", "/api/files/upload"}
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
            role = self.headers.get("X-Prime-Role", "user")
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
            elif path == "/api/providers/configure":
                self.require_admin()
                self.send_json(200, configure_provider(payload))
            elif path == "/api/admin/routing-rules":
                self.require_admin()
                self.send_json(200, update_routing_rules(payload))
            elif path == "/api/tasks/start":
                requested = payload.get("taskPolicy") or {}
                preference = policy_preference(payload.get("conversationPolicy"), role)
                authorization = task_policy.authorize_task(
                    requested,
                    role,
                    login_execution=execution_grant(user, self.headers),
                    task_execution_confirmed=payload.get("executionConfirm") == "allow-execution-task",
                    network_confirmed=payload.get("networkConfirm") == f"allow-network-{requested.get('networkMode')}",
                    files_confirmed=payload.get("filesConfirm") == "allow-local-files-task",
                )
                self.send_json(202, {"task": launch_task(payload.get("message"), payload.get("sessionId"), thinking=payload.get("thinking"), owner=user, authorization=authorization, policy=preference)})
            elif path == "/api/tasks/stop":
                self.send_json(200, stop_native_task(str(payload.get("id", "")), user))
            elif path == "/api/tasks/message":
                self.send_json(202, message_native_task(str(payload.get("id", "")), payload.get("message"), str(payload.get("mode", "steer")), user))
            elif path == "/api/tasks/authorization":
                self.send_json(200, grant_login_execution(user, self.headers, payload.get("confirm")))
            elif path == "/api/conversations/update":
                self.send_json(200, update_conversation(str(payload.get("id", "")), str(payload.get("action", "")), payload.get("value"), user, role))
            elif path == "/api/conversations/delete":
                session_id = str(payload.get("id", ""))
                require_conversation_owner(session_id, user)
                with TASK_LOCK:
                    active_ids = {value for task in TASKS.values() if task.get("owner") == user and task.get("status") == "running" for value in (task.get("sessionId"), task.get("agentSessionId")) if value}
                self.send_json(200, legacy.delete_conversation(session_id, session_root(user), session_trash(user), active_ids))
            elif path == "/api/conversations/duplicate":
                authorization = task_policy.authorize_task({"executionMode": "deny"}, role)
                self.send_json(202, {"task": launch_task("Continue this fork with a concise recap of the inherited context.", str(payload.get("id", "")), True, owner=user, authorization=authorization)})
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
