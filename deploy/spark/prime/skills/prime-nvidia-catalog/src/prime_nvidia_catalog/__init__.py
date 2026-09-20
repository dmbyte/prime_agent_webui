"""Search and read the pinned, locally installed NVIDIA skill catalog."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CATALOG_ROOT = Path.home() / ".prime/agent/catalogs/nvidia"


def _manifest() -> dict[str, Any]:
    return json.loads((CATALOG_ROOT / "manifest.json").read_text())


def list_skills() -> list[dict[str, str]]:
    return [{"name": row["name"], "description": row["description"]} for row in _manifest()["skills"]]


def search_skills(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not terms:
        return []
    matches = []
    for row in _manifest()["skills"]:
        name = row["name"].lower()
        text = f"{name} {row['description'].lower()}"
        score = sum(5 if term in name else 1 for term in terms if term in text)
        if score:
            matches.append({"name": row["name"], "description": row["description"], "score": score})
    return sorted(matches, key=lambda item: (-item["score"], item["name"]))[: max(1, min(int(limit), 20))]


def read_skill(name: str) -> str:
    rows = {row["name"]: row for row in _manifest()["skills"]}
    if name not in rows:
        raise KeyError(f"Unknown NVIDIA skill: {name}")
    path = (CATALOG_ROOT / "skills" / rows[name]["directory"] / "SKILL.md").resolve()
    skills_root = (CATALOG_ROOT / "skills").resolve()
    if skills_root not in path.parents:
        raise RuntimeError("Catalog manifest contains an unsafe path")
    return path.read_text()


def run(query: str) -> list[dict[str, Any]]:
    return search_skills(query)
