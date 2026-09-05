"""Stage 1: turn (repo, commit, test, bug patch, gold) into a case folder.

clone at commit -> build -> run clean: must PASS
apply bug patch (dut_paths only) -> build -> run: must FAIL (not crash)
STEAD line -> validate against dump -> keep, or drop to null with the reason
write cases/<repo>/<id>/ (tree without .git, logs, waves, case.yaml, README)
write gold/<repo>/<id>/ (gold.yaml, bug.patch) -- never inside the case folder
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from . import patch as patchlib
from .case import Case, matches_any
from .fail import Stead
from .gold import Gold
from .recipe import BuildError, RunResult, RunStatus, ScriptRecipe
from .validate import validate_stead


class BakeError(RuntimeError):
    pass


@dataclass
class BakeSpec:
    id: str
    repo: str
    url: str
    commit: str
    test: str
    bug_patch: str
    gold: Gold
    dut_paths: list[str]
    checker_paths: list[str]
    validated_on: str
    out_root: Path
    gold_root: Path
    kind: str = "injected"


def _git(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(["git", *args], check=True, text=True, capture_output=True, cwd=cwd)
    return p.stdout.strip()


logger = logging.getLogger("stead.bake")


def _checkout(url: str, commit: str, dest: Path) -> str:
    _git("clone", "-q", url, str(dest))
    _git("checkout", "-q", commit, cwd=dest)
    _git("submodule", "update", "--init", "--recursive", "-q", cwd=dest)
    return _git("rev-parse", "HEAD", cwd=dest)


def _build_and_run(recipe: ScriptRecipe, tree: Path, test: str, out: Path, what: str) -> RunResult:
    logger.info("build %s tree", what)
    try:
        recipe.build(tree)
    except BuildError as e:
        raise BakeError(f"{what} tree does not build:\n{e}") from e
    logger.info("run %s on %s tree", test, what)
    return recipe.run(tree, test, out)


def _expect(run: RunResult, status: RunStatus, what: str) -> None:
    if run.status is not status:
        tail = run.log.read_text()[-2000:]
        raise BakeError(f"{what} tree must {status.name}, got {run.status.name}\n{tail}")


def _keep(run: RunResult, work: Path, name: str) -> str | None:
    """Copy a run's log and dump into the case; return the dump's relative path."""
    shutil.copy(run.log, work / "logs" / f"{name}.log")
    if run.dump is None:
        return None
    rel = f"waves/{name}{run.dump.suffix}"
    shutil.copy(run.dump, work / rel)
    return rel


def _resolve_stead(run: RunResult, dump_rel: str | None) -> tuple[Stead | None, str]:
    """Validate the FAIL line against the dump. Returns (record or None, note)."""
    if run.stead is None:
        logger.info("no STEAD line in fail log; case ships with stead: null")
        return None, ""
    if run.dump is None:
        return None, "STEAD dropped: no dump written. "
    ok, why = validate_stead(run.stead, run.dump)
    if not ok:
        logger.info("STEAD dropped: %s", why)
        return None, f"STEAD dropped: {why}. "
    return replace(run.stead, dump=dump_rel), ""


def _strip_tree(tree: Path) -> None:
    shutil.rmtree(tree / ".git", ignore_errors=True)
    for p in tree.rglob(".git"):
        if p.is_file():  # submodule gitlinks
            p.unlink()


def _write_gold(spec: BakeSpec, gold_dir: Path) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    (gold_dir / "bug.patch").write_text(spec.bug_patch)
    replace(spec.gold, patch="bug.patch").save(gold_dir / "gold.yaml")


def bake(spec: BakeSpec, recipe: ScriptRecipe) -> Path:
    case_dir = Path(spec.out_root) / spec.repo / spec.id
    if case_dir.exists():
        raise BakeError(f"{case_dir} already exists")
    bad = [f for f in patchlib.touched_files(spec.bug_patch) if not matches_any(f, spec.dut_paths)]
    if bad:
        raise BakeError(f"bug patch touches files outside dut_paths: {bad}")

    work = case_dir.parent / f".{spec.id}.baking"
    shutil.rmtree(work, ignore_errors=True)
    (work / "logs").mkdir(parents=True)
    (work / "waves").mkdir()
    tree = work / "tree"
    try:
        logger.info("%s: clone %s @ %s", spec.id, spec.url, spec.commit)
        sha = _checkout(spec.url, spec.commit, tree)

        clean = _build_and_run(recipe, tree, spec.test, work / "run_pass", "clean")
        _expect(clean, RunStatus.PASS, "clean")
        _keep(clean, work, "pass")

        logger.info("apply bug patch")
        patchlib.apply(tree, spec.bug_patch)
        buggy = _build_and_run(recipe, tree, spec.test, work / "run_fail", "buggy")
        _expect(buggy, RunStatus.FAIL, "buggy")
        dump_rel = _keep(buggy, work, "fail")
        stead, note = _resolve_stead(buggy, dump_rel)

        _strip_tree(tree)
        shutil.rmtree(work / "run_pass", ignore_errors=True)
        shutil.rmtree(work / "run_fail", ignore_errors=True)
        case = Case(
            id=spec.id,
            repo=spec.repo,
            url=spec.url,
            commit=sha,
            kind=spec.kind,
            test=spec.test,
            recipe=recipe.name,
            dump=dump_rel,
            validated_on=spec.validated_on,
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
    return f"""# {c.id}

Repo `{c.repo}` ({c.url}) at `{c.commit}`. Test `{c.test}` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree. The fix goes in {c.dut_paths}.
  {c.checker_paths} is the checker and is off limits.
- `logs/fail.log`, `logs/pass.log` — the failing run and the clean-tree run of the same test.
- `waves/` — the dumps of both runs (`{c.dump or "none"}` is the fail wave).

## STEAD

| | |
|---|---|
{stead_txt}
## Hand back

One JSON file:

    {{"method", "case": "{c.id}", "k", "lines": [{{"file", "line", "confidence"}}],
     "patch", "text", "cost": {{"usd", "wall_s"}}}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must go
FAIL -> PASS touching only {c.dut_paths}. Text is judged.
"""
