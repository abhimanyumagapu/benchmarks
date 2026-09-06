"""Claude Code headless (`claude -p`): its own tools and loop, our system prompt and skill appended.
stream-json gives every message as it happens; the last event carries the answer and the cost."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from stead.case import Case

from . import PROMPT, Run, sandbox, system_prompt

TOOLS = [
    "Read",
    "Grep",
    "Glob",
    "Edit",
    "Write",
    "Bash(python:*)",
    "Bash(stead-sim:*)",
    "Bash(ls:*)",
    "Bash(head:*)",
    "Bash(grep:*)",
]
TIMEOUT = 3600  # s of wall per case


def is_method(name: str) -> bool:
    """`claude` (the CLI's default model) or `claude-<alias>` (sonnet, opus, fable, haiku, ...)."""
    return name == "claude" or name.startswith("claude-")


def run(work: Path, method: str, effort: str = "") -> Run:
    version = subprocess.run(
        ["claude", "--version"], text=True, capture_output=True, check=True
    ).stdout.strip()
    model = ["--model", method[len("claude-") :]] if method != "claude" else []
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", *model]
    cmd += ["--effort", effort] if effort else []
    repo = Case.load(work / "case.yaml").repo
    cmd += ["--allowedTools", *TOOLS, "--append-system-prompt", system_prompt(repo), PROMPT]
    bin_dir = sandbox(work / ".bin")
    (bin_dir / "stead-sim").write_text(
        f'#!/bin/sh\nexec {sys.executable} tools/sim.py "$@"\n'
    )  # needs docker: outside the sandbox
    (bin_dir / "stead-sim").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        cmd, cwd=work, text=True, capture_output=True, check=False, timeout=TIMEOUT, env=env
    )
    if proc.returncode:
        raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr[-1500:]}")
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    out = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if out is None:
        raise RuntimeError(f"claude gave no result event: {proc.stdout[-1500:]}")
    cost = {"usd": out.get("total_cost_usd", 0.0), "turns": out.get("num_turns")}
    return Run(out.get("result", ""), version, cost, [e for e in events if e.get("type") != "result"])
