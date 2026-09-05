"""One module per agent kind, each with run(work, ...) -> Run; solve.py picks one by method name.

    claude_code   Claude Code headless: its own tools, our system prompt and skill appended
    llm           any model through litellm with our own five-tool loop; API key from the environment

A method is "<name>[+<effort>]": "claude-sonnet+high", "anthropic/claude-opus-4-5+max". Walker,
ChipAgents, Bronco and the rest go here as modules with the same shape. They all get the same thing:
a writable copy of the case with tree/, and hand back text plus their transcript; the patch is the
diff of tree/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROMPT = "Work the case in the current directory. Read README.md first. k = 3."


@dataclass
class Run:
    answer: str  # the agent's final text; the JSON block is parsed out of it
    agent: str  # what ran: a CLI version, a model string
    cost: dict  # usd and whatever else the agent accounts for; solve adds wall_s
    transcript: list = field(default_factory=list)  # every message after the system prompt, for audit


def split_effort(method: str) -> tuple[str, str]:
    name, _, effort = method.partition("+")
    return name, effort


def system_prompt() -> str:
    """The role (prompts/system.md) with the method (the rtl-debug skill) on top."""
    return (
        (ROOT / "prompts" / "system.md").read_text()
        + "\n\n"
        + (ROOT / "skills" / "rtl-debug" / "SKILL.md").read_text()
    )
