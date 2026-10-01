#!/usr/bin/env python3
"""Bounded loopback-to-Unix relay; all egress policy stays in the host gateway."""

import errno
import select
import socket
import sys
import threading
import time

ENDPOINTS = {
    "model": (31000, "/run/prime-gateway/model.sock"),
    "network": (31080, "/run/prime-gateway/network.sock"),
}
RECOVERABLE_ACCEPT = {errno.EACCES, errno.EPERM, errno.ECONNABORTED, errno.EINTR, errno.EPROTO}


def accept_client(listener, stop, report=print):
    """A rejected/cancelled connection must not take down the shared listener."""
    failures = 0
    while not stop.is_set():
        try:
            return listener.accept()[0]
        except socket.timeout:
            continue
        except OSError as error:
            if error.errno not in RECOVERABLE_ACCEPT:
                raise
            failures += 1
            if failures == 1 or failures % 100 == 0:
                report(f"gateway relay rejected connection (errno={error.errno}); listener retained")
            # Prevent a permanent failure from busy-spinning. Never change policy.
            stop.wait(min(.05 * failures, 1))
    return None


def bridge(client, upstream_path):
    with client, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
        upstream.settimeout(30)
        upstream.connect(upstream_path)
        client.settimeout(30)
        streams = [client, upstream]
        last_data = time.monotonic()
        while streams and time.monotonic() - last_data < 1800:
            readable, _, _ = select.select(streams, [], [], 1)
            for source in readable:
                target = upstream if source is client else client
                data = source.recv(65536)
                if not data:
                    streams.remove(source)
                    target.shutdown(socket.SHUT_WR)
                    continue
                target.sendall(data)
                last_data = time.monotonic()


def serve(kind):
    port, upstream_path = ENDPOINTS[kind]
    stop = threading.Event()
    capacity = threading.BoundedSemaphore(64)

    def report(message):
        print(f"{kind}: {message}", file=sys.stderr, flush=True)

    def handle(client):
        try:
            bridge(client, upstream_path)
        except OSError as error:
            # Do not log requests, destinations, or credentials.
            report(f"connection ended (errno={error.errno})")
        finally:
            client.close()
            capacity.release()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(64)
        listener.settimeout(1)
        while not stop.is_set():
            client = accept_client(listener, stop, report)
            if client is None:
                break
            if not capacity.acquire(blocking=False):
                client.close()
                continue
            try:
                threading.Thread(target=handle, args=(client,), daemon=True).start()
            except BaseException:
                client.close()
                capacity.release()
                raise


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ENDPOINTS:
        raise SystemExit("Usage: gateway_relay.py model|network")
    serve(sys.argv[1])
