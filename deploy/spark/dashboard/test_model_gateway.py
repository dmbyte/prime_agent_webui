#!/usr/bin/env python3
import socket
import sys
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


if __name__ == "__main__":
    unittest.main()
