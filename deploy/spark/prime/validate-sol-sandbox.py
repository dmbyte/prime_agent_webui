#!/usr/bin/env python3
"""Canary: verify SOL's PTY and renderer in a real restricted OpenShell task image.

Run as prime-runner on the Spark. No BMC credentials or network access are used.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/prime-runner")
import openshell_runner


def main() -> None:
    if os.geteuid() == 0:
        raise SystemExit("Run as prime-runner, not root")
    owner = os.environ.get("PRIME_WEB_OWNER", "dbyte")
    root = Path("/var/lib/prime-runner")
    task_id = uuid.uuid4().hex
    spec = openshell_runner.task_spec(
        task_id, owner,
        {"profile": "network-operations", "networkMode": "restricted",
         "executionMode": "task", "approvalMode": "manual"},
        "spark-nemotron", "canary", "low",
        storage_root=root / "users",
        image_manifest=root / "openshell-image-digests.json",
        policy_root=root / "openshell-policies",
        workspace_root=Path(f"/home/{owner}/prime-agent/tasks"),
    )
    env = {**os.environ, "HOME": str(root)}
    created = False
    try:
        subprocess.run(spec["create"], check=True, env=env)
        created = True
        command = ["/usr/bin/openshell", "--gateway", "spark-local", "sandbox", "exec",
                   "--name", spec["name"], "--no-tty", "--",
                   "/opt/prime-kernel/bin/python", "-c",
                   "import os,pty,pyte,ipmi_redfish_bmc; m,s=pty.openpty(); "
                   "os.close(m); os.close(s); "
                   "assert hasattr(ipmi_redfish_bmc,'SOLSession'); "
                   "assert pyte.Screen(100,31).columns==100; print('SOL PTY and screen ready')"]
        subprocess.run(command, check=True, env=env, timeout=60)
    finally:
        if created or "--keep-on-failure" not in sys.argv:
            subprocess.run(spec["delete"], check=False, env=env, timeout=45)
            spec["policy"].unlink(missing_ok=True)
        else:
            print(f"Failed sandbox retained for diagnostics: {spec['name']}")


if __name__ == "__main__":
    main()
