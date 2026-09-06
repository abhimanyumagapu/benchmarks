"""Two ways a case leaves this machine.

`ship` tars one case with its tree materialized, for a closed tool that cannot run our harness. It
carries no gold: the recipient is being asked the question, not shown the answer.

`ship_set` tars every baked case of one core together with its gold, for someone running the whole
benchmark themselves. Baking is minutes per bug, so this is the download that skips it. The tree is
not in it -- that comes from the image, which each case records -- so cases and images travel apart.
"""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from .case import Case
from .gold import Gold
from .solve import add_tools
from .tree import materialize


def ship(case_dir: Path, gold_dir: Path, dist: Path) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    tar = dist / f"{case_dir.name}.tar.gz"
    case = Case.load(case_dir / "case.yaml")
    tmp = Path(tempfile.mkdtemp(prefix="stead-ship-"))
    try:
        materialize(case.image, (gold_dir / "bug.patch").read_text(), tmp / "tree")
        add_tools(tmp, case.repo)
        with tarfile.open(tar, "w:gz") as t:
            t.add(case_dir, arcname=case_dir.name)
            t.add(tmp / "tree", arcname=f"{case_dir.name}/tree")
            t.add(tmp / "tools", arcname=f"{case_dir.name}/tools")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return tar


def _member(tar: tarfile.TarFile, name: str, text: str) -> None:
    """Write `text` into the archive as `name`, without staging it on disk first."""
    raw = text.encode()
    info = tarfile.TarInfo(name)
    info.size = len(raw)
    tar.addfile(info, io.BytesIO(raw))


def ship_set(repo: str, cases: list[Path], gold_root: Path, dist: Path) -> Path:
    """One core's baked cases and their gold, as a tarball that unpacks at the bench root.

    Paths inside are `cases/<repo>/<id>/` and `gold/<repo>/<id>/`, so `tar xzf` in the bench root
    puts everything where the harness already looks and `stead check --all` proves it landed intact.
    """
    dist.mkdir(parents=True, exist_ok=True)
    tar_path = dist / f"stead-cases-{repo}.tar.gz"
    index = []
    with tarfile.open(tar_path, "w:gz") as tar:
        for case_dir in sorted(cases):
            gold_dir = Path(gold_root) / repo / case_dir.name
            case = Case.load(case_dir / "case.yaml")
            tar.add(case_dir, arcname=f"cases/{repo}/{case_dir.name}")
            tar.add(gold_dir, arcname=f"gold/{repo}/{case_dir.name}")
            index.append(
                {
                    "id": case.id,
                    "test": case.test,
                    "class": Gold.load(gold_dir / "gold.yaml").klass,
                    "image": case.image,
                    "image_digest": case.image_digest,
                }
            )
        # so a reader can see which images this set needs before pulling gigabytes of them
        _member(
            tar,
            "MANIFEST.json",
            json.dumps(
                {
                    "repo": repo,
                    "created": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "images": sorted({c["image"] for c in index}),
                    "cases": index,
                },
                indent=2,
            ),
        )
    return tar_path
