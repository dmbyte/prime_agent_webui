"""Standards-based Redfish and ipmitool clients with mutation confirmation gates."""

from __future__ import annotations

import os
import codecs
import errno
import fcntl
import pty
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
import tty
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

try:
    import pyte
except ImportError:  # Installed only in the network-operations task image.
    pyte = None


class RedfishClient:
    def __init__(self, base_url: str, username: str, password: str, *, verify_tls: bool = True, timeout: int = 30):
        if not username or not password:
            raise ValueError("Redfish credentials must be supplied at runtime")
        if "://" not in base_url:
            base_url = "https://" + base_url
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must identify an HTTP(S) BMC endpoint")
        origin = f"{parsed.scheme}://{parsed.netloc}/"
        self.service_root = urljoin(origin, "redfish/v1/")
        self.timeout = int(timeout)
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = bool(verify_tls)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        if urlparse(path).scheme:
            candidate = path
        elif path.startswith("/redfish/"):
            root = urlparse(self.service_root)
            candidate = f"{root.scheme}://{root.netloc}{path}"
        else:
            candidate = urljoin(self.service_root, path.lstrip("/"))
        base = urlparse(self.service_root)
        target = urlparse(candidate)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise ValueError("Refusing a Redfish link outside the configured BMC origin")
        return candidate

    def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def root(self) -> dict[str, Any]:
        return self.request("GET", self.service_root)

    def _first_member(self, collection_name: str) -> str:
        root = self.root()
        collection = root.get(collection_name, {}).get("@odata.id") or collection_name
        payload = self.request("GET", collection)
        members = payload.get("Members") or []
        if not members or not members[0].get("@odata.id"):
            raise LookupError(f"Redfish {collection_name} collection has no members")
        return str(members[0]["@odata.id"])

    def system(self) -> dict[str, Any]:
        return self.request("GET", self._first_member("Systems"))

    def chassis(self) -> dict[str, Any]:
        return self.request("GET", self._first_member("Chassis"))

    def manager(self) -> dict[str, Any]:
        return self.request("GET", self._first_member("Managers"))

    def inventory(self) -> dict[str, Any]:
        return {"system": self.system(), "chassis": self.chassis(), "manager": self.manager()}

    def sensors(self) -> dict[str, Any]:
        chassis_uri = self._first_member("Chassis")
        chassis = self.request("GET", chassis_uri)
        sensor_uri = chassis.get("Sensors", {}).get("@odata.id")
        if sensor_uri:
            return self.request("GET", sensor_uri)
        thermal_uri = chassis.get("Thermal", {}).get("@odata.id") or f"{chassis_uri}/Thermal"
        power_uri = chassis.get("Power", {}).get("@odata.id") or f"{chassis_uri}/Power"
        return {"thermal": self.request("GET", thermal_uri), "power": self.request("GET", power_uri)}

    def firmware(self) -> dict[str, Any]:
        root = self.root()
        update_uri = root.get("UpdateService", {}).get("@odata.id") or "UpdateService"
        update = self.request("GET", update_uri)
        inventory_uri = update.get("FirmwareInventory", {}).get("@odata.id")
        return self.request("GET", inventory_uri) if inventory_uri else update

    def reset(self, reset_type: str, *, confirm: bool = False) -> dict[str, Any]:
        if not confirm:
            raise PermissionError("Redfish power actions require confirm=True after explicit user authorization")
        system_uri = self._first_member("Systems")
        system = self.request("GET", system_uri)
        actions = system.get("Actions", {})
        reset = actions.get("#ComputerSystem.Reset", {})
        target = reset.get("target") or reset.get("Target") or f"{system_uri}/Actions/ComputerSystem.Reset"
        allowable = reset.get("ResetType@Redfish.AllowableValues")
        if allowable and reset_type not in allowable:
            raise ValueError(f"ResetType must be one of {allowable}")
        return self.request("POST", target, json={"ResetType": reset_type})

    def boot_once_and_reset(self, boot_target: str, reset_type: str = "ForceRestart", *, confirm: bool = False) -> dict[str, Any]:
        """Reset only after the one-time boot override is accepted and read back."""
        if not confirm:
            raise PermissionError("Boot override and reset require explicit authorization and confirm=True")
        system_uri = self._first_member("Systems")
        system = self.request("GET", system_uri)
        allowable = system.get("Boot", {}).get("BootSourceOverrideTarget@Redfish.AllowableValues")
        if allowable and boot_target not in allowable:
            raise ValueError(f"Boot target must be one of {allowable}")
        requested = {"BootSourceOverrideTarget": boot_target, "BootSourceOverrideEnabled": "Once"}
        self.request("PATCH", system_uri, json={"Boot": requested})
        observed = self.request("GET", system_uri).get("Boot", {})
        if any(observed.get(key) != value for key, value in requested.items()):
            raise RuntimeError("Boot override was not confirmed by BMC; reset was not sent")
        return {"boot": observed, "reset": self.reset(reset_type, confirm=True)}


class IPMIClient:
    def __init__(self, host: str, username: str, password: str, *, interface: str = "lanplus", timeout: int = 30):
        if not host or not username or not password:
            raise ValueError("IPMI host and credentials must be supplied at runtime")
        if os.environ.get("PRIME_NETWORK_MODE") in {"restricted", "internet", "lan", "full"}:
            raise RuntimeError("Direct IPMI/SOL UDP transport is not supported by this OpenShell task's HTTP gateway, even in LAN or Full mode. Use Redfish for management or bmc-html5-kvm for a graphical console; do not retry raw sockets or remove proxy settings.")
        executable = shutil.which("ipmitool")
        if not executable:
            raise RuntimeError("ipmitool is unavailable; use the network-operations profile")
        self.executable, self.host, self.username, self.password = executable, host, username, password
        self.interface, self.timeout = interface, int(timeout)

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env["IPMI_PASSWORD"] = self.password
        return env

    def _command(self, *args: str) -> list[str]:
        return [self.executable, "-I", self.interface, "-H", self.host, "-U", self.username, "-E", *args]

    def _run(self, *args: str, timeout: int | None = None) -> str:
        result = subprocess.run(self._command(*args), env=self._environment(), text=True,
                                capture_output=True, timeout=timeout or self.timeout, check=False)
        if result.returncode:
            message = (result.stderr or result.stdout or "ipmitool failed").strip()
            raise RuntimeError(message)
        return result.stdout.strip()

    def chassis_status(self) -> str:
        return self._run("chassis", "status")

    def sensors(self) -> str:
        return self._run("sensor", "list")

    def firmware(self) -> str:
        return self._run("mc", "info")

    def sol_info(self) -> str:
        """Read SOL configuration without opening or changing a console session."""
        if self.interface != "lanplus":
            raise ValueError("Serial-over-LAN requires the lanplus interface")
        return self._run("sol", "info")

    def sol_session(self, *, columns: int = 100, rows: int = 31) -> "SOLSession":
        """Create an interactive session; use it as a context manager."""
        return SOLSession(self, columns=columns, rows=rows)

    def sol_deactivate(self, *, confirm: bool = False) -> str:
        """Recover a stranded SOL payload, potentially disconnecting another viewer."""
        if not confirm:
            raise PermissionError("Deactivating SOL requires explicit authorization for this BMC")
        if self.interface != "lanplus":
            raise ValueError("Serial-over-LAN requires the lanplus interface")
        return self._run("sol", "deactivate")

    def power(self, action: str, *, confirm: bool = False) -> str:
        allowed = {"on", "off", "cycle", "reset", "soft", "diag"}
        if action not in allowed:
            raise ValueError(f"Power action must be one of {sorted(allowed)}")
        if not confirm:
            raise PermissionError("IPMI power actions require confirm=True after explicit user authorization")
        return self._run("chassis", "power", action)


class SOLSession:
    """Bounded interactive IPMI SOL console with a rendered VT100 screen."""

    KEYS = {
        "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
        "enter": b"\r", "enter-crlf": b"\r\n", "escape": b"\x1b", "tab": b"\t",
        "backspace": b"\x7f", "delete": b"\x1b[3~", "home": b"\x1b[H", "end": b"\x1b[F",
        "f1": b"\x1bOP", "f2": b"\x1bOQ", "f3": b"\x1bOR", "f4": b"\x1bOS",
        "f5": b"\x1b[15~", "f6": b"\x1b[17~", "f7": b"\x1b[18~",
        "f8": b"\x1b[19~", "f9": b"\x1b[20~", "f10": b"\x1b[21~",
        "f11": b"\x1b[23~", "f12": b"\x1b[24~",
    }

    def __init__(self, client: IPMIClient, *, columns: int = 100, rows: int = 31):
        if client.interface != "lanplus":
            raise ValueError("Serial-over-LAN requires the lanplus interface")
        if pyte is None:
            raise RuntimeError("SOL screen support is unavailable; use the network-operations task image")
        if not 40 <= columns <= 160 or not 16 <= rows <= 60:
            raise ValueError("SOL screen dimensions are outside the supported range")
        self.client = client
        self.columns, self.rows = columns, rows
        self._screen = pyte.Screen(columns, rows)
        self._stream = pyte.Stream(self._screen)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._master: int | None = None
        self._process: subprocess.Popen | None = None
        self._line_start = True
        self._active_payload = False
        self._activation_tail = ""

    def __enter__(self) -> "SOLSession":
        if self._process is not None:
            raise RuntimeError("SOL session is already open")
        master, slave = pty.openpty()
        try:
            tty.setraw(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.columns, 0, 0))
            self._process = subprocess.Popen(self.client._command("sol", "activate"),
                                             stdin=slave, stdout=slave, stderr=slave,
                                             env=self.client._environment(), start_new_session=True,
                                             close_fds=True)
            self._master = master
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        return self

    def read(self, *, timeout: float = 1.0, max_bytes: int = 16384) -> dict[str, Any]:
        """Return fresh console output and the current rendered screen."""
        if self._master is None or self._process is None:
            raise RuntimeError("SOL session is not open")
        if not 0 <= timeout <= 10 or not 1 <= max_bytes <= 65536:
            raise ValueError("SOL read timeout or size is outside the supported range")
        deadline = time.monotonic() + timeout
        chunks: list[bytes] = []
        remaining = max_bytes
        while remaining:
            wait = max(0, deadline - time.monotonic())
            ready, _, _ = select.select([self._master], [], [], min(wait, 0.1) if chunks else wait)
            if not ready:
                break
            try:
                data = os.read(self._master, min(remaining, 4096))
            except OSError as error:
                if error.errno == errno.EIO:  # PTY child has exited.
                    break
                raise
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
            if time.monotonic() >= deadline:
                break
        output = self._decoder.decode(b"".join(chunks))
        if output:
            self._stream.feed(output)
            if "SOL Session operational" in self._activation_tail + output:
                self._active_payload = True
            self._activation_tail = output[-64:]
        screen = "\n".join(line.rstrip() for line in self._screen.display).rstrip()
        return {"output": output, "screen": screen, "active": self._process.poll() is None,
                "exitCode": self._process.returncode}

    def _send(self, data: bytes, *, confirm: bool) -> None:
        if not confirm:
            raise PermissionError("SOL input requires explicit authorization for the exact target and action")
        if self._master is None or self._process is None or self._process.poll() is not None:
            raise RuntimeError("SOL session is not active")
        last = data[-1:]
        while data:
            count = os.write(self._master, data)
            data = data[count:]
        self._line_start = last in {b"\r", b"\n"}

    def send_key(self, key: str, *, confirm: bool = False) -> None:
        """Send one named firmware/boot key after exact-action authorization."""
        value = self.KEYS.get(str(key).lower())
        if value is None:
            raise ValueError(f"Unsupported SOL key; choose one of {sorted(self.KEYS)}")
        self._send(value, confirm=confirm)

    def send_text(self, value: str, *, confirm: bool = False) -> None:
        """Send bounded printable text; use send_key for control characters."""
        if not isinstance(value, str) or not value or len(value) > 512 or any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise ValueError("SOL text must be 1–512 printable ASCII characters without controls")
        if self._line_start and value.startswith("~."):
            raise ValueError("SOL text cannot start with ipmitool's detach sequence")
        self._send(value.encode("ascii"), confirm=confirm)

    def close(self) -> None:
        process, master = self._process, self._master
        self._process, self._master = None, None
        if process is None or master is None:
            return
        forced = False
        try:
            if process.poll() is None and self._line_start:
                try:
                    os.write(master, b"~.")  # ipmitool's in-band SOL exit sequence.
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    forced = True
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
        finally:
            os.close(master)
        if forced and self._active_payload:
            # Only release a payload whose successful activation we observed;
            # never clear a pre-existing SOL viewer after a failed activation.
            try:
                self.client._run("sol", "deactivate", timeout=5)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass

    def __exit__(self, *_: object) -> None:
        self.close()


class HPEBMC(RedfishClient):
    """Compatibility wrapper for the original Prime-created HPEBMC API."""

    def __init__(self, bmc_ip: str, username: str, password: str, *, verify_ssl: bool = False, timeout: int = 30):
        super().__init__(bmc_ip, username, password, verify_tls=verify_ssl, timeout=timeout)

    def get_system_status(self) -> dict[str, Any]:
        return self.system()

    def get_power_state(self) -> dict[str, Any]:
        return self.system()

    def get_sensors(self) -> dict[str, Any]:
        return self.sensors()

    def get_sensor_readings(self) -> dict[str, Any]:
        return self.sensors()

    def get_firmware(self) -> dict[str, Any]:
        return self.firmware()

    def get_inventory(self) -> dict[str, Any]:
        return self.inventory()

    def set_power_state(self, state: str, *, confirm: bool = False) -> dict[str, Any]:
        reset_types = {"On": "On", "Off": "ForceOff", "Reset": "ForceRestart", "Push": "GracefulShutdown"}
        if state not in reset_types:
            raise ValueError(f"Power state must be one of {sorted(reset_types)}")
        return self.reset(reset_types[state], confirm=confirm)


class IPMIBMC(IPMIClient):
    """Compatibility wrapper for the original Prime-created IPMIBMC API."""

    def __init__(self, bmc_ip: str, username: str, password: str, *, timeout: int = 30):
        super().__init__(bmc_ip, username, password, timeout=timeout)

    def get_system_info(self) -> str:
        return self.chassis_status()

    def get_sensors(self) -> str:
        return self.sensors()

    def get_firmware(self) -> str:
        return self.firmware()

    def set_power_state(self, state: str, *, confirm: bool = False) -> str:
        normalized = "cycle" if state.lower() == "powercycle" else state.lower()
        return self.power(normalized, confirm=confirm)


def run() -> dict[str, Any]:
    return {"status": "ready", "ipmitool": shutil.which("ipmitool"), "mutationsRequireConfirmation": True}
