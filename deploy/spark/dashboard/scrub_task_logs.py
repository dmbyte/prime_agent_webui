#!/usr/bin/env python3
"""Remove a leaked BMC auth literal from owner-only historical WebUI logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from api_v2 import safe_runtime_line


AUTH_PAIR = re.compile(r"\bauth\s*=\s*\(\s*(['\"])([^'\"\r\n]{1,128})\1\s*,\s*(['\"])([^'\"\r\n]{12,256})\3\s*\)")


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child)


def auth_literals(seed_log: Path) -> set[str]:
    found = set()
    with seed_log.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                values = text_values(json.loads(line))
                for value in values:
                    found.update(match.group(4) for match in AUTH_PAIR.finditer(value))
            except (json.JSONDecodeError, TypeError, ValueError):
                found.update(match.group(4) for match in AUTH_PAIR.finditer(line))
    if not found:
        raise ValueError("No long literal auth pair found in the selected log")
    return found


def scrub_file(path: Path, secrets: set[str]) -> bool:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError(f"Refusing unexpected log permissions or file type: {path.name}")
    with path.open(encoding="utf-8", errors="replace") as handle:
        if not any(any(secret in line for secret in secrets) for line in handle):
            return False
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}.scrub-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output, path.open(encoding="utf-8", errors="replace") as source:
            os.fchmod(output.fileno(), 0o600)
            for line in source:
                for secret in secrets:
                    line = line.replace(secret, "[REDACTED_CREDENTIAL]")
                output.write(safe_runtime_line(line) + "\n")
            output.flush()
            os.fsync(output.fileno())
        with open(temporary, encoding="utf-8") as check:
            if any(any(secret in line for secret in secrets) for line in check):
                raise RuntimeError(f"Credential remained after scrubbing {path.name}")
        os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--seed-log", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    seed_log = args.seed_log.resolve(strict=True)
    if seed_log.parent != directory or not re.fullmatch(r"[a-f0-9]{32}\.log", seed_log.name):
        raise ValueError("Seed log must be a task log in the selected directory")
    secrets = auth_literals(seed_log)
    changed = 0
    for path in sorted(directory.glob("*.log")):
        if not re.fullmatch(r"[a-f0-9]{32}\.log", path.name):
            continue
        changed += scrub_file(path, secrets)
    print(f"Scrubbed {changed} owner-only task logs; removed {len(secrets)} credential literal(s).")


if __name__ == "__main__":
    main()
