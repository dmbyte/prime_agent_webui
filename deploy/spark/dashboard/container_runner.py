#!/usr/bin/env python3
"""Build fail-closed rootless Podman argv for one ephemeral Prime task."""

import os
import re
import base64
import json
from pathlib import Path


SAFE_USER = re.compile(r"[A-Za-z0-9_.-]{2,32}\Z")
SAFE_TASK = re.compile(r"[a-f0-9]{32}\Z")
SAFE_SESSION = re.compile(r"[A-Za-z0-9_-]{8,80}\Z")
PROFILE_IMAGES = {
    "general": "localhost/prime-task-general:0.8.0",
    "development": "localhost/prime-task-development:0.8.0",
    "cad": "localhost/prime-task-cad:0.8.0",
    "finance": "localhost/prime-task-finance:0.8.0",
    "network-operations": "localhost/prime-task-network-operations:0.8.0",
    "review": "localhost/prime-task-review:0.8.0",
}
SAFE_IMAGE = re.compile(r"localhost/prime-task-[a-z-]+:0\.8\.0@sha256:[a-f0-9]{64}\Z")
LOCAL_PATH_ROOTS = tuple(Path(value) for value in ("/mnt", "/media", "/srv", "/opt"))
SENSITIVE_PARTS = {".ssh", ".gnupg", ".aws", ".kube", ".prime", "prime-agent"}


def _safe_path(root, child):
    resolved_root = root.resolve()
    candidate = (resolved_root / child).resolve()
    if candidate.parent != resolved_root:
        raise ValueError("Invalid isolated user storage path")
    return candidate


def prepare_user_storage(root, owner):
    if not SAFE_USER.fullmatch(str(owner)):
        raise ValueError("Invalid task owner")
    user_root = _safe_path(Path(root), owner)
    prime = user_root / "prime"
    agent = prime / "agent"
    workspace = user_root / "workspace"
    for path, mode in ((user_root, 0o700), (prime, 0o700), (agent, 0o700), (workspace, 0o700)):
        path.mkdir(mode=mode, parents=True, exist_ok=True)
        os.chmod(path, mode)
    return agent, workspace


def local_mounts(paths):
    """Resolve a bounded set of read-only host inputs at the privileged boundary."""
    mounts = []
    for index, value in enumerate(paths or [], 1):
        source = Path(value)
        if not source.is_absolute() or any(character in str(source) for character in "\x00\r\n,"):
            raise ValueError("Invalid local path")
        try:
            resolved = source.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError(f"Local path is unavailable: {source}") from error
        if not any(resolved == root or root in resolved.parents for root in LOCAL_PATH_ROOTS):
            raise ValueError("Local path is outside approved data roots")
        if any(part in SENSITIVE_PARTS for part in resolved.parts):
            raise ValueError("Sensitive credential and agent-state paths cannot be mounted")
        if not (resolved.is_file() or resolved.is_dir()):
            raise ValueError("Local path must be a regular file or directory")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", resolved.name).strip("-.")[:48] or "data"
        mounts.append((resolved, f"/project-files/{index:02d}-{safe_name}"))
    return mounts


def command(task_id, owner, authorization, provider, model, thinking, session_id=None, fork=False, storage_root=None, image_manifest=None):
    if not SAFE_TASK.fullmatch(str(task_id)):
        raise ValueError("Invalid task identifier")
    if session_id and not SAFE_SESSION.fullmatch(str(session_id)):
        raise ValueError("Invalid conversation identifier")
    profile = authorization.get("profile", "general")
    image = PROFILE_IMAGES.get(profile)
    if not image:
        raise ValueError("Unsupported task container profile")
    if image_manifest:
        configured = json.loads(Path(image_manifest).read_text()).get(profile)
        if not configured or not SAFE_IMAGE.fullmatch(configured):
            raise ValueError("Profile image is not pinned by an approved digest")
        image = configured
    limits = authorization.get("limits") or {}
    memory = int(limits["memoryGiB"])
    cpus = int(limits["cpus"])
    pids = int(limits["pids"])
    open_files = int(limits["openFiles"])
    temporary = int(limits["temporaryGiB"])
    storage_root = Path(storage_root or os.environ.get("PRIME_RUNNER_STORAGE", "/var/lib/prime-runner/users"))
    agent, workspace = prepare_user_storage(storage_root, owner)
    network = authorization.get("networkMode", "restricted")
    if network not in {"restricted", "internet", "lan", "full"}:
        raise ValueError("Unsupported task network mode")
    network_arg = "slirp4netns:enable_ipv6=true" if network == "full" else "none"
    uid, gid = os.getuid(), os.getgid()
    argv = [
        "/usr/bin/timeout", "--signal=TERM", "--kill-after=15s", f"{int(limits['runtimeMinutes'])}m",
        "/usr/bin/podman", "run", "--rm", "--interactive",
        "--name", f"prime-task-{task_id}", "--hostname", "prime-task",
        "--network", network_arg, "--read-only", "--read-only-tmpfs=false", "--cap-drop=all",
        "--security-opt", "no-new-privileges", "--userns=keep-id",
        "--user", f"{uid}:{gid}", "--memory", f"{memory}g", "--cpus", str(cpus),
        "--pids-limit", str(pids), "--ulimit", f"nofile={open_files}:{open_files}",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={temporary}g,mode=1777,notmpcopyup",
        "--tmpfs", "/run:rw,nosuid,nodev,size=64m,mode=0755,notmpcopyup",
        "--mount", f"type=bind,src={agent.parent},dst=/home/prime/.prime,rw",
        "--mount", f"type=bind,src={workspace},dst=/workspace,rw",
        "--mount", f"type=bind,src={storage_root.parent / 'gateway' / owner / network},dst=/run/prime-gateway,ro",
        "--env", "HOME=/home/prime",
        "--env", "NO_PROXY=127.0.0.1,localhost,::1",
        "--env", "no_proxy=127.0.0.1,localhost,::1",
    ]
    for source, target in local_mounts(authorization.get("localPaths")):
        argv.extend(["--mount", f"type=bind,src={source},dst={target},ro"])
    argv.extend([
        "--workdir", "/workspace", image,
        "--cwd", "/workspace", "--mode", "rpc", "--provider", str(provider),
        "--model", str(model), "--thinking", str(thinking),
    ])
    if authorization.get("executionMode") == "deny":
        argv.append("--no-tools")
    if session_id:
        argv.extend(["--fork" if fork else "--resume", str(session_id)])
    return argv


def broker_command(task_id, owner, authorization, provider, model, thinking, session_id=None, fork=False):
    request = {"taskId": task_id, "owner": owner, "authorization": authorization,
               "provider": provider, "model": model, "thinking": thinking,
               "sessionId": session_id, "fork": bool(fork)}
    encoded = base64.urlsafe_b64encode(json.dumps(request, separators=(",", ":")).encode()).decode()
    return ["/usr/local/libexec/prime-runner-client", encoded]
