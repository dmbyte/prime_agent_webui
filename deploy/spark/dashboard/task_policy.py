#!/usr/bin/env python3
"""Server-enforced task authorization policy for containerized Prime work."""

from dataclasses import dataclass


ROLES = {"user", "power_user", "admin"}
EXECUTION_MODES = {"prompt", "task", "login", "deny"}
NETWORK_MODES = {"restricted", "internet", "lan", "full"}
PROFILES = {"general", "development", "cad", "finance", "network-operations", "review"}


@dataclass(frozen=True)
class ResourceLimits:
    memory_gib: int
    cpus: int
    runtime_minutes: int
    pids: int = 256
    open_files: int = 1024
    temporary_gib: int = 4


ROLE_DEFAULTS = {
    "user": ResourceLimits(8, 4, 30),
    "power_user": ResourceLimits(8, 4, 30),
    "admin": ResourceLimits(8, 4, 30),
}
ROLE_MAXIMUMS = {
    "user": ResourceLimits(8, 4, 30),
    "power_user": ResourceLimits(16, 8, 120, temporary_gib=8),
    "admin": ResourceLimits(24, 12, 240, temporary_gib=16),
}


def normalize_role(value):
    role = str(value or "user")
    if role not in ROLES:
        raise ValueError("Unsupported WebUI role")
    return role


def authorize_task(payload, role, login_execution=False, task_execution_confirmed=False, network_confirmed=False):
    """Return an immutable, normalized policy or reject an unauthorized request."""
    role = normalize_role(role)
    profile = str(payload.get("profile") or "general")
    network = str(payload.get("networkMode") or "restricted")
    execution = str(payload.get("executionMode") or "prompt")
    if profile not in PROFILES:
        raise ValueError("Unsupported task profile")
    if network not in NETWORK_MODES:
        raise ValueError("Unsupported network mode")
    if execution not in EXECUTION_MODES:
        raise ValueError("Unsupported execution mode")
    if network in {"lan", "full"} and role not in {"power_user", "admin"}:
        raise ValueError("LAN and full-network tasks require power-user or administrator access")
    if profile == "network-operations" and role not in {"power_user", "admin"}:
        raise ValueError("The network-operations profile requires power-user or administrator access")
    if network == "full" and execution == "deny":
        raise ValueError("Full-network tasks require task execution approval")
    approved_execution = execution == "login" and login_execution or execution == "task" and task_execution_confirmed
    if execution == "login" and not login_execution:
        raise ValueError("Login-session execution approval is required")
    if execution == "task" and not task_execution_confirmed:
        raise ValueError("Task execution approval is required")
    if network in {"lan", "full"} and not network_confirmed:
        raise ValueError("Explicit private-network approval is required")
    requested = payload.get("limits") or {}
    defaults, maximums = ROLE_DEFAULTS[role], ROLE_MAXIMUMS[role]
    limits = ResourceLimits(
        memory_gib=int(requested.get("memoryGiB", defaults.memory_gib)),
        cpus=int(requested.get("cpus", defaults.cpus)),
        runtime_minutes=int(requested.get("runtimeMinutes", defaults.runtime_minutes)),
        pids=defaults.pids,
        open_files=defaults.open_files,
        temporary_gib=int(requested.get("temporaryGiB", defaults.temporary_gib)),
    )
    if role == "user" and requested:
        raise ValueError("Resource overrides require power-user or administrator access")
    for name in ("memory_gib", "cpus", "runtime_minutes", "temporary_gib"):
        value = getattr(limits, name)
        if value < 1 or value > getattr(maximums, name):
            raise ValueError(f"Requested {name.replace('_', ' ')} exceeds the role limit")
    return {
        "role": role,
        "profile": profile,
        "networkMode": network,
        "executionMode": execution,
        "executionApproved": approved_execution,
        "packageOverride": bool(payload.get("packageOverride") and role == "admin"),
        "limits": {
            "memoryGiB": limits.memory_gib,
            "cpus": limits.cpus,
            "runtimeMinutes": limits.runtime_minutes,
            "pids": limits.pids,
            "openFiles": limits.open_files,
            "temporaryGiB": limits.temporary_gib,
        },
    }
