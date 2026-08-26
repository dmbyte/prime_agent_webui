#!/usr/bin/env python3
import base64
import getpass
import hashlib
import json
import os
import pwd
import secrets
import tempfile
from pathlib import Path

SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_BYTES = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024


def main():
    username = os.environ.get("PRIME_AUTH_USER") or pwd.getpwuid(os.getuid()).pw_name
    account = pwd.getpwnam(username)
    if os.getuid() != account.pw_uid:
        raise SystemExit(f"Run this command as {username}, without sudo.")
    path = Path(account.pw_dir) / ".config/prime-agent/web-auth.json"
    first = getpass.getpass("New Prime WebUI password: ")
    second = getpass.getpass("Confirm Prime WebUI password: ")
    if first != second:
        raise SystemExit("Passwords did not match; nothing was changed.")
    encoded = first.encode("utf-8")
    if len(first) < 12:
        raise SystemExit("Use at least 12 characters; nothing was changed.")
    if len(encoded) > 1024:
        raise SystemExit("Password is too long; nothing was changed.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        encoded,
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_BYTES,
        maxmem=SCRYPT_MAXMEM,
    )
    record = {"role": "admin", "enabled": True, "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "salt": base64.b64encode(salt).decode("ascii"), "hash": base64.b64encode(digest).decode("ascii")}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    if existing.get("version") == 2 and isinstance(existing.get("users"), dict):
        previous = existing["users"].get(username, {})
        record["createdAt"] = previous.get("createdAt") or int(__import__("time").time())
        record["role"] = previous.get("role", "admin")
        value = existing
        value["users"][username] = record
    else:
        record["createdAt"] = int(__import__("time").time())
        value = {"version": 2, "users": {username: record}}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".web-auth.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    first = second = ""
    print("Prime WebUI password updated. Existing sessions remain valid until expiry or service restart.")


if __name__ == "__main__":
    main()
