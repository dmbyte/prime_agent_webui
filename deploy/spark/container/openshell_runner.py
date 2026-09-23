#!/usr/bin/env python3
"""Build validated OpenShell commands for one ephemeral Prime task sandbox."""

import json
import os
import re
from pathlib import Path

import task_common


SAFE_OPEN_SHELL_IMAGE = re.compile(
    r"local/prime-openshell-[a-z-]+:0\.9\.5-[a-f0-9]{12}\Z"
)
DEFAULT_LIMITS = {"memoryGiB": 8, "cpus": 4, "runtimeMinutes": 30}


def image_for_profile(profile, manifest):
    record = json.loads(Path(manifest).read_text()).get(profile)
    image = record.get("image") if isinstance(record, dict) else None
    if not image or not SAFE_OPEN_SHELL_IMAGE.fullmatch(image):
        raise ValueError("OpenShell profile image is not pinned by an approved immutable tag")
    return image


def _volume(source, target, read_only):
    return {
        "type": "volume",
        "source": str(source),
        "target": target,
        "read_only": bool(read_only),
    }


def _shared_path_volume(source, target):
    source = Path(source)
    root = next((root for root in task_common.LOCAL_PATH_ROOTS
                 if source == root or root in source.parents), None)
    if root is None:
        raise ValueError("Local path is outside approved data roots")
    mount = _volume(f"prime-shared-{root.name}", target, True)
    relative = source.relative_to(root)
    if relative.parts:
        mount["subpath"] = str(relative)
    return mount


def task_spec(task_id, owner, authorization, provider, model, thinking,
              session_id=None, fork=False, storage_root=None, image_manifest=None,
              policy_root=None, workspace_root=None):
    if not task_common.SAFE_TASK.fullmatch(str(task_id)):
        raise ValueError("Invalid task identifier")
    if session_id and not task_common.SAFE_SESSION.fullmatch(str(session_id)):
        raise ValueError("Invalid conversation identifier")
    if not task_common.SAFE_USER.fullmatch(str(owner)):
        raise ValueError("Invalid task owner")
    profile = authorization.get("profile", "general")
    storage_root = Path(storage_root or "/var/lib/prime-runner/users")
    agent, workspace = task_common.prepare_user_storage(storage_root, owner, workspace_root)
    network = authorization.get("networkMode", "restricted")
    if network not in {"restricted", "internet", "lan", "full"}:
        raise ValueError("Unsupported task network mode")
    approval = authorization.get("approvalMode", "manual")
    if approval not in {"manual", "auto"}:
        raise ValueError("Unsupported OpenShell approval mode")
    limits = {**DEFAULT_LIMITS, **(authorization.get("limits") or {})}
    memory = int(limits["memoryGiB"])
    cpus = int(limits["cpus"])
    runtime = int(limits["runtimeMinutes"])
    image = image_for_profile(profile, image_manifest)
    sandbox = f"pt-{task_id[:16]}"
    input_fifo = f"/tmp/prime-rpc-{task_id[:16]}.fifo"
    # These pre-provisioned Docker volumes are local-driver bind volumes. They
    # preserve Prime's /var/lib ownership boundary without granting the
    # unprivileged OpenShell gateway process access to that host tree.
    mounts = [
        _volume(f"prime-{owner}-prime", "/home/prime/.prime", False),
        _volume(f"prime-{owner}-workspace", "/project", False),
        _volume(f"prime-{owner}-gateway-{network}", "/run/prime-gateway", True),
    ]
    local_targets = []
    for source, target in task_common.local_mounts(authorization.get("localPaths")):
        mounts.append(_shared_path_volume(source, target))
        local_targets.append(target)
    policy_root = Path(policy_root or storage_root.parent / "openshell-policies")
    policy_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    policy_path = policy_root / f"{task_id}.yaml"
    read_only = ["/usr", "/lib", "/proc", "/etc", "/opt/prime-kernel", "/run/prime-gateway", "/home/prime/.prime/agent/project-sources", *local_targets]
    lines = [
        "version: 1", "filesystem_policy:", "  include_workdir: true", "  read_only:",
        *[f"    - {path}" for path in read_only],
        "  read_write:", "    - /home/prime/.prime", "    - /project", "    - /tmp",
        # Chromium's NSS runtime opens the random devices directly and uses
        # shared memory. These grants must be present when the sandbox is
        # created because a later OpenShell policy update cannot widen the
        # process' existing Landlock domain.
        "    - /dev/null", "    - /dev/urandom", "    - /dev/random", "    - /dev/shm",
        "landlock:", "  compatibility: hard_requirement", "network_policies: {}", "",
    ]
    temporary = policy_path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines))
    os.chmod(temporary, 0o600)
    os.replace(temporary, policy_path)
    driver_config = json.dumps({"docker": {"mounts": mounts}}, separators=(",", ":"))
    common = ["/usr/bin/openshell", "--gateway", "spark-local"]
    create = common + [
        "sandbox", "create", "--name", sandbox, "--from", image,
        "--policy", str(policy_path), "--driver-config-json", driver_config,
        "--cpu", str(cpus), "--memory", f"{memory}Gi", "--approval-mode", approval,
        "--label", f"prime.owner={owner}", "--label", f"prime.profile={profile}",
        "--label", f"prime.network={network}", "--label", f"prime.task={task_id}",
        "--detach", "--no-auto-providers", "--no-tty", "--", "/bin/sleep", "infinity",
    ]
    daemon_socket = f"/tmp/prime-daemon-{task_id[:16]}.sock"
    prime = [
        "/usr/local/bin/prime-container-entrypoint", "--cwd", "/project", "--mode", "rpc",
        "--daemon-socket", daemon_socket,
        "--provider", str(provider), "--model", str(model), "--thinking", str(thinking),
    ]
    if authorization.get("executionMode") == "deny":
        prime.append("--no-tools")
    if session_id:
        prime.extend(["--fork" if fork else "--resume", str(session_id)])
    relay = (
        "import fcntl,os,subprocess,sys; "
        "r=os.open(sys.argv[1],os.O_RDONLY|os.O_NONBLOCK); "
        "w=os.open(sys.argv[1],os.O_WRONLY|os.O_NONBLOCK); "
        "fcntl.fcntl(r,fcntl.F_SETFL,fcntl.fcntl(r,fcntl.F_GETFL)&~os.O_NONBLOCK); "
        "raise SystemExit(subprocess.Popen(sys.argv[2:],stdin=os.fdopen(r,'rb',buffering=0)).wait())"
    )
    execute = [
        "/usr/bin/timeout", "--signal=TERM", "--kill-after=15s", f"{runtime}m",
        *common, "sandbox", "exec", "--name", sandbox, "--workdir", "/project", "--no-tty",
        "--env", "HOME=/home/prime", "--env", "NO_PROXY=127.0.0.1,localhost,::1",
        "--env", "no_proxy=127.0.0.1,localhost,::1", "--env", "TINI_SUBREAPER=1",
        "--env", "PATH=/home/prime/.prime/tools/npm/bin:/project/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "--env", "XDG_CACHE_HOME=/home/prime/.prime/cache",
        "--env", "UV_CACHE_DIR=/home/prime/.prime/cache/uv",
        "--env", "PIP_CACHE_DIR=/home/prime/.prime/cache/pip",
        "--env", "NPM_CONFIG_CACHE=/home/prime/.prime/cache/npm",
        "--env", "NPM_CONFIG_PREFIX=/home/prime/.prime/tools/npm",
        "--env", "PLAYWRIGHT_BROWSERS_PATH=/home/prime/.prime/tools/playwright",
        "--env", "PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python",
        "--env", "IPYTHONDIR=/home/prime/.prime/ipython", "--",
        "/usr/bin/python3", "-c", relay, input_fifo, *prime,
    ]
    prepare_input = common + [
        "sandbox", "exec", "--name", sandbox, "--no-tty", "--",
        "/bin/sh", "-lc", f"rm -f {input_fifo}; mkfifo -m 600 {input_fifo}",
    ]
    delete = common + ["sandbox", "delete", sandbox]
    return {"name": sandbox, "create": create, "execute": execute, "delete": delete,
            "prepareInput": prepare_input, "inputFifo": input_fifo,
            "daemonSocket": daemon_socket, "policy": policy_path, "image": image,
            "workspace": workspace}
