#!/usr/bin/env python3
"""Run a no-BMC Chromium canary in the dedicated KVM OpenShell policy."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


sys.path.insert(0, "/usr/local/lib/prime-runner")
import kvm_broker


def main() -> None:
    if os.geteuid() == 0:
        raise SystemExit("Run as prime-runner")
    owner = os.environ["PRIME_WEB_OWNER"]
    manifest = Path(sys.argv[1])
    spec = kvm_broker.sandbox_spec(owner, uuid.uuid4().hex, manifest)
    env = {**os.environ, "HOME": "/var/lib/prime-runner"}
    try:
        subprocess.run(spec["create"], check=True, env=env, timeout=90)
        code = (
            "from playwright.sync_api import sync_playwright; "
            "import bmc_html5_kvm; "
            "assert isinstance(bmc_html5_kvm.KVMClient.list_sessions(),list); "
            "p=sync_playwright().start(); "
            "b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,"
            "args=['--disable-dev-shm-usage','--disable-gpu','--no-zygote']); "
            "page=b.new_page(); page.set_content('<title>KVM canary</title><canvas></canvas>'); "
            "assert page.title()=='KVM canary'; "
            "assert page.screenshot(type='jpeg')[:2]==bytes.fromhex('ffd8'); "
            "b.close(); p.stop(); print('Restricted KVM Chromium canary ready')"
        )
        subprocess.run([*kvm_broker.COMMON, "sandbox", "exec", "--name", spec["name"],
                        "--no-tty", "--", "/opt/prime-kernel/bin/python", "-c", code],
                       check=True, env=env, timeout=75)
        subprocess.run(spec["launch"], check=True, env=env, timeout=30)
        deadline = time.monotonic() + 10
        while not spec["workerSocket"].is_socket() and time.monotonic() < deadline:
            time.sleep(.1)
        if not spec["workerSocket"].is_socket():
            raise RuntimeError("Detached KVM worker socket did not appear")
        kvm_broker._worker_call(spec["workerSocket"], "close", timeout=10)
        print("Detached KVM worker socket ready")
    finally:
        subprocess.run(spec["delete"], check=False, env=env, timeout=45)
        spec["workerSocket"].unlink(missing_ok=True)
        spec["policy"].unlink(missing_ok=True)


if __name__ == "__main__":
    main()
