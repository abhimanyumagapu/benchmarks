"""How a repo is built and run, behind one contract.

A recipe is a `run.sh` next to the repo's shims (repos/<repo>/run.sh):

    run.sh build <tree>                                        0 ok | 2 build error
    run.sh run   <tree> <test> <out_dir> [--dump=on|off]
        0 PASS | 1 FAIL | 2 build error | 3 crash/hang/timeout

`run` writes <out_dir>/sim.log (with the STEAD FAIL line on a value-check
fail) and, with dump on, <out_dir>/dump.<fst|vcd>.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .fail import Stead, parse_log


class RunStatus(Enum):
    PASS = 0
    FAIL = 1  # value check failed; the only status a case may be built on
    BUILD_ERROR = 2
    CRASH = 3  # crash, hang, timeout; never confused with FAIL


class BuildError(RuntimeError):
    pass


@dataclass
class RunResult:
    status: RunStatus
    log: Path
    dump: Path | None
    stead: Stead | None


class ScriptRecipe:
    def __init__(self, name: str, script: Path | str):
        self.name = name
        self.script = Path(script).resolve()

    def _sh(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.script), *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def build(self, tree: Path) -> None:
        p = self._sh("build", str(tree))
        if p.returncode != 0:
            raise BuildError(f"{self.script} build {tree} -> exit {p.returncode}\n{p.stdout}\n{p.stderr}")

    def run(self, tree: Path, test: str, out_dir: Path, dump: bool = True, timeout: int = 1200) -> RunResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            p = self._sh(
                "run", str(tree), test, str(out_dir), f"--dump={'on' if dump else 'off'}", timeout=timeout
            )
            code = p.returncode
            stderr = p.stderr
        except subprocess.TimeoutExpired as e:
            code, stderr = 3, f"harness timeout after {timeout}s\n{e.stderr or ''}"
        log = out_dir / "sim.log"
        if not log.exists():
            log.write_text(f"(no sim.log written by recipe; exit {code})\n{stderr}")
        try:
            status = RunStatus(code)
        except ValueError:
            status = RunStatus.CRASH
        dumps = sorted(out_dir.glob("dump.*"))
        stead = parse_log(log) if status is RunStatus.FAIL else None
        return RunResult(status=status, log=log, dump=dumps[0] if dumps else None, stead=stead)
