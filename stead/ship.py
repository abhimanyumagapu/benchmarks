"""Tar one case folder for handing out. Gold lives elsewhere, so nothing to exclude."""

from __future__ import annotations

import tarfile
from pathlib import Path


def ship(case_dir: Path, dist: Path) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    tar = dist / f"{case_dir.name}.tar.gz"
    with tarfile.open(tar, "w:gz") as t:
        t.add(case_dir, arcname=case_dir.name)
    return tar
