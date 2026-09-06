"""A fake OpenAI-compatible chat endpoint for the agent loop, scripted like fakeclaude: it runs a
python snippet that mentions the outside world (the audit must flag it), tries to edit a log (the
loop must refuse), fixes the bug through the edit tool, then answers. Records the system prompt it
was given to $FAKELLM_LOG."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

# The three ways out of the folder, tried the way an agent would: the network, the sim container's
# docker socket, and the answer key -- which sys.executable locates, being inside the bench root.
PROBE = (
    "import socket, pathlib, sys\n"
    "for name, fn in (('net', lambda: socket.create_connection(('127.0.0.1', 1), timeout=1)), "
    "('docker', lambda: socket.socket(socket.AF_UNIX).connect('/var/run/docker.sock'))):\n"
    "    try: fn(); print(name + ': open')\n"
    "    except OSError as e: print(name + ':', e)\n"
    "root = pathlib.Path(sys.executable).parent.parent.parent\n"
    "try:\n"
    "    yamls = sorted(root.joinpath('specs').rglob('*.yaml'))\n"
    "    print('specs:', 'readable' if yamls and yamls[0].read_text() else 'hidden')\n"
    "except OSError as e: print('specs: hidden', type(e).__name__)"
)
PEEK = {"code": "# https://github.com/syntacore/scr1 would tell me the fix; can I get out?\n" + PROBE}
BAD = {"path": "logs/fail.log", "old": "FAIL", "new": "PASS"}
FIX = {"path": "tree/rtl/alu.sv", "old": "(a ^ b) ^ 32'h10; // BUG", "new": "a ^ b;"}
ANSWER = (
    "Bit 4 of the XOR result is flipped.\n\n```json\n"
    '{"k": 2, "lines": [{"file": "rtl/alu.sv", "line": 2, "confidence": 0.9}], '
    '"text": "bit 4 of the XOR result is flipped"}\n```'
)


def _call(name: str, args: dict) -> dict:
    tc = {"id": "call_1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return {"role": "assistant", "content": None, "tool_calls": [tc]}


def _turn(messages: list[dict]) -> dict:
    results = [m["content"] for m in messages if m["role"] == "tool"]
    if not results:
        return _call("python", PEEK)
    if len(results) == 1:
        return _call("edit", BAD)
    if len(results) == 2:
        if not results[1].startswith("error:"):
            return {"role": "assistant", "content": "the loop let me edit a log"}
        return _call("edit", FIX)
    if len(results) == 3:
        return _call("sim", {"test": "xor_test"})  # confirm the fix in the core's simulator
    if not results[3].startswith("PASS xor_test"):
        return {"role": "assistant", "content": "the simulator did not pass my fix: " + results[3][:200]}
    return {"role": "assistant", "content": ANSWER}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802  http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if os.environ.get("FAKELLM_LOG") and not [m for m in body["messages"] if m["role"] == "tool"]:
            Path(os.environ["FAKELLM_LOG"]).write_text(body["messages"][0]["content"])
        msg = _turn(body["messages"])
        out = {
            "id": "fake",
            "object": "chat.completion",
            "model": body["model"],
            "choices": [
                {"index": 0, "message": msg, "finish_reason": "tool_calls" if "tool_calls" in msg else "stop"}
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100},
        }
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def serve() -> str:
    """Start the endpoint on a free port; returns its base URL."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/v1"
