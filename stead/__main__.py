"""stead <command> <args>

    image tools <tools_dir> | image <repo> <mirror_dir> [<commit>]
    push <repo|tools|--all> <registry> | pull <repo|tools|--all> <registry>
    bake <spec.yaml> | bake --all <specs_dir>
    solve <case_dir> [method] [trials] | solve --all <method> [trials]
        method: claude | claude-<alias> | <provider>/<model>, with +<effort>; trials > 1 for pass@k
    score <submission.json> | score --all
    check <case_dir> | check --all
    table | ship <case_dir> | validate <sim.log>

Run from the bench root: repos/<repo>/{run.sh,repo.yaml}, specs/, cases/, gold/, results/.
results/<case>/<method>[.tN].json is what the agent handed back, .score.json its verdict,
.trajectory.jsonl its transcript.
"""

from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .bake import BakeSpec, bake
from .check import check
from .fail import parse_fail_line
from .gold import Gold
from .image import REPOS, TOOLS_TAG, build_core, build_tools, image_tag, pull, push, repo_cfg
from .score import Submission, score_submission
from .ship import ship
from .solve import result_path, runner, solve
from .table import table
from .validate import validate_stead

CASES, GOLD, RESULTS = Path("cases"), Path("gold"), Path("results")
SOLVE_JOBS = 4  # agents at once; a solve holds a container but builds in it only under the sim tool's lock


def load_spec(spec_path: Path) -> BakeSpec:
    d = yaml.safe_load(spec_path.read_text())
    repo = spec_path.parent.name
    cfg = repo_cfg(repo)
    g = d.pop("gold")
    commit = d.pop("commit", cfg["commit"])  # a case may live at any commit of its core
    return BakeSpec(
        repo=repo,
        url=cfg["url"],
        commit=commit,
        image=image_tag(repo, commit),
        dut_paths=cfg["dut_paths"],
        checker_paths=cfg["checker_paths"],
        validated_on=cfg["validated_on"],
        gold=Gold(file=g["file"], start=g["start"], end=g["end"], klass=g.get("class", "")),
        bug_patch=(spec_path.parent / d.pop("bug_patch")).read_text(),
        out_root=CASES,
        gold_root=GOLD,
        **d,
    )


def _cases() -> list[Path]:
    return [c for c in sorted(CASES.glob("*/*")) if c.is_dir() and not c.name.startswith(".")]


def _case_dir(case_id: str) -> Path:
    return next(CASES.glob(f"*/{case_id}"))


def _gold_dir(case_dir: Path) -> Path:
    return GOLD / case_dir.parent.name / case_dir.name


def _by_repo(items: list, repo_of) -> list[tuple[int, list]]:
    """(jobs, items) per repo in repo order, so --all runs one repo at a time under its own cap."""
    repos = sorted({repo_of(i) for i in items})
    return [(repo_cfg(r).get("jobs", 1), [i for i in items if repo_of(i) == r]) for r in repos]


def _run_all(groups: list[tuple[int, list]], label, work, verdict) -> int:
    """Apply `work` to every item of every group, `jobs` at a time; one line per item.
    `verdict(item, result) -> (line, failed)`. Returns the number of failures."""
    failed = 0
    for jobs, items in groups:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [(item, pool.submit(work, item)) for item in items]
            for item, fut in futures:
                try:
                    line, bad = verdict(item, fut.result())
                except Exception as e:  # noqa: BLE001  one bad item must not stop the batch; the line says why
                    line, bad = (
                        f"FAILED  {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}",
                        True,
                    )
                failed += bad
                print(f"{label(item)}  {line}", flush=True)
    return failed


def bake_all(specs_dir: Path) -> int:
    """Bake every spec without a case yet; one verdict line each. Returns the number of failures."""
    todo = []
    for p in sorted(specs_dir.glob("*/*.yaml")):
        if (CASES / p.parent.name / p.stem).exists():
            print(f"{p.stem}  exists")
        else:
            todo.append(p)
    return _run_all(
        _by_repo(todo, lambda p: p.parent.name),
        lambda p: p.stem,
        lambda p: bake(load_spec(p)),
        lambda _p, case_dir: (f"baked  {case_dir}", False),
    )


def cmd_bake(spec_path: str, specs_dir: str = "") -> int:
    if spec_path == "--all":
        return 1 if bake_all(Path(specs_dir)) else 0
    print(bake(load_spec(Path(spec_path))))
    return 0


def cmd_image(repo: str, src_dir: str, commit: str = "") -> int:
    """Build the tools image from a prebuilt tools dir, or a core image from its mirror."""
    if repo == "tools":
        print(build_tools(Path(src_dir)))
        return 0
    print(*build_core(repo, Path(src_dir), commit))
    return 0


def _images(what: str) -> list[str]:
    """`tools`, a core at its pinned commit, or `--all`: tools, every core, every image a spec needs."""
    if what == "tools":
        return [TOOLS_TAG]
    if what != "--all":
        return [image_tag(what, repo_cfg(what)["commit"])]
    tags = {image_tag(p.parent.name, repo_cfg(p.parent.name)["commit"]) for p in REPOS.glob("*/repo.yaml")}
    for p in Path("specs").glob("*/*.yaml"):  # a spec may pin its own commit
        commit = yaml.safe_load(p.read_text()).get("commit", repo_cfg(p.parent.name)["commit"])
        tags.add(image_tag(p.parent.name, commit))
    return [TOOLS_TAG, *sorted(tags)]


def cmd_push(what: str, registry: str) -> int:
    for tag in _images(what):
        print(push(tag, registry))
    return 0


def cmd_pull(what: str, registry: str) -> int:
    for tag in _images(what):
        print(pull(tag, registry))
    return 0


def cmd_ship(case_dir: str) -> int:
    print(ship(Path(case_dir), _gold_dir(Path(case_dir)), Path("dist")))
    return 0


def _score(sub_path: Path) -> dict:
    sub = Submission.load(sub_path)
    case_dir = _case_dir(sub.case)
    res = score_submission(case_dir, _gold_dir(case_dir), sub)
    out = result_path(RESULTS, sub.case, sub.method, sub.trial).with_suffix(".score.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    return res


def cmd_score(sub_path: str) -> int:
    if sub_path != "--all":
        print(json.dumps(_score(Path(sub_path)), indent=2))
        return 0
    todo = [
        p
        for p in sorted(RESULTS.glob("*/*.json"))
        if not p.name.endswith(".score.json") and not p.with_suffix(".score.json").exists()
    ]
    return _run_all(
        _by_repo(todo, lambda p: _case_dir(p.parent.name).parent.name),
        str,
        _score,
        lambda _p, res: (f"hit_rank={res['hit_rank']}  patch={(res['patch'] or {}).get('fixed')}", False),
    )


def cmd_solve(case_dir: str, method: str = "claude", trials: str = "1") -> int:
    runner(method)  # a typo must fail here, not once per case
    if case_dir != "--all":
        for t in range(1, int(trials) + 1):
            print(solve(Path(case_dir), _gold_dir(Path(case_dir)), method, RESULTS, t))
        return 0
    todo = [
        (c, t)
        for c in _cases()
        for t in range(1, int(trials) + 1)
        if not result_path(RESULTS, c.name, method, t).exists()
    ]
    return _run_all(
        [(SOLVE_JOBS, todo)],  # the sim tool serializes builds per image itself
        lambda ct: f"{ct[0]} t{ct[1]}",
        lambda ct: solve(ct[0], _gold_dir(ct[0]), method, RESULTS, ct[1]),
        lambda _ct, path: (f"solved  {path}", False),
    )


def cmd_check(case_dir: str) -> int:
    """Re-run a case's test in a container (clean must PASS, buggy must FAIL) and re-validate STEAD."""
    cases = _cases() if case_dir == "--all" else [Path(case_dir)]
    return _run_all(
        _by_repo(cases, lambda c: c.parent.name),
        str,
        lambda c: check(c, _gold_dir(c)),
        lambda _c, why: (why, why != "ok"),
    )


def cmd_table() -> int:
    md = table(RESULTS)
    (RESULTS / "table.md").write_text(md)
    print(md)
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
        "image": cmd_image,
        "push": cmd_push,
        "pull": cmd_pull,
        "bake": cmd_bake,
        "ship": cmd_ship,
        "solve": cmd_solve,
        "score": cmd_score,
        "check": cmd_check,
        "validate": cmd_validate,
        "table": cmd_table,
    }
    if not argv or argv[0] not in cmds:
        print(__doc__, file=sys.stderr)
        return 64
    return cmds[argv[0]](*argv[1:])


if __name__ == "__main__":
    sys.exit(main())
