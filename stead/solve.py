"""Stage 2 for LLM agents: run one in the case folder, keep what it hands back.

    solve(case_dir, method, results_root) -> results/<case>/<method>.json

The agent gets the rtl-debug skill as system prompt, works inside the case folder with read-only
tools, and ends with a JSON block. Cost and wall time come from the CLI's own accounting.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .case import Case

SKILL = Path(__file__).parent.parent / "skills" / "rtl-debug" / "SKILL.md"
READ_ONLY = ["Read", "Grep", "Glob", "Bash(python:*)", "Bash(ls:*)", "Bash(head:*)", "Bash(grep:*)"]

METHODS = {
    "claude": ["claude", "-p", "--output-format", "json", "--allowedTools", *READ_ONLY],
    "claude-sonnet": [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        "sonnet",
        "--allowedTools",
        *READ_ONLY,
    ],
}

PROMPT = "Work the case in the current directory. Read README.md first. k = 3."


def parse_submission(text: str) -> dict:
    """The agent's JSON block, or {"text": ...} when it did not produce one."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return {"text": text}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"text": text}


def solve(case_dir: Path, method: str, results_root: Path) -> Path:
    case = Case.load(case_dir / "case.yaml")
    cmd = [*METHODS[method], "--append-system-prompt", SKILL.read_text(), PROMPT]
    run = subprocess.run(cmd, cwd=case_dir, text=True, capture_output=True, check=True)
    out = json.loads(run.stdout)
    answer = parse_submission(out.get("result", ""))
    sub = {
        "method": method,
        "case": case.id,
        "k": answer.get("k", 3),
        "lines": answer.get("lines", []),
        "patch": answer.get("patch"),
        "text": answer.get("text", ""),
        "cost": {"usd": out.get("total_cost_usd", 0.0), "wall_s": out.get("duration_ms", 0) / 1000},
    }
    path = results_root / case.id / f"{method}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sub, indent=2))
    return path
