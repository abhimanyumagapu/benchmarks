"""stead <command> <args>

    bake <spec.yaml> | bake --all <specs_dir> | ship <case_dir>
    solve <case_dir> [method] | score <submission.json> | table | validate <sim.log>

Run from the bench root: repos/<repo>/run.sh, cases/, gold/, results/.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import yaml

from .bake import BakeError, BakeSpec, bake
from .fail import parse_fail_line
from .gold import Gold
from .recipe import ScriptRecipe
from .score import Submission, score_submission
from .ship import ship
from .solve import solve
from .table import table
from .validate import validate_stead


def _recipe(repo: str) -> ScriptRecipe:
    return ScriptRecipe(repo, Path("repos") / repo / "run.sh")


def load_spec(spec_path: Path) -> BakeSpec:
    d = yaml.safe_load(spec_path.read_text())
    g = d.pop("gold")
    shim = Path("repos") / d["repo"] / "shim.patch"
    return BakeSpec(
        gold=Gold(file=g["file"], start=g["start"], end=g["end"], klass=g.get("class", "")),
        bug_patch=(spec_path.parent / d.pop("bug_patch")).read_text(),
        shim_patch=shim.read_text() if shim.exists() else "",
        out_root=Path("cases"),
        gold_root=Path("gold"),
        **d,
    )


def bake_all(specs_dir: Path) -> int:
    """Bake every spec without a case yet; one verdict line each. Returns the number of failures."""
    failed = 0
    for spec_path in sorted(specs_dir.glob("*/*.yaml")):
        spec = load_spec(spec_path)
        if (spec.out_root / spec.repo / spec.id).exists():
            print(f"{spec.id}  exists")
            continue
        try:
            bake(spec, _recipe(spec.repo))
            print(f"{spec.id}  baked")
        except (BakeError, subprocess.CalledProcessError) as e:
            failed += 1
            print(f"{spec.id}  FAILED  {str(e).splitlines()[0]}")
    return failed


def cmd_bake(spec_path: str, specs_dir: str = "") -> int:
    if spec_path == "--all":
        return 1 if bake_all(Path(specs_dir)) else 0
    spec = load_spec(Path(spec_path))
    print(bake(spec, _recipe(spec.repo)))
    return 0


def cmd_ship(case_dir: str) -> int:
    print(ship(Path(case_dir), Path("dist")))
    return 0


def cmd_score(sub_path: str) -> int:
    sub = Submission.load(sub_path)
    case_dir = next(Path("cases").glob(f"*/{sub.case}"))
    gold_dir = Path("gold") / case_dir.parent.name / sub.case
    res = score_submission(case_dir, gold_dir, sub, _recipe(case_dir.parent.name))
    out = Path("results") / sub.case / f"{sub.method}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


def cmd_solve(case_dir: str, method: str = "claude") -> int:
    print(solve(Path(case_dir), method, Path("results")))
    return 0


def cmd_table() -> int:
    print(table(Path("results")))
    return 0


def cmd_validate(log_path: str) -> int:
    """Check every STEAD FAIL line in a log against its dump (the TB author's self-test)."""
    bad = 0
    for line in Path(log_path).read_text().splitlines():
        s = parse_fail_line(line)
        if s is None:
            continue
        ok, why = validate_stead(s, s.dump)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {s.test} {s.signal} t={s.time} {why}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    cmds = {
        "bake": cmd_bake,
        "ship": cmd_ship,
        "solve": cmd_solve,
        "score": cmd_score,
        "validate": cmd_validate,
        "table": cmd_table,
    }
    if not argv or argv[0] not in cmds:
        print(__doc__, file=sys.stderr)
        return 64
    return cmds[argv[0]](*argv[1:])


if __name__ == "__main__":
    sys.exit(main())
