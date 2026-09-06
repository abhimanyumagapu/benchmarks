"""One module per agent kind, each with run(work, ...) -> Run; solve.py picks one by method name.

    claude_code   Claude Code headless: its own tools, our system prompt and skill appended
    llm           any model through litellm with our own five-tool loop; API key from the environment

A method is "<name>[+<effort>]": "claude-sonnet+high", "anthropic/claude-opus-4-5+max". Walker,
ChipAgents, Bronco and the rest go here as modules with the same shape. They all get the same thing:
a writable copy of the case with tree/, and hand back text plus their transcript; the patch is the
diff of tree/.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROMPT = "Work the case in the current directory. Read README.md first. k = 3."
# What the agent's own commands must not reach: the network, its sim container, and the answer key.
# gold/ holds the bug patch and the gold window; specs/ holds both again; results/ holds what other
# agents answered. The agent is handed sys.executable, which names the bench root, so "it would have
# to go looking" is not a defence.
HIDDEN = ("gold", "specs", "results")
SOCKETS = ("/var/run/docker.sock", "~/.docker", "~/.orbstack")
PASSTHROUGH = '#!/bin/sh\nexec "$@"\n'


def _runs(argv: list[str]) -> bool:
    """True if `argv` runs and exits 0 here. A fence that is installed but forbidden is not a fence."""
    try:
        return subprocess.run(argv, capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@cache
def sandbox_kind() -> str:
    """Which fence the agent's commands run behind on this machine.

    "seatbelt"  macOS: sandbox-exec denies the network, the docker socket and the answer key.
    "userns"    Linux: unshare gives a private net+mount namespace; the answer key is mounted over.
    "none"      neither is available. Commands run as they are and the transcript audit is the
                only thing left; every submission records which of the three it got.

    Probed, not assumed: unshare is present and forbidden on GitHub's runners and on hardened
    distros, and a wrapper that fails is worse than none -- the command never runs at all.
    """
    if _runs(["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"]):
        return "seatbelt"
    if shutil.which("unshare") and _runs(["unshare", "-rmn", "true"]):
        return "userns"
    return "none"


def _hidden_paths() -> list[str]:
    return [str(ROOT / d) for d in HIDDEN]


def _seatbelt(bin_dir: Path) -> str:
    """sandbox-exec with a profile next to the wrapper. Denies outright rather than allow-listing:
    the agent needs the whole toolchain, and naming what it may not have is the shorter list."""
    denied = " ".join(f'(subpath "{p}")' for p in _hidden_paths())
    sockets = " ".join(f'(subpath "{Path(p).expanduser()}")' for p in SOCKETS)
    profile = bin_dir / "sandbox.sb"
    profile.write_text(
        "(version 1)\n(allow default)\n(deny network*)\n"
        f"(deny file-read* {denied})\n"
        f"(deny file-read* file-write* {sockets})\n"
    )
    return f'#!/bin/sh\nexec /usr/bin/sandbox-exec -f "{profile}" "$@"\n'


def _userns(bin_dir: Path) -> str:
    """unshare with no interfaces, not even loopback, the docker socket bound over with /dev/null,
    and an empty directory bound over each answer-key path. The mount namespace starts as a copy of
    ours, so hiding those is a mount, not a permission."""
    empty = bin_dir / "empty"
    empty.mkdir(exist_ok=True)
    hide = "".join(f'mount --bind "{empty}" "{p}" 2>/dev/null;' for p in _hidden_paths())
    inner = f'mount --bind /dev/null /var/run/docker.sock 2>/dev/null;{hide} exec "$@"'
    return f"#!/bin/sh\nexec unshare -rmn sh -c '{inner}' -- \"$@\"\n"


@dataclass
class Run:
    answer: str  # the agent's final text; the JSON block is parsed out of it
    agent: str  # what ran: a CLI version, a model string
    cost: dict  # usd and whatever else the agent accounts for; solve adds wall_s
    transcript: list = field(default_factory=list)  # every message after the system prompt, for audit


def split_effort(method: str) -> tuple[str, str]:
    name, _, effort = method.partition("+")
    return name, effort


def sandbox(bin_dir: Path) -> Path:
    """bin_dir/sandbox runs a command in the sandbox; bin_dir/python and python3 run this interpreter
    in it. Put bin_dir first on PATH for a subprocess whose own shell runs python (the Claude Code CLI)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fence = {"seatbelt": _seatbelt, "userns": _userns}.get(sandbox_kind())
    for name, text in (
        ("sandbox", fence(bin_dir) if fence else PASSTHROUGH),
        ("python", f'#!/bin/sh\nexec "{bin_dir}/sandbox" {sys.executable} "$@"\n'),
        ("python3", f'#!/bin/sh\nexec "{bin_dir}/sandbox" {sys.executable} "$@"\n'),
    ):
        (bin_dir / name).write_text(text)
        (bin_dir / name).chmod(0o755)
    return bin_dir


def system_prompt(repo: str = "") -> str:
    """The role (prompts/system.md), the method (the rtl-debug skill), the repo's own skill if it has one."""
    parts = [ROOT / "prompts" / "system.md", ROOT / "skills" / "rtl-debug" / "SKILL.md"]
    if repo and (ROOT / "skills" / repo / "SKILL.md").exists():
        parts.append(ROOT / "skills" / repo / "SKILL.md")
    return "\n\n".join(p.read_text() for p in parts)
