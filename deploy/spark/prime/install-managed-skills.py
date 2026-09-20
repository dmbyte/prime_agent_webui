#!/usr/bin/env python3
"""Install reviewed Prime skills and a pinned, lazy NVIDIA catalog atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

NVIDIA_COMMIT = "fd9f1466ff8a39178e488981e8b5118709392949"
NVIDIA_SKILL_COUNT = 366
BUNDLED_SKILLS = ("bmc-headless-browser", "ipmi-redfish-bmc", "prime-nvidia-catalog")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--bundled", type=Path, required=True)
    parser.add_argument("--nvidia-source", type=Path)
    return parser.parse_args()


def frontmatter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"Missing YAML frontmatter: {path}")
    block = text.split("\n---\n", 1)[0][4:]
    lines = block.splitlines()
    values: dict[str, str] = {}
    for index, line in enumerate(lines):
        key, separator, value = line.partition(":")
        if separator and key in {"name", "description"}:
            value = value.strip().strip('"\'')
            if key == "description" and value in {">", "|"}:
                continuation = []
                for candidate in lines[index + 1:]:
                    if candidate and not candidate[0].isspace():
                        break
                    if candidate.strip():
                        continuation.append(candidate.strip())
                value = " ".join(continuation)
            values[key] = value
    name, description = values.get("name", ""), values.get("description", "")
    if not NAME_RE.fullmatch(name) or not description:
        raise ValueError(f"Invalid skill metadata: {path}")
    return name, description


def validate_tree(root: Path, expected_count: int | None = None, include: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    rows = []
    directories = sorted(path for path in root.iterdir() if path.is_dir() and (include is None or path.name in include))
    if include is not None and {path.name for path in directories} != set(include):
        raise ValueError("One or more distribution-managed skills are missing")
    for directory in directories:
        files = []
        total = 0
        digest = hashlib.sha256()
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlinks are not accepted in managed skills: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            content = path.read_bytes()
            files.append(path)
            total += len(content)
            digest.update(relative.encode() + b"\0" + content + b"\0")
        if not files or len(files) > 200 or total > 20 * 1024 * 1024:
            raise ValueError(f"Skill exceeds file or size limits: {directory.name}")
        name, description = frontmatter(directory / "SKILL.md")
        rows.append({"name": name, "directory": directory.name, "description": description, "sha256": digest.hexdigest()})
    if expected_count is not None and len(rows) != expected_count:
        raise ValueError(f"Expected {expected_count} skills, found {len(rows)}")
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Duplicate skill names are not accepted")
    return rows


def atomic_replace(source: Path, target: Path, recovery: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage-", dir=target.parent))
    shutil.rmtree(staged)
    shutil.copytree(source, staged)
    if target.exists():
        recovery.parent.mkdir(parents=True, exist_ok=True)
        os.replace(target, recovery)
    os.replace(staged, target)


def main() -> None:
    args = arguments()
    if os.geteuid() != 0:
        raise SystemExit("Run this helper through sudo")
    account = pwd.getpwnam("prime-runner")
    state = Path("/var/lib/prime-runner/users") / args.owner / "prime/agent"
    skills_target = state / "skills"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recovery_root = state / "recovery/managed-skills" / timestamp
    touched: list[Path] = []

    bundled_rows = validate_tree(args.bundled, len(BUNDLED_SKILLS), BUNDLED_SKILLS)
    for row in bundled_rows:
        source = args.bundled / row["directory"]
        target = skills_target / row["directory"]
        atomic_replace(source, target, recovery_root / row["directory"])
        touched.append(target)

    if args.nvidia_source:
        checkout = args.nvidia_source.resolve()
        commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if commit != NVIDIA_COMMIT:
            raise ValueError(f"NVIDIA skills checkout must be pinned to {NVIDIA_COMMIT}, found {commit}")
        catalog_rows = validate_tree(checkout / "skills", NVIDIA_SKILL_COUNT)
        stage = Path(tempfile.mkdtemp(prefix=".nvidia-catalog-", dir=state))
        try:
            shutil.copytree(checkout / "skills", stage / "skills")
            for filename in ("README.md", "LICENSE-APACHE", "LICENSE-CC-BY-4.0"):
                shutil.copy2(checkout / filename, stage / filename)
            manifest = {
                "schemaVersion": 1,
                "source": "https://github.com/NVIDIA/skills",
                "commit": NVIDIA_COMMIT,
                "installedAt": datetime.now(timezone.utc).isoformat(),
                "count": len(catalog_rows),
                "skills": catalog_rows,
            }
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            target = state / "catalogs/nvidia"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                destination = recovery_root / "nvidia-catalog"
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, destination)
            os.replace(stage, target)
            touched.append(target)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    if recovery_root.exists():
        touched.append(recovery_root)
    for root in touched:
        for path in [root, *root.rglob("*")]:
            os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
    print(f"Installed {len(bundled_rows)} managed Prime skills", end="")
    if args.nvidia_source:
        print(f" and {NVIDIA_SKILL_COUNT} pinned NVIDIA catalog skills")
    else:
        print()


if __name__ == "__main__":
    main()
