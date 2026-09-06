"""Stage 3: score one submission against a baked case and its hidden gold. The agent's answer is
parsed, not trusted: anything malformed scores as a miss, never as a crash."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from . import container
from . import patch as patchlib
from .case import Case
from .gold import Gold
from .recipe import BuildError, RunStatus, apply_patch, build, run


def _line(ln: Any) -> dict[str, Any] | None:
    """One ranked line as {file, line, ...}, or None without a file and an integer line."""
    try:
        return {**ln, "file": str(ln["file"]), "line": int(ln["line"])}
    except (TypeError, KeyError, ValueError):
        return None


def _lines(raw: Any) -> list[dict[str, Any]]:
    return [ln for ln in map(_line, raw if isinstance(raw, list) else []) if ln]


@dataclass
class Submission:
    method: str
    case: str
    k: int = 1
    agent: str = ""
    lines: list[dict[str, Any]] = field(default_factory=list)
    patch: str | None = None
    text: str | None = None
    answer: str = ""  # the raw final message
    cost: dict[str, Any] = field(default_factory=dict)
    ran_at: str = ""
    error: str | None = None  # the agent crashed; scored as a miss, counted separately
    effort: str = ""
    trial: int = 1
    attempts: int = 1
    flags: list[str] = field(default_factory=list)  # reached outside the folder; for a human to read

    @classmethod
    def load(cls, path: Path | str) -> Submission:
        d = json.loads(Path(path).read_text())
        d = {k: v for k, v in d.items() if k in {f.name for f in fields(cls)}}
        d["lines"] = _lines(d.get("lines"))
        try:
            d["k"] = int(d.get("k", 1))
        except (TypeError, ValueError):
            d["k"] = 1
        return cls(**d)


def score_lines(gold: Gold, lines: list[dict[str, Any]], k: int) -> dict[str, Any]:
    hit_rank = file_rank = None
    for i, ln in enumerate(lines, start=1):
        if file_rank is None and gold.hit_file(ln["file"]):
            file_rank = i
        if hit_rank is None and gold.hit(ln["file"], ln["line"]):
            hit_rank = i
    return {
        f"hit@{k}": hit_rank is not None and hit_rank <= k,
        f"file@{k}": file_rank is not None and file_rank <= k,
        "hit_rank": hit_rank,
        "file_rank": file_rank,
    }


def score_patch(case_dir: Path, gold_dir: Path, patch: str) -> dict[str, Any]:
    """Bug patch then fix patch in a fresh container; the named test and every also_fails must PASS."""
    case = Case.load(Path(case_dir) / "case.yaml")
    res: dict[str, Any] = {"applied": False, "dut_only": True, "fixed": False, "status": None}
    outside = [f for f in patchlib.touched_files(patch) if not case.is_dut_path(f)]
    if outside:
        res["dut_only"] = False
        res["status"] = f"patch touches non-DUT files: {outside}"
        return res
    tmp = Path(tempfile.mkdtemp(prefix=f"stead-score-{case.id}-"))
    cid = container.start(case.image)
    try:
        apply_patch(cid, (Path(gold_dir) / "bug.patch").read_text())
        try:
            apply_patch(cid, patch)
        except BuildError as e:
            res["status"] = str(e)
            return res
        res["applied"] = True
        try:
            build(cid)
        except BuildError as e:
            res["status"] = f"BUILD_ERROR: {str(e)[:500]}"
            return res
        status = {}
        for i, test in enumerate([case.test, *case.also_fails]):
            status[test] = run(cid, test, tmp / str(i), dump=False).status.name
            if status[test] == RunStatus.CRASH.name:
                break  # a harness timeout has killed the container
    finally:
        container.stop(cid)
        shutil.rmtree(tmp, ignore_errors=True)
    res["status"] = status
    res["fixed"] = all(s == RunStatus.PASS.name for s in status.values())
    return res


def score_submission(case_dir: Path, gold_dir: Path, sub: Submission) -> dict[str, Any]:
    gold = Gold.load(Path(gold_dir) / "gold.yaml")
    case = Case.load(Path(case_dir) / "case.yaml")
    out: dict[str, Any] = {
        "method": sub.method,
        "agent": sub.agent,
        "effort": sub.effort,
        "case": sub.case,
        "repo": case.repo,
        "class": gold.klass,
        "trial": sub.trial,
        "attempts": sub.attempts,
        "ran_at": sub.ran_at,
        "error": sub.error,
        "flags": sub.flags,
        "k": sub.k,
    }
    out.update(score_lines(gold, sub.lines, sub.k))
    out["lines"] = sub.lines
    out["patch"] = score_patch(case_dir, gold_dir, sub.patch) if sub.patch else None
    out["text"] = sub.text
    out["cost"] = sub.cost
    return out
