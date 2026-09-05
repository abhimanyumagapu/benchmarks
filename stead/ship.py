"""Tar one case folder for handing out, with its tree materialized from the image. Gold lives
elsewhere, so nothing to exclude."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path

from .case import Case
from .tree import materialize


def ship(case_dir: Path, gold_dir: Path, dist: Path) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    tar = dist / f"{case_dir.name}.tar.gz"
    case = Case.load(case_dir / "case.yaml")
    tmp = Path(tempfile.mkdtemp(prefix="stead-ship-"))
    try:
        materialize(case.image, (gold_dir / "bug.patch").read_text(), tmp / "tree")
        with tarfile.open(tar, "w:gz") as t:
            t.add(case_dir, arcname=case_dir.name)
            t.add(tmp / "tree", arcname=f"{case_dir.name}/tree")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return tar
