"""Stage 3: score one submission against a baked case and its hidden gold."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import patch as patchlib
from .case import Case
from .gold import Gold
from .recipe import BuildError, RunStatus, ScriptRecipe


@dataclass
class Submission:
    method: str
    case: str
    k: int = 1
    lines: list[dict[str, Any]] = field(default_factory=list)
    patch: str | None = None
    text: str | None = None
    cost: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> Submission:
        return cls(**json.loads(Path(path).read_text()))


def score_lines(gold: Gold, lines: list[dict[str, Any]], k: int) -> dict[str, Any]:
    hit_rank = file_rank = None
    for i, ln in enumerate(lines, start=1):
        if file_rank is None and gold.hit_file(ln["file"]):
            file_rank = i
        if hit_rank is None and gold.hit(ln["file"], int(ln["line"])):
            hit_rank = i
    return {
        f"hit@{k}": hit_rank is not None and hit_rank <= k,
        f"file@{k}": file_rank is not None and file_rank <= k,
        "hit_rank": hit_rank,
        "file_rank": file_rank,
    }


def score_patch(case_dir: Path, recipe: ScriptRecipe, patch: str) -> dict[str, Any]:
    """Apply the patch to a copy of the case tree and re-run the case's test."""
    case = Case.load(Path(case_dir) / "case.yaml")
    res: dict[str, Any] = {"applied": False, "dut_only": True, "fixed": False, "status": None}
    outside = [f for f in patchlib.touched_files(patch) if not case.is_dut_path(f)]
    if outside:
        res["dut_only"] = False
        res["status"] = f"patch touches non-DUT files: {outside}"
        return res
    tmp = Path(tempfile.mkdtemp(prefix=f"stead-score-{case.id}-"))
    try:
        tree = tmp / "tree"
        shutil.copytree(Path(case_dir) / "tree", tree, symlinks=True)
        try:
            patchlib.apply(tree, patch)
        except subprocess.CalledProcessError as e:
            res["status"] = f"patch does not apply: {e.stderr}"
            return res
        res["applied"] = True
        try:
            recipe.build(tree)
        except BuildError as e:
            res["status"] = f"BUILD_ERROR: {str(e)[:500]}"
            return res
        run = recipe.run(tree, case.test, tmp / "run", dump=False)
        res["status"] = run.status.name
        res["fixed"] = run.status is RunStatus.PASS
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def score_submission(
    case_dir: Path, gold_dir: Path, sub: Submission, recipe: ScriptRecipe | None = None
) -> dict[str, Any]:
    gold = Gold.load(Path(gold_dir) / "gold.yaml")
    out: dict[str, Any] = {"method": sub.method, "case": sub.case, "k": sub.k}
    out.update(score_lines(gold, sub.lines, sub.k))
    out["patch"] = score_patch(case_dir, recipe, sub.patch) if (sub.patch and recipe) else None
    out["text"] = sub.text
    out["cost"] = sub.cost
    return out
