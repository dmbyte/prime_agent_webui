import errno
import importlib.util
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("gateway_relay", Path(__file__).parent.parent / "container/gateway_relay.py")
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def test_rejected_accept_does_not_kill_listener(self):
        listener, stop, client = mock.Mock(), mock.Mock(), mock.Mock()
        stop.is_set.return_value = False
        listener.accept.side_effect = [PermissionError(errno.EACCES, "denied"),
                                       ConnectionAbortedError(errno.ECONNABORTED, "aborted"),
                                       (client, ("127.0.0.1", 1))]
        self.assertIs(relay.accept_client(listener, stop, mock.Mock()), client)
        self.assertEqual(listener.accept.call_count, 3)
        self.assertEqual(stop.wait.call_count, 2)

    def test_unrecoverable_listener_failure_is_not_hidden(self):
        listener = mock.Mock()
        listener.accept.side_effect = OSError(errno.EBADF, "bad descriptor")
        with self.assertRaises(OSError):
            relay.accept_client(listener, threading.Event())

    def test_bidirectional_stream_preserves_half_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "upstream.sock")
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(path)
                server.listen(1)
                client, accepted = socket.socketpair()
                worker = threading.Thread(target=relay.bridge, args=(accepted, path))
                worker.start()
                upstream, _ = server.accept()
                with client, upstream:
                    client.settimeout(3)
                    upstream.settimeout(3)
                    client.sendall(b"request")
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(upstream.recv(7), b"request")
                    self.assertEqual(upstream.recv(1), b"")
                    upstream.sendall(b"response")
                    upstream.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(8), b"response")
                    self.assertEqual(client.recv(1), b"")
                worker.join(3)
                self.assertFalse(worker.is_alive())

    def test_only_fixed_gateway_endpoints_exist(self):
        self.assertEqual(relay.ENDPOINTS, {
            "model": (31000, "/run/prime-gateway/model.sock"),
            "network": (31080, "/run/prime-gateway/network.sock")})


if __name__ == "__main__":
    unittest.main()
