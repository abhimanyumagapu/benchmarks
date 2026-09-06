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
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROMPT = "Work the case in the current directory. Read README.md first. k = 3."
# The sandbox the agent's own commands run in: a private net+mount namespace with no interfaces, not
# even loopback, and the docker socket hidden, so neither the network nor its sim container's files
# are reachable. Linux only; elsewhere commands run as they are and the transcript audit (solve.flags)
# is what catches an outward request.
SANDBOX = (
    "#!/bin/sh\nexec unshare -rmn sh -c "
    '\'mount --bind /dev/null /var/run/docker.sock 2>/dev/null; exec "$@"\' -- "$@"\n'
    if shutil.which("unshare")
    else '#!/bin/sh\nexec "$@"\n'
)


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
    for name, text in (
        ("sandbox", SANDBOX),
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
