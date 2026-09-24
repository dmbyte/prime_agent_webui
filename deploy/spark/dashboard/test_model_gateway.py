#!/usr/bin/env python3
import socket
import sys
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "container"))
import model_gateway


class ModelGatewayNetworkTests(unittest.TestCase):
    def addresses(self, mode):
        rows = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.2.3.4", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        with mock.patch.object(model_gateway.socket, "getaddrinfo", return_value=rows):
            return model_gateway.allowed_address("example.test", mode)

    def test_internet_is_public_only(self):
        self.assertEqual(self.addresses("internet"), ["8.8.8.8"])

    def test_lan_is_private_only(self):
        self.assertEqual(self.addresses("lan"), ["10.2.3.4"])

    def test_full_allows_public_and_private_but_not_host_loopback(self):
        self.assertEqual(self.addresses("full"), ["8.8.8.8", "10.2.3.4"])


class ModelGatewayCredentialTests(unittest.TestCase):
    def test_reused_refresh_token_has_actionable_safe_error(self):
        class Response:
            status = 401
            def read(self, _limit):
                return json.dumps({"error": {"code": "refresh_token_reused", "message": "secret upstream detail"}}).encode()
        class Connection:
            def request(self, *_args, **_kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "credentials/global/auth.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"openai-codex": {"access": "a", "refresh": "r", "accountId": "id", "expires": 1}}))
            os.chmod(path, 0o600)
            with mock.patch.object(model_gateway, "ROOT", root), mock.patch.object(model_gateway.http.client, "HTTPSConnection", return_value=Connection()):
                with self.assertRaisesRegex(model_gateway.CodexCredentialError, "run /login"):
                    model_gateway.credential("alice")


if __name__ == "__main__":
    unittest.main()
