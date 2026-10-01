"""Interactive SOL tests use a local pseudo-terminal, never a real BMC."""

import importlib.util
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "skills/ipmi-redfish-bmc/src/ipmi_redfish_bmc/__init__.py"


def load_skill():
    fake_requests = types.ModuleType("requests")
    fake_pyte = types.ModuleType("pyte")

    class Screen:
        def __init__(self, columns, rows):
            self.display = [""] * rows

    class Stream:
        def __init__(self, screen):
            self.screen = screen

        def feed(self, text):
            self.screen.display[0] += text

    fake_pyte.Screen = Screen
    fake_pyte.Stream = Stream
    spec = importlib.util.spec_from_file_location("prime_sol_test_module", SOURCE)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"requests": fake_requests, "pyte": fake_pyte}):
        spec.loader.exec_module(module)
    return module


class SOLSkillTests(unittest.TestCase):
    def test_openshell_http_gateway_fails_fast_for_unsupported_udp(self):
        with mock.patch.dict(self.skill.os.environ, {"PRIME_NETWORK_MODE": "full"}):
            with self.assertRaisesRegex(RuntimeError, "Direct IPMI/SOL UDP transport is not supported"):
                self.skill.IPMIClient("bmc.example", "operator", "private")

    def setUp(self):
        self.skill = load_skill()
        self.which = mock.patch.object(self.skill.shutil, "which", return_value="/fake/ipmitool")
        self.which.start()
        self.addCleanup(self.which.stop)

    def test_boot_override_never_resets_after_failed_patch_or_readback(self):
        bmc = object.__new__(self.skill.RedfishClient)
        with mock.patch.object(bmc, "_first_member", return_value="/redfish/v1/Systems/1/"), mock.patch.object(bmc, "reset", return_value={"ok": True}) as reset:
            with mock.patch.object(bmc, "request", side_effect=[{"Boot": {}}, RuntimeError("HTTP 400")]) as request:
                with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                    bmc.boot_once_and_reset("Cd", confirm=True)
                reset.assert_not_called()
                self.assertEqual(request.call_count, 2)
            with mock.patch.object(bmc, "request", side_effect=[{"Boot": {}}, {}, {"Boot": {"BootSourceOverrideTarget": "Cd", "BootSourceOverrideEnabled": "Disabled"}}]):
                with self.assertRaisesRegex(RuntimeError, "not confirmed"):
                    bmc.boot_once_and_reset("Cd", confirm=True)
                reset.assert_not_called()
            with mock.patch.object(bmc, "request", side_effect=[{"Boot": {}}, {}, {"Boot": {"BootSourceOverrideTarget": "Cd", "BootSourceOverrideEnabled": "Once"}}]):
                result = bmc.boot_once_and_reset("Cd", confirm=True)
                self.assertEqual(result["reset"], {"ok": True})
                reset.assert_called_once_with("ForceRestart", confirm=True)
            with self.assertRaises(PermissionError):
                bmc.boot_once_and_reset("Cd")

    def test_sol_info_and_recovery_are_lanplus_and_confirmation_gated(self):
        bmc = self.skill.IPMIClient("bmc.example", "operator", "private")
        with mock.patch.object(bmc, "_run", return_value="enabled") as command:
            self.assertEqual(bmc.sol_info(), "enabled")
            command.assert_called_once_with("sol", "info")
            with self.assertRaises(PermissionError):
                bmc.sol_deactivate()
            self.assertEqual(bmc.sol_deactivate(confirm=True), "enabled")
            command.assert_called_with("sol", "deactivate")
        legacy = self.skill.IPMIClient("bmc.example", "operator", "private", interface="lan")
        with self.assertRaisesRegex(ValueError, "lanplus"):
            legacy.sol_info()
        with self.assertRaisesRegex(ValueError, "lanplus"):
            legacy.sol_session()

    def test_interactive_pty_reads_boot_screen_and_sends_authorized_keys(self):
        bmc = self.skill.IPMIClient("bmc.example", "operator", "private")
        real_popen = subprocess.Popen
        captured = {}
        child = (
            "import os,sys\n"
            "os.write(1,b'SOL Session operational\\r\\nBIOS MENU\\r\\n')\n"
            "while True:\n"
            " data=os.read(0,1024)\n"
            " if not data or b'~.' in data: break\n"
            " os.write(1,b'KEYS='+data.hex().encode()+b'\\r\\n')\n"
        )

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured["environment"] = kwargs["env"]
            return real_popen([sys.executable, "-u", "-c", child], **kwargs)

        with mock.patch.object(self.skill.subprocess, "Popen", side_effect=fake_popen):
            with bmc.sol_session() as sol:
                first = sol.read(timeout=2)
                self.assertIn("BIOS MENU", first["screen"])
                self.assertTrue(first["active"])
                with self.assertRaises(PermissionError):
                    sol.send_key("f9")
                with self.assertRaises(ValueError):
                    sol.send_text("bad\ncommand", confirm=True)
                with self.assertRaises(ValueError):
                    sol.send_text("~.", confirm=True)
                sol.send_key("f9", confirm=True)
                second = sol.read(timeout=2)
                self.assertIn("KEYS=1b5b32307e", second["output"])
                sol.send_text("boot option", confirm=True)
                sol.send_key("enter", confirm=True)
                third = sol.read(timeout=2)
                self.assertIn("boot option".encode().hex(), third["output"])
            self.assertIsNone(sol._process)
            self.assertIsNone(sol._master)
        self.assertEqual(captured["command"][-2:], ["sol", "activate"])
        self.assertIn("-E", captured["command"])
        self.assertNotIn("private", captured["command"])
        self.assertEqual(captured["environment"]["IPMI_PASSWORD"], "private")

    def test_forced_close_only_deactivates_observed_payload(self):
        bmc = self.skill.IPMIClient("bmc.example", "operator", "private")
        real_popen = subprocess.Popen
        child = "import os,time; os.write(1,b'SOL Session operational\\n'); time.sleep(30)"

        def fake_popen(_command, **kwargs):
            return real_popen([sys.executable, "-u", "-c", child], **kwargs)

        with mock.patch.object(self.skill.subprocess, "Popen", side_effect=fake_popen), mock.patch.object(bmc, "_run", return_value="") as command:
            sol = bmc.sol_session()
            with sol:
                sol.read(timeout=2)
                sol.send_key("up", confirm=True)
            command.assert_called_once_with("sol", "deactivate", timeout=5)


if __name__ == "__main__":
    unittest.main()
