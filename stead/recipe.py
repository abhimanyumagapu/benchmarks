"""How a core is built and run, behind one contract.

A recipe is `repos/<repo>/run.sh`, executed inside the core's container against /work/tree:

    run.sh build <tree>                                   0 ok | 2 build error
    run.sh run   <tree> <test> <out_dir> [--dump=on|off]  0 PASS | 1 FAIL | 2 build error | 3 crash
    run.sh suite <tree> <out_dir> [<regex>]               0 ran | 2 build error

`run` writes <out_dir>/sim.log (with the STEAD FAIL line on a value-check fail) and, with dump
on, <out_dir>/dump.<fst|vcd>. `suite` runs every test (matching <regex>) with the dump off and
writes <out_dir>/summary.txt, "<exit> <test>" per test, plus <out_dir>/<test>/sim.log for each
test that did not pass.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import container
from .fail import Stead, parse_log
from .progress import timed

logger = logging.getLogger("stead.recipe")

RUN_SH = "/work/recipe/run.sh"
TREE = "/work/tree"
TEST_TIMEOUT = 1200  # s per test, for `run` here and for each test of `suite` inside the container


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


def _status(code: int) -> RunStatus:
    try:
        return RunStatus(code)
    except ValueError:
        return RunStatus.CRASH


def apply_patch(cid: str, patch: str, reverse: bool = False) -> None:
    """`git apply` the diff at the tree root (no .git needed). Raises CalledProcessError."""
    container.put(cid, patch, "/work/patch.diff")
    p = container.run(cid, "git", "apply", *(["-R"] if reverse else []), "/work/patch.diff", cwd=TREE)
    container.run(cid, "rm", "-f", "/work/patch.diff")
    if p.returncode != 0:
        raise BuildError(f"patch does not apply: {p.stderr}")


def patch_applies(cid: str, patch: str) -> None:
    """Raise BuildError unless `patch` would apply to the tree.

    `git apply --check` writes nothing, so the image's warm build survives it. Bake calls this before
    the clean run: a patch with a stale line number or a wrong context line is then a second's work
    to find, not a full test run on cva6 or caliptra.
    """
    container.put(cid, patch, "/work/check.diff")
    p = container.run(cid, "git", "apply", "--check", "/work/check.diff", cwd=TREE)
    container.run(cid, "rm", "-f", "/work/check.diff")
    if p.returncode != 0:
        raise BuildError(f"patch does not apply: {p.stderr}")


def build(cid: str) -> None:
    with timed(logger, "build"):
        p = container.run(cid, RUN_SH, "build", TREE)
    if p.returncode != 0:
        raise BuildError(f"run.sh build -> exit {p.returncode}\n{p.stdout}\n{p.stderr}")


def run(cid: str, test: str, out_dir: Path, dump: bool = True) -> RunResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / "sim.log"
    inside = f"/out/{out_dir.name}"
    argv = (RUN_SH, "run", TREE, test, inside, f"--dump={'on' if dump else 'off'}")
    try:
        with timed(logger, f"run {test}{'' if dump else ' (no dump)'}"):
            p = container.run(cid, *argv, timeout=TEST_TIMEOUT)
    except subprocess.TimeoutExpired:  # the container was killed; nothing is left to copy
        logger.warning("run %s: harness timeout after %ds; container killed", test, TEST_TIMEOUT)
        log.write_text(f"harness timeout after {TEST_TIMEOUT}s\n")
        return RunResult(RunStatus.CRASH, log, None, None)
    container.get(cid, inside, out_dir)
    if not log.exists():
        log.write_text(f"(no sim.log written by recipe; exit {p.returncode})\n{p.stderr}")
    status = _status(p.returncode)
    logger.info("run %s -> %s", test, status.name)
    dumps = sorted(out_dir.glob("dump.*"))
    stead = parse_log(log) if status is RunStatus.FAIL else None
    return RunResult(status=status, log=log, dump=dumps[0] if dumps else None, stead=stead)


def suite(cid: str, out_dir: Path, regex: str = "") -> list[tuple[RunStatus, str]]:
    """Every test's status, in suite order; failing tests have their sim.log under out_dir/<test>/.
    No cap here: stead_suite caps each test at TEST_TIMEOUT."""
    argv = (RUN_SH, "suite", TREE, "/out/suite", *([regex] if regex else []))
    with timed(logger, f"suite{f' ({regex})' if regex else ''}"):
        p = container.run(cid, *argv, env={"STEAD_TEST_TIMEOUT": str(TEST_TIMEOUT)})
    if p.returncode != 0:
        raise BuildError(f"run.sh suite -> exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    container.get(cid, "/out/suite", out_dir)
    rows = []
    for line in (Path(out_dir) / "summary.txt").read_text().splitlines():
        code, test = line.split(maxsplit=1)
        rows.append((_status(int(code)), test))
    return rows
