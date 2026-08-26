#!/usr/bin/env python3
"""Build fail-closed rootless Podman argv for one ephemeral Prime task."""

import os
import re
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
    agent = user_root / "agent"
    workspace = user_root / "workspace"
    for path in (user_root, agent, workspace):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return agent, workspace


def command(task_id, owner, authorization, provider, model, thinking, session_id=None, fork=False, storage_root=None):
    if not SAFE_TASK.fullmatch(str(task_id)):
        raise ValueError("Invalid task identifier")
    if session_id and not SAFE_SESSION.fullmatch(str(session_id)):
        raise ValueError("Invalid conversation identifier")
    profile = authorization.get("profile", "general")
    image = PROFILE_IMAGES.get(profile)
    if not image:
        raise ValueError("Unsupported task container profile")
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
        "--network", network_arg, "--read-only", "--cap-drop=all",
        "--security-opt", "no-new-privileges", "--userns=keep-id",
        "--user", f"{uid}:{gid}", "--memory", f"{memory}g", "--cpus", str(cpus),
        "--pids-limit", str(pids), "--ulimit", f"nofile={open_files}:{open_files}",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={temporary}g,mode=1777",
        "--mount", f"type=bind,src={agent},dst=/home/prime/.prime/agent,rw",
        "--mount", f"type=bind,src={workspace},dst=/workspace,rw",
        "--env", "HOME=/home/prime", "--workdir", "/workspace", image,
        "--cwd", "/workspace", "--mode", "rpc", "--provider", str(provider),
        "--model", str(model), "--thinking", str(thinking),
    ]
    if authorization.get("executionMode") == "deny":
        argv.append("--no-tools")
    if session_id:
        argv.extend(["--fork" if fork else "--resume", str(session_id)])
    return argv

