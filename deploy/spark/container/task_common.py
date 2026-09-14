#!/usr/bin/env python3
"""Shared validation and storage helpers for OpenShell task sandboxes."""

import base64
import json
import os
import re
from pathlib import Path


SAFE_USER = re.compile(r"[A-Za-z0-9_.-]{2,32}\Z")
SAFE_TASK = re.compile(r"[a-f0-9]{32}\Z")
SAFE_SESSION = re.compile(r"[A-Za-z0-9_-]{8,80}\Z")
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


def broker_command(task_id, owner, authorization, provider, model, thinking, session_id=None, fork=False):
    request = {"taskId": task_id, "owner": owner, "authorization": authorization,
               "provider": provider, "model": model, "thinking": thinking,
               "sessionId": session_id, "fork": bool(fork)}
    encoded = base64.urlsafe_b64encode(json.dumps(request, separators=(",", ":")).encode()).decode()
    return ["/usr/local/libexec/prime-runner-client", encoded]
