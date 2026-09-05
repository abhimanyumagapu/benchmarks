"""Unified-diff helpers shared by bake (bug patch) and score (fix patch)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HDR = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)")


def touched_files(patch: str) -> list[str]:
    files = []
    for line in patch.splitlines():
        m = _HDR.match(line)
        if m and m.group(1) != "/dev/null" and m.group(1) not in files:
            files.append(m.group(1))
    return files


def apply(tree: Path, patch: str) -> None:
    """Apply a unified diff at the tree root (works with or without .git). Raises CalledProcessError."""
    subprocess.run(
        ["git", "apply", "-"], input=patch, text=True, check=True, capture_output=True, cwd=str(tree)
    )
