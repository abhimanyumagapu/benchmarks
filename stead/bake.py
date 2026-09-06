"""Stage 1: turn (image, test, bug patch, gold) into a case folder.

container from the core image (clean simulator warm)
fixed test:  run clean: must PASS -> apply bug patch (dut_paths only) -> build -> run: must FAIL (not crash)
test: auto:  apply bug patch -> build -> suite -> pick the failing test -> run it with dump
             -> reverse the patch -> run clean: must PASS
STEAD line -> validate against dump -> keep, or drop to null with the reason
write cases/<repo>/<id>/ (logs, waves, case.yaml, README); no tree, it lives in the image
write gold/<repo>/<id>/ (gold.yaml, bug.patch) -- never inside the case folder
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from . import container
from . import patch as patchlib
from .case import Case, matches_any
from .fail import Stead, parse_log
from .gold import Gold
from .recipe import BuildError, RunResult, RunStatus, apply_patch, build, patch_applies, run, suite
from .validate import validate_stead


class BakeError(RuntimeError):
    pass


@dataclass
class BakeSpec:
    id: str
    repo: str
    url: str
    commit: str
    image: str
    test: str  # a test name, or "auto": let the suite find one
    bug_patch: str
    gold: Gold
    dut_paths: list[str]
    checker_paths: list[str]
    validated_on: str
    out_root: Path
    gold_root: Path
    suite: str = ""  # regex over test names for `auto`; empty = whole suite


@dataclass
class Runs:
    test: str
    also_fails: list[str]
    clean: RunResult
    buggy: RunResult


logger = logging.getLogger("stead.bake")
KEEP_PASS = False  # ship the clean run's log and wave too; off: a pass wave hands the solver the diff


def _build(cid: str, what: str) -> None:
    logger.info("build %s tree", what)
    try:
        build(cid)
    except BuildError as e:
        raise BakeError(f"{what} tree does not build:\n{e}") from e


def _expect(res: RunResult, status: RunStatus, what: str) -> None:
    if res.status is not status:
        tail = res.log.read_text()[-2000:]
        raise BakeError(f"{what} tree must {status.name}, got {res.status.name}\n{tail}")


def _runs_fixed(spec: BakeSpec, cid: str, work: Path) -> Runs:
    patch_applies(cid, spec.bug_patch)  # before the clean run: a bad patch should not cost one
    logger.info("run %s on clean tree", spec.test)
    clean = run(cid, spec.test, work / "run_pass", dump=KEEP_PASS)
    _expect(clean, RunStatus.PASS, "clean")
    apply_patch(cid, spec.bug_patch)
    _build(cid, "buggy")
    logger.info("run %s on buggy tree", spec.test)
    buggy = run(cid, spec.test, work / "run_fail")
    _expect(buggy, RunStatus.FAIL, "buggy")
    return Runs(spec.test, [], clean, buggy)


def _pick(rows: list[tuple[RunStatus, str]], out: Path) -> tuple[str, list[str]]:
    """The failing test to build the case on (one with a STEAD line first, then by name), and the rest."""
    fails = sorted(t for s, t in rows if s is RunStatus.FAIL)
    if not fails:
        raise BakeError(f"buggy tree must FAIL: suite passed ({len(rows)} tests)")
    with_stead = [t for t in fails if parse_log(out / t / "sim.log") is not None]
    test = (with_stead or fails)[0]
    return test, [t for t in fails if t != test]


def _runs_auto(spec: BakeSpec, cid: str, work: Path) -> Runs:
    apply_patch(cid, spec.bug_patch)
    _build(cid, "buggy")
    logger.info("suite on buggy tree%s", f" ({spec.suite})" if spec.suite else "")
    rows = suite(cid, work / "suite", spec.suite)
    test, also = _pick(rows, work / "suite")
    logger.info("picked %s; also fails: %s", test, also)
    buggy = run(cid, test, work / "run_fail")
    _expect(buggy, RunStatus.FAIL, "buggy")
    apply_patch(cid, spec.bug_patch, reverse=True)
    _build(cid, "clean")
    clean = run(cid, test, work / "run_pass", dump=KEEP_PASS)
    _expect(clean, RunStatus.PASS, "clean")
    return Runs(test, also, clean, buggy)


LOG_MAX = 20_000_000  # bytes; a trace bigger than this stays out of the case


def _keep(res: RunResult, work: Path, name: str) -> str | None:
    """Copy a run's sim.log as <name>.log, every other log it wrote by its own name, and its dump;
    return the dump's relative path."""
    shutil.copy(res.log, work / "logs" / f"{name}.log")
    for f in sorted(res.log.parent.iterdir()):
        small = f.is_file() and f.suffix != ".elf" and f.stat().st_size <= LOG_MAX
        if small and f not in (res.log, res.dump):
            shutil.copy(f, work / "logs" / f.name)
    if res.dump is None:
        return None
    rel = f"waves/{name}{res.dump.suffix}"
    shutil.copy(res.dump, work / rel)
    return rel


def _resolve_stead(res: RunResult, dump_rel: str | None) -> tuple[Stead | None, str]:
    """Validate the FAIL line against the dump. Returns (record or None, note)."""
    if res.stead is None:
        logger.info("no STEAD line in fail log; case ships with stead: null")
        return None, ""
    if res.dump is None:
        return None, "STEAD dropped: no dump written. "
    ok, why = validate_stead(res.stead, res.dump)
    if not ok:
        logger.info("STEAD dropped: %s", why)
        return None, f"STEAD dropped: {why}. "
    return replace(res.stead, dump=dump_rel), ""


def _write_gold(spec: BakeSpec, gold_dir: Path) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    (gold_dir / "bug.patch").write_text(spec.bug_patch)
    replace(spec.gold, patch="bug.patch").save(gold_dir / "gold.yaml")


def bake(spec: BakeSpec) -> Path:
    case_dir = Path(spec.out_root) / spec.repo / spec.id
    if case_dir.exists():
        raise BakeError(f"{case_dir} already exists")
    bad = [f for f in patchlib.touched_files(spec.bug_patch) if not matches_any(f, spec.dut_paths)]
    if bad:
        raise BakeError(f"bug patch touches files outside dut_paths: {bad}")

    logger.info("%s: container from %s", spec.id, spec.image)
    cid = container.start(spec.image)
    work = case_dir.parent / f".{spec.id}.baking"
    try:
        shutil.rmtree(work, ignore_errors=True)
        (work / "logs").mkdir(parents=True)
        (work / "waves").mkdir()
        runs = _runs_auto(spec, cid, work) if spec.test == "auto" else _runs_fixed(spec, cid, work)
        if KEEP_PASS:
            _keep(runs.clean, work, "pass")
        dump_rel = _keep(runs.buggy, work, "fail")
        stead, note = _resolve_stead(runs.buggy, dump_rel)
        for d in ("run_pass", "run_fail", "suite"):
            shutil.rmtree(work / d, ignore_errors=True)
        case = Case(
            id=spec.id,
            repo=spec.repo,
            url=spec.url,
            commit=spec.commit,
            image=spec.image,
            image_digest=container.image_id(spec.image),
            test=runs.test,
            dump=dump_rel,
            validated_on=spec.validated_on,
            also_fails=runs.also_fails,
            dut_paths=spec.dut_paths,
            checker_paths=spec.checker_paths,
            stead=stead,
            notes=note.strip(),
        )
        case.save(work / "case.yaml")
        (work / "README.md").write_text(_readme(case))
        _write_gold(spec, Path(spec.gold_root) / spec.repo / spec.id)
        work.rename(case_dir)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        container.stop(cid)
    logger.info("%s: baked -> %s", spec.id, case_dir)
    return case_dir


def _readme(c: Case) -> str:
    s = c.stead
    if s:
        stead_txt = (
            f"| Signal | `{s.signal}` |\n| Time | {s.time} |\n| Expected | `0x{s.expected:x}` |\n"
            f"| Actual | `0x{s.actual:x}` |\n| Dump | `{s.dump}` |\n"
        )
    else:
        stead_txt = "No STEAD record for this case (the checker did not yield a validated signal/time).\n"
    also = f" It also fails {', '.join(f'`{t}`' for t in c.also_fails)}." if c.also_fails else ""
    return f"""# {c.id}

Repo `{c.repo}` ({c.url}) at `{c.commit}`. Test `{c.test}` fails on this tree; it passes on the
unmodified commit.{also} Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  ({c.dut_paths}) or in the testbench ({c.checker_paths}); say which.
- `logs/fail.log` — the failing run's verdict, and next to it every other log that run wrote
  (traces, console, bus logs). `tools/` — scripts for them; the skill says what each does.
- `waves/` — the failing run's dump (`{c.dump or "none"}`).

## STEAD

| | |
|---|---|
{stead_txt}
## Hand back

One JSON file:

    {{"method", "case": "{c.id}", "k", "lines": [{{"file", "line", "confidence"}}],
     "patch", "text", "cost": {{"usd", "wall_s"}}}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`{c.test}`{" and the other failing tests" if c.also_fails else ""} go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
"""
