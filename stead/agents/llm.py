"""One model, five tools, one case folder. litellm carries the call: the model string picks the
provider ("anthropic/claude-sonnet-4-5", "openai/gpt-5", "xai/grok-4.6", ...) and the provider's
API key comes from the environment.

    run(work, model, effort) -> Run
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import sys
from itertools import islice
from pathlib import Path

from . import PROMPT, Run, system_prompt

MAX_TURNS = 80
MAX_OUT = 20_000  # chars of one tool result the model sees
STRING = {"type": "string"}
INTEGER = {"type": "integer"}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Lines start..end of a text file, numbered. Default: the first 200.",
            "parameters": {
                "type": "object",
                "properties": {"path": STRING, "start": INTEGER, "end": INTEGER},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "grep -rn for a pattern under a file or directory (default: the case folder).",
            "parameters": {
                "type": "object",
                "properties": {"pattern": STRING, "path": STRING},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Files matching a glob, relative to the case folder.",
            "parameters": {"type": "object", "properties": {"pattern": STRING}, "required": ["pattern"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace the one exact occurrence of old with new in a file under tree/.",
            "parameters": {
                "type": "object",
                "properties": {"path": STRING, "old": STRING, "new": STRING},
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python",
            "description": "Run Python in the case folder (pywellen is installed); returns stdout+stderr.",
            "parameters": {"type": "object", "properties": {"code": STRING}, "required": ["code"]},
        },
    },
]


def _inside(work: Path, path: str) -> Path:
    p = (work / path).resolve()
    if not p.is_relative_to(work.resolve()):
        raise ValueError(f"{path} is outside the case folder")
    return p


def _read(work: Path, path: str, start: int = 1, end: int = 200) -> str:
    p = _inside(work, path)
    if p.suffix in (".fst", ".vcd"):
        raise ValueError(f"{path} is a wave dump; read it with python and pywellen")
    with p.open(errors="replace") as f:
        return "\n".join(
            f"{i}\t{ln.rstrip(chr(10))}" for i, ln in enumerate(islice(f, start - 1, end), start=start)
        )


def _grep(work: Path, pattern: str, path: str = ".") -> str:
    _inside(work, path)
    res = subprocess.run(
        ["grep", "-rnI", "--", pattern, path], cwd=work, text=True, capture_output=True, check=False
    )
    return res.stdout or res.stderr or "no match"


def _glob(work: Path, pattern: str) -> str:
    return "\n".join(sorted(str(p.relative_to(work)) for p in work.glob(pattern))) or "no match"


def _edit(work: Path, path: str, old: str, new: str) -> str:
    p = _inside(work, path)
    if not p.is_relative_to((work / "tree").resolve()):
        raise ValueError(f"{path} is not under tree/; only the tree may be edited")
    text = p.read_text()
    if text.count(old) != 1:
        raise ValueError(f"old occurs {text.count(old)} times in {path}; it must occur exactly once")
    p.write_text(text.replace(old, new))
    return f"edited {path}"


def _python(work: Path, code: str) -> str:
    try:
        res = subprocess.run(
            [sys.executable, "-c", code], cwd=work, text=True, capture_output=True, timeout=300, check=False
        )
    except subprocess.TimeoutExpired:
        return "error: timeout after 300 s"
    return (res.stdout + res.stderr) or "(no output)"


CALLS = {"read": _read, "grep": _grep, "glob": _glob, "edit": _edit, "python": _python}


def call(work: Path, name: str, arguments: str) -> str:
    """One tool call from the model; every failure comes back as text, never as an exception."""
    try:
        out = CALLS[name](work, **json.loads(arguments))
    except (OSError, TypeError, KeyError, ValueError) as e:
        out = f"error: {e}"
    return out[:MAX_OUT] + ("\n[truncated]" if len(out) > MAX_OUT else "")


def _litellm():
    import litellm  # ~0.9 s to import: only an agent run pays it, not every CLI call

    litellm.suppress_debug_info = True
    litellm.drop_params = True  # a provider without reasoning_effort gets the call without it
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    return litellm


def _step(msgs: list, model: str, effort: str, tool_choice: str, usage: dict):
    lib = _litellm()
    resp = lib.completion(
        model=model,
        messages=msgs,
        tools=TOOLS,
        tool_choice=tool_choice,
        max_tokens=8192,
        num_retries=3,
        reasoning_effort=effort or None,
    )
    with contextlib.suppress(Exception):  # a model missing from litellm's price table costs 0
        usage["usd"] += lib.completion_cost(resp)
    usage["tokens_in"] += resp.usage.prompt_tokens
    usage["tokens_out"] += resp.usage.completion_tokens
    usage["turns"] += 1
    msg = resp.choices[0].message
    msgs.append(msg)
    return msg


def _plain(msg) -> dict:
    return msg.model_dump(exclude_none=True) if hasattr(msg, "model_dump") else msg


def run(work: Path, model: str, effort: str = "") -> Run:
    """Tool loop until the model answers without a tool call, or MAX_TURNS, then one last answer."""
    msgs: list = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": PROMPT}]
    usage = {"usd": 0.0, "tokens_in": 0, "tokens_out": 0, "turns": 0}
    for _ in range(MAX_TURNS):
        msg = _step(msgs, model, effort, "auto", usage)
        if not msg.tool_calls:
            return Run(msg.content or "", model, usage, [_plain(m) for m in msgs[1:]])
        for tc in msg.tool_calls:
            out = call(work, tc.function.name, tc.function.arguments)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    msgs.append({"role": "user", "content": "Turn limit reached. Answer now with the JSON block."})
    msg = _step(msgs, model, effort, "none", usage)  # tools stay declared: the history holds tool calls
    return Run(msg.content or "", model, usage, [_plain(m) for m in msgs[1:]])
