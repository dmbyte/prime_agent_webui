"""Standards-based Redfish and ipmitool clients with mutation confirmation gates."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


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


class IPMIClient:
    def __init__(self, host: str, username: str, password: str, *, interface: str = "lanplus", timeout: int = 30):
        if not host or not username or not password:
            raise ValueError("IPMI host and credentials must be supplied at runtime")
        executable = shutil.which("ipmitool")
        if not executable:
            raise RuntimeError("ipmitool is unavailable; use the network-operations profile")
        self.executable, self.host, self.username, self.password = executable, host, username, password
        self.interface, self.timeout = interface, int(timeout)

    def _run(self, *args: str) -> str:
        env = os.environ.copy()
        env["IPMI_PASSWORD"] = self.password
        command = [self.executable, "-I", self.interface, "-H", self.host, "-U", self.username, "-E", *args]
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=self.timeout, check=False)
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

    def power(self, action: str, *, confirm: bool = False) -> str:
        allowed = {"on", "off", "cycle", "reset", "soft", "diag"}
        if action not in allowed:
            raise ValueError(f"Power action must be one of {sorted(allowed)}")
        if not confirm:
            raise PermissionError("IPMI power actions require confirm=True after explicit user authorization")
        return self._run("chassis", "power", action)


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
