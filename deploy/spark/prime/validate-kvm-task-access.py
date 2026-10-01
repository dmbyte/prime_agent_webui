#!/usr/bin/env python3
"""Verify KVM socket access in actual task policies; never contact a BMC."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/prime-runner")
import openshell_runner


def main():
    if os.geteuid() == 0:
        raise SystemExit("Run as prime-runner")
    owner = os.environ["PRIME_WEB_OWNER"]
    root = Path("/var/lib/prime-runner")
    manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "openshell-image-digests.json"
    for network in ("lan", "full", "restricted", "internet"):
        allowed = network in {"lan", "full"}
        spec = openshell_runner.task_spec(
            uuid.uuid4().hex, owner,
            {"profile": "network-operations", "networkMode": network,
             "executionMode": "task", "approvalMode": "manual",
             "limits": {"memoryGiB": 2, "cpus": 1, "runtimeMinutes": 5}},
            "spark-nemotron", "canary", "low", storage_root=root / "users",
            image_manifest=manifest, policy_root=root / "openshell-policies",
            workspace_root=Path(f"/home/{owner}/prime-agent/tasks"))
        try:
            subprocess.run(spec["create"], check=True, timeout=90)
            # Use the launcher-generated environment, as a real Prime task does.
            environment = []
            for index, argument in enumerate(spec["execute"]):
                if argument == "--env":
                    environment.extend([argument, spec["execute"][index + 1]])
            code = "from bmc_html5_kvm import KVMClient\n"
            if allowed:
                code += "assert isinstance(KVMClient.list_sessions(), list)\n"
            else:
                code += (
                    "try:\n    KVMClient.list_sessions()\n"
                    "except RuntimeError as error:\n"
                    "    assert 'KVM control socket is missing' in str(error)\n"
                    "else:\n    raise AssertionError('Unapproved KVM access')\n")
            code += (
                "from bmc_headless_browser import BMCBrowser\n"
                "try:\n    BMCBrowser('https://bmc.invalid')._command_blocking({})\n"
                "except RuntimeError as error:\n"
                "    assert 'Browser session is not open' in str(error)\n"
                "else:\n    raise AssertionError('Unopened browser accepted a command')\n"
                f"print('KVM task access: {network} passed')\n")
            subprocess.run(["/usr/bin/openshell", "--gateway", "spark-local", "sandbox", "exec",
                            "--name", spec["name"], "--no-tty", *environment, "--",
                            "/opt/prime-kernel/bin/python", "-c", code], check=True, timeout=60)
        finally:
            subprocess.run(spec["delete"], check=False, timeout=45)
            spec["policy"].unlink(missing_ok=True)


if __name__ == "__main__":
    main()
