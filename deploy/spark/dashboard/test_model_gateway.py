#!/usr/bin/env python3
import importlib.util
import ipaddress
import socket
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

path = Path(__file__).parents[1] / "container" / "model_gateway.py"
spec = importlib.util.spec_from_file_location("model_gateway", path)
gateway = importlib.util.module_from_spec(spec); spec.loader.exec_module(gateway)

def answer(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (address, 0))]

class GatewayPolicyTests(unittest.TestCase):
    def check(self, address, mode):
        with mock.patch.object(socket, "getaddrinfo", return_value=answer(address)):
            return gateway.allowed_address("example.test", mode)

    def test_internet_rejects_private_loopback_link_local_and_metadata(self):
        for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254"):
            self.assertEqual(self.check(address, "internet"), [])

    def test_internet_allows_public_and_lan_allows_private(self):
        self.assertEqual(self.check("1.1.1.1", "internet"), ["1.1.1.1"])
        self.assertEqual(self.check("192.168.1.50", "lan"), ["192.168.1.50"])

    def test_lan_still_rejects_loopback_and_link_local(self):
        self.assertEqual(self.check("127.0.0.1", "lan"), [])
        self.assertEqual(self.check("169.254.169.254", "lan"), [])

    def test_secure_json_rejects_group_readable_and_symlink_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "auth.json"
            credential.write_text(json.dumps({"openai-codex": {"access": "x"}}))
            os.chmod(credential, 0o640)
            with self.assertRaises(RuntimeError):
                gateway.secure_json(credential)
            os.chmod(credential, 0o600)
            link = root / "link.json"
            link.symlink_to(credential)
            with self.assertRaises(RuntimeError):
                gateway.secure_json(link)

    def test_secure_json_accepts_owner_only_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "auth.json"
            credential.write_text('{"ok":true}')
            os.chmod(credential, 0o600)
            self.assertEqual(gateway.secure_json(credential), {"ok": True})

    def test_personal_codex_credential_overrides_global_fallback(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(gateway, "ROOT", Path(directory)):
            root = Path(directory) / "credentials"
            personal = root / "users" / "alice"
            global_root = root / "global"
            personal.mkdir(parents=True); global_root.mkdir(parents=True)
            template = lambda access: {"openai-codex": {"access": access, "refresh": "refresh", "accountId": "account", "expires": 4102444800000}}
            for path, value in ((personal / "auth.json", template("personal")), (global_root / "auth.json", template("global"))):
                path.write_text(json.dumps(value)); os.chmod(path, 0o600)
            self.assertEqual(gateway.credential("alice")["access"], "personal")
            self.assertEqual(gateway.credential("bob")["access"], "global")

if __name__ == "__main__": unittest.main()
