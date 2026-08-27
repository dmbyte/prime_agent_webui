#!/usr/bin/env python3
"""Group-restricted Unix broker owning the rootless Podman boundary."""
import grp, json, os, pwd, selectors, socket, struct, subprocess, threading

SOCKET = "\0prime-runner-broker-v1"
LAUNCHER = "/usr/local/libexec/prime-runner-launch"

def authorized(conn):
    _, uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    user = pwd.getpwuid(uid)
    web = grp.getgrnam("prime-web")
    return gid == web.gr_gid or user.pw_name in web.gr_mem

def handle(conn):
    process = None
    try:
        if not authorized(conn):
            return
        first = bytearray()
        while b"\n" not in first and len(first) <= 32768:
            chunk = conn.recv(4096)
            if not chunk:
                return
            first.extend(chunk)
        if b"\n" not in first:
            return
        encoded, remainder = bytes(first).split(b"\n", 1)
        process = subprocess.Popen([LAUNCHER, encoded.decode("ascii")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if remainder:
            process.stdin.write(remainder)
            process.stdin.flush()
        selector = selectors.DefaultSelector()
        selector.register(conn, selectors.EVENT_READ, "client")
        selector.register(process.stdout, selectors.EVENT_READ, "runner")
        while True:
            for key, _ in selector.select(timeout=1):
                if key.data == "client":
                    data = conn.recv(65536)
                    if data:
                        process.stdin.write(data); process.stdin.flush()
                    else:
                        process.stdin.close(); selector.unregister(conn)
                else:
                    data = os.read(process.stdout.fileno(), 65536)
                    if data:
                        conn.sendall(data)
                    else:
                        selector.unregister(process.stdout)
                        returncode = process.wait()
                        if returncode:
                            event = json.dumps({"type": "broker_exit", "exitCode": returncode}, separators=(",", ":"))
                            conn.sendall(event.encode() + b"\n")
                        return
    except (BrokenPipeError, ConnectionError, OSError, ValueError, UnicodeError):
        pass
    finally:
        conn.close()
        if process and process.poll() is None:
            process.terminate()

def main():
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET)
    server.listen(16)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    main()
