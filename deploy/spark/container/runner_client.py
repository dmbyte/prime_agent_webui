#!/usr/bin/env python3
"""Unprivileged full-duplex client for the local rootless runner broker."""
import os, selectors, socket, sys

SOCKET = "\0prime-runner-broker-v1"

def main():
    if len(sys.argv) != 2 or len(sys.argv[1]) > 32768:
        raise SystemExit(2)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET)
    sock.sendall(sys.argv[1].encode("ascii") + b"\n")
    selector = selectors.DefaultSelector()
    selector.register(sock, selectors.EVENT_READ, "socket")
    selector.register(sys.stdin.buffer, selectors.EVENT_READ, "stdin")
    while True:
        for key, _ in selector.select():
            if key.data == "socket":
                data = sock.recv(65536)
                if not data:
                    return
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                data = os.read(sys.stdin.fileno(), 65536)
                if data:
                    sock.sendall(data)
                else:
                    selector.unregister(sys.stdin.buffer)
                    sock.shutdown(socket.SHUT_WR)

if __name__ == "__main__":
    main()
