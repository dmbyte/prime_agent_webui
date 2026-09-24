#!/usr/bin/env python3
"""Restore Prime storage ACLs after an interrupted OpenShell task."""

import os
import re
import subprocess
import sys
from pathlib import Path


SAFE_USER = re.compile(r"[A-Za-z0-9_.-]{2,32}\Z")
STORAGE_ROOT = Path("/var/lib/prime-runner")
WRITABLE_DIRS = ("sessions", "trash", "project-sources", "skills")


def set_acl(arguments, path):
    subprocess.run(["/usr/bin/setfacl", *arguments, str(path)], check=True)


def restore_tree(path, web_owner):
    if not path.is_dir():
        return
    set_acl(["-Rm", f"u:{web_owner}:rwX,g:prime-web:rwX,m::rwX,o::---"], path)
    for directory, _, _ in os.walk(path):
        set_acl(["-m", f"d:u:{web_owner}:rwx,d:g:prime-web:rwx,d:m::rwx,d:o::---"], Path(directory))


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: runner_recover.py WEB_OWNER WORKSPACE_ROOT")
    web_owner, workspace_root_value = sys.argv[1:]
    if not SAFE_USER.fullmatch(web_owner):
        raise SystemExit("invalid WebUI owner")
    workspace_root = Path(workspace_root_value)
    if not workspace_root.is_absolute() or workspace_root != Path(f"/home/{web_owner}/prime-agent/tasks"):
        raise SystemExit("invalid task workspace root")

    users_root = STORAGE_ROOT / "users"
    traverse = ["-m", f"u:{web_owner}:--x,g:prime-web:--x,m::--x"]
    for path in (STORAGE_ROOT, users_root):
        if path.is_dir():
            set_acl(traverse, path)

    if not users_root.is_dir():
        return
    for user_root in users_root.iterdir():
        if not user_root.is_dir() or not SAFE_USER.fullmatch(user_root.name):
            continue
        prime = user_root / "prime"
        agent = prime / "agent"
        for path in (user_root, prime, agent):
            if path.is_dir():
                set_acl(traverse, path)
        for name in WRITABLE_DIRS:
            restore_tree(agent / name, web_owner)
        restore_tree(workspace_root / user_root.name, web_owner)


if __name__ == "__main__":
    main()
