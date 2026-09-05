"""Stage 2 for agents: run one on a copy of the case, keep what it hands back.

    solve(case_dir, gold_dir, method, results_root, trial=1) -> results/<case>/<method>[.t<trial>].json

method:  claude | claude-<alias>         Claude Code headless (agents/claude_code.py), e.g. claude-sonnet
         <provider>/<model>              any model through litellm (agents/llm.py), API key from the env
         ...+<effort>                    reasoning effort, passed through and recorded

The agent works in a scratch copy of the case folder plus a tree materialized from the image (bug
applied, manifest only). Ranked lines and text come from its final JSON block; the patch is the diff
of that tree afterwards, so the case folder itself is never touched. Its transcript is kept next to
the result for audit, and scanned for network or history access on the way.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .agents import Run, claude_code, llm, split_effort
from .case import Case
from .tree import materialize

RETRIES = 2  # more attempts after a crash (rate limit, container hiccup); a timeout is not retried
FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
OUTSIDE = re.compile(
    r"https?://\S+"
    r"|\b(urllib|requests|socket|httpx|curl|wget|pip install|git (log|fetch|pull|clone|show|blame))\b"
)


def parse_submission(text: str) -> dict:
    """The agent's last ```json block (or, without one, the outermost braces); else {"text": ...}."""
    blocks = FENCE.findall(text)
    raw = blocks[-1] if blocks else text[text.find("{") : text.rfind("}") + 1]
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {"text": text}
    return d if isinstance(d, dict) else {"text": text}


def result_path(results_root: Path, case_id: str, method: str, trial: int = 1) -> Path:
    stem = method.replace("/", "-") + (f".t{trial}" if trial > 1 else "")
    return results_root / case_id / f"{stem}.json"


def flags(transcript: list) -> list[str]:
    """What the agent said or asked to run that reaches outside the folder. For a human to read."""
    out = []
    for i, m in enumerate(transcript):
        if (m.get("role") or m.get("type")) != "assistant":
            continue
        out.extend(
            f"turn {i}: {hit[:80]}" for hit in sorted({h.group(0) for h in OUTSIDE.finditer(json.dumps(m))})
        )
    return out


def runner(method: str) -> Callable[[Path], Run]:
    """The agent behind a method name. Raises ValueError for a name that is not one."""
    name, effort = split_effort(method)
    if claude_code.is_method(name):
        return lambda work: claude_code.run(work, name, effort)
    if "/" in name:
        return lambda work: llm.run(work, name, effort)
    raise ValueError(f"unknown method {method!r}: claude, claude-<alias>, or <provider>/<model>")


def _git(tree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], text=True, capture_output=True, check=True).stdout


def _writable_copy(case_dir: Path, gold_dir: Path, work: Path) -> Path:
    """Copy of the case with a tree/ that is a git repo, so the agent's edits come out as a diff."""
    shutil.copytree(case_dir, work, symlinks=True)
    case = Case.load(case_dir / "case.yaml")
    materialize(case.image, (gold_dir / "bug.patch").read_text(), work / "tree")
    _git(work / "tree", "init", "-q")
    _git(work / "tree", "-c", "user.email=stead@bench", "-c", "user.name=stead", "add", "-A")
    _git(work / "tree", "-c", "user.email=stead@bench", "-c", "user.name=stead", "commit", "-qm", "case")
    return work


def _attempt(case_dir: Path, gold_dir: Path, run: Callable[[Path], Run]) -> tuple[Run, Exception | None, str]:
    """One run on a fresh copy: (run, what crashed it, patch including files it created)."""
    tmp = Path(tempfile.mkdtemp(prefix="stead-solve-"))
    try:
        work = _writable_copy(case_dir, gold_dir, tmp / case_dir.name)
        try:
            res, error = run(work), None
        except Exception as e:  # every provider raises its own classes; a crash is a recorded miss
            res, error = Run("", "", {"usd": 0.0}), e
        _git(work / "tree", "add", "-A")
        return res, error, _git(work / "tree", "diff", "--cached")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def solve(case_dir: Path, gold_dir: Path, method: str, results_root: Path, trial: int = 1) -> Path:
    run = runner(method)
    case = Case.load(case_dir / "case.yaml")
    ran_at = datetime.now().astimezone().isoformat(timespec="seconds")
    t0 = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        res, error, patch = _attempt(case_dir, gold_dir, run)
        if error is None or attempts > RETRIES or isinstance(error, subprocess.TimeoutExpired):
            break
    answer = parse_submission(res.answer)
    sub = {
        "method": method,
        "agent": res.agent,
        "effort": split_effort(method)[1],
        "case": case.id,
        "trial": trial,
        "attempts": attempts,
        "ran_at": ran_at,
        "error": f"{type(error).__name__}: {str(error)[:1500]}" if error else None,
        "flags": flags(res.transcript),
        "k": answer.get("k", 3),
        "lines": answer.get("lines", []),
        "patch": patch or None,
        "text": answer.get("text", ""),
        "cost": {**res.cost, "wall_s": round(time.monotonic() - t0, 1)},
    }
    path = result_path(results_root, case.id, method, trial)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sub, indent=2))
    if res.transcript:
        with path.with_suffix(".trajectory.jsonl").open("w") as f:
            f.writelines(json.dumps(m) + "\n" for m in res.transcript)
    return path
