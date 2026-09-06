"""The agent's simulator: its current edits to tree/, rebuilt and run in a container of the case's image.

    python tools/sim.py <test> [--dump]     from inside a case copy; prints the verdict and the log

The harness starts the container before the agent begins (bug applied) and stops it afterwards; its
state lives next to the copy, not inside it, and the agent's own commands cannot reach docker. Each
call reverses the previous edits in the container, applies the current ones, rebuilds, runs. One
build+run per image at a time on this machine. --dump copies the wave to waves/sim.fst.
"""

from __future__ import annotations

import fcntl
import shutil
import subprocess
import sys
from pathlib import Path

from stead import container
from stead.case import Case
from stead.recipe import BuildError, apply_patch, build, run

LOG_TAIL = 3000


def _state(work: Path) -> Path:
    return work.parent / ".sim"


def start(work: Path, image: str, bug_patch: str) -> str:
    """The container the copy's sim calls will use; returns its id."""
    state = _state(work)
    state.mkdir(exist_ok=True)
    cid = container.start(image)
    (state / "cid").write_text(cid)
    apply_patch(cid, bug_patch)
    return cid


def calls(work: Path) -> int:
    return len(list(_state(work).glob("run*")))


def stop(work: Path) -> None:
    cid = _state(work) / "cid"
    if cid.exists():
        container.stop(cid.read_text().strip())


def _git(tree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], text=True, capture_output=True, check=True).stdout


def _sync(cid: str, work: Path, last: Path) -> None:
    """The container's tree = the image's tree + the bug + the agent's current edits."""
    _git(work / "tree", "add", "-A")
    diff = _git(work / "tree", "diff", "--cached")
    if last.exists() and last.read_text():
        apply_patch(cid, last.read_text(), reverse=True)
        last.write_text("")
    if diff:
        apply_patch(cid, diff)
    last.write_text(diff)


def sim(work: Path, test: str, dump: bool = False) -> str:
    state = _state(work)
    cid = (state / "cid").read_text().strip()
    subprocess.run(["docker", "start", cid], capture_output=True, check=False)  # a killed test stops it
    n = calls(work) + 1
    image = Case.load(work / "case.yaml").image
    with Path(f"/tmp/stead-sim-{image.replace('/', '-').replace(':', '-')}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            _sync(cid, work, state / "last.diff")
            build(cid)
        except BuildError as e:
            return f"BUILD_ERROR {test}\n{str(e)[-LOG_TAIL:]}"
        res = run(cid, test, state / f"run{n}", dump=dump)
    if dump and res.dump:
        shutil.copy(res.dump, work / "waves" / f"sim{res.dump.suffix}")
    log = res.log.read_text()[-LOG_TAIL:]
    return f"{res.status.name} {test}\n{log}" + ("\nwave: waves/sim.fst" if dump and res.dump else "")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dump"]
    if len(args) != 1:
        sys.stderr.write("usage: sim.py <test> [--dump]\n")
        return 64
    sys.stdout.write(sim(Path.cwd(), args[0], dump="--dump" in sys.argv) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
