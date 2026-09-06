"""stead <command> <args>

    image tools <tools_dir> | image <repo> <mirror_dir> [<commit>]
    push <repo|tools|--all> <registry> | pull <repo|tools|--all> <registry>
    bake <spec.yaml> | bake --all <specs_dir>
    solve <case_dir> [method] [trials] | solve --all <method> [trials]
        method: claude | claude-<alias> | <provider>/<model>, with +<effort>; trials > 1 for pass@k
    score <submission.json> | score --all
    check <case_dir> | check --all
    table | validate <sim.log>
    ship <case_dir> | ship --all [<dist>]   one case with its tree, or a pre-baked set per core

Any command that walks cases takes, anywhere in the line:

    --repo <a,b>    only these cores          --case <id,id>   only these cases
    --force         redo work that already has a result (solve and score; bake never redoes)

`--all` without --force is a resume: it skips whatever already has a result on disk. STEAD_JOBS
caps how many containers run at once across every repo (default 4).

Run from the bench root: repos/<repo>/{run.sh,repo.yaml}, specs/, cases/, gold/, results/.
results/<case>/<method>[.tN].json is what the agent handed back, .score.json its verdict,
.trajectory.jsonl its transcript; results/index.html is the page.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import progress
from .bake import BakeSpec, bake
from .check import check
from .fail import parse_fail_line
from .gold import Gold
from .image import REPOS, TOOLS_TAG, build_core, build_tools, image_tag, pull, push, repo_cfg
from .score import Submission, score_submission
from .ship import ship, ship_set
from .solve import result_path, runner, solve
from .table import page, summary
from .validate import validate_stead

CASES, GOLD, RESULTS = Path("cases"), Path("gold"), Path("results")
SOLVE_JOBS = 4  # agents at once; a solve holds a container but builds in it only under the sim tool's lock
# Total containers in flight across every repo. The per-repo `jobs` caps are about memory, so they do
# not compose: five cores rebuilding at once is what exhausts a 16 GB box. Raise it on a bigger one.
MAX_JOBS = int(os.environ.get("STEAD_JOBS", "4"))


@dataclass
class Selection:
    """Which cases a command touches and whether it redoes finished work.

    --repo and --case narrow it, --force turns the resume off. One instance lives in
    SELECTED, because the command table dispatches on argv alone and has nowhere to
    thread an argument through.
    """

    repos: list[str] = field(default_factory=list)
    cases: list[str] = field(default_factory=list)
    force: bool = False

    def keep(self, repo: str, case_id: str) -> bool:
        """True unless a --repo or --case was given that this one does not match."""
        return (not self.repos or repo in self.repos) and (not self.cases or case_id in self.cases)


SELECTED = Selection()


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


def _selected(paths: list[Path], repo_of, id_of) -> list[Path]:
    """`paths` narrowed by --repo and --case. Neither given, nothing is dropped."""
    return [p for p in paths if SELECTED.keep(repo_of(p), id_of(p))]


def _cases() -> list[Path]:
    """Every baked case, or the ones --repo/--case name."""
    all_ = [c for c in sorted(CASES.glob("*/*")) if c.is_dir() and not c.name.startswith(".")]
    return _selected(all_, lambda c: c.parent.name, lambda c: c.name)


def _case_dir(case_id: str) -> Path:
    return next(CASES.glob(f"*/{case_id}"))


def _gold_dir(case_dir: Path) -> Path:
    return GOLD / case_dir.parent.name / case_dir.name


def _by_repo(items: list, repo_of) -> list[tuple[int, list]]:
    """(jobs, items) per repo, each group under that repo's own cap."""
    repos = sorted({repo_of(i) for i in items})
    return [(repo_cfg(r).get("jobs", 1), [i for i in items if repo_of(i) == r]) for r in repos]


def _run_all(what: str, groups: list[tuple[int, list]], label, work, is_bad=None) -> int:
    """Apply `work` to every item of every group, showing one counter and nothing else.

    Every group runs at the same time under its own `jobs` cap -- one core's cap is no reason to
    leave another core's build slot idle -- with STEAD_JOBS capping the total in flight. A run is
    minutes to hours, so the only routine output is `<what> [####....]  7/20`; what each case scored
    is on the page and in its json. Failures print above the counter, because a number cannot carry
    them. `is_bad(result) -> str` names a result that ran but did not pass. Returns the failure count.
    """
    gate = threading.Semaphore(MAX_JOBS)
    counter = progress.Counter(what, sum(len(items) for _, items in groups))

    def tagged(item):
        with gate, progress.tag(label(item)):
            return work(item)

    pools, futures = [], {}
    counter.draw()
    try:
        for jobs, items in groups:
            pool = ThreadPoolExecutor(max_workers=jobs)
            pools.append(pool)
            futures.update({pool.submit(tagged, item): item for item in items})
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                result = fut.result()  # always: this is where the item's exception surfaces
                why = is_bad(result) if is_bad else ""
            except Exception as e:  # noqa: BLE001  one bad item must not stop the batch; the line says why
                why = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
            counter.tick(f"{label(item)}  FAILED  {why}" if why else "")
    finally:
        for pool in pools:
            pool.shutdown(wait=True)
    counter.finish()
    return counter.failed


def bake_all(specs_dir: Path) -> int:
    """Bake every spec without a case yet; one verdict line each. Returns the number of failures."""
    todo = []
    for p in _selected(sorted(specs_dir.glob("*/*.yaml")), lambda p: p.parent.name, lambda p: p.stem):
        if (CASES / p.parent.name / p.stem).exists():
            print(f"{p.stem}  exists")  # --force does not rebake: delete the case dir to redo one
        else:
            todo.append(p)
    return _run_all(
        "baking", _by_repo(todo, lambda p: p.parent.name), lambda p: p.stem, lambda p: bake(load_spec(p))
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


def cmd_ship(case_dir: str, dist: str = "dist") -> int:
    """One case with its tree for a closed tool, or --all: a pre-baked set per core.

    The set is what spares someone the bake, which is minutes per bug and needs every image. It
    carries the cases and their gold and unpacks at the bench root; `stead check --all` then proves
    it landed intact against the images.
    """
    if case_dir != "--all":
        print(ship(Path(case_dir), _gold_dir(Path(case_dir)), Path(dist)))
        return 0
    cases = _cases()
    repos = sorted({c.parent.name for c in cases})
    return _run_all(
        "packing",
        [(len(repos) or 1, repos)],
        lambda repo: repo,
        lambda repo: ship_set(repo, [c for c in cases if c.parent.name == repo], GOLD, Path(dist)),
    )


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
    subs = [p for p in sorted(RESULTS.glob("*/*.json")) if not p.name.endswith(".score.json")]
    subs = _selected(subs, lambda p: _case_dir(p.parent.name).parent.name, lambda p: p.parent.name)
    todo = [p for p in subs if SELECTED.force or not p.with_suffix(".score.json").exists()]
    return _run_all(
        "scoring",
        _by_repo(todo, lambda p: _case_dir(p.parent.name).parent.name),
        lambda p: f"{p.parent.name} {p.stem}",
        _score,
    )


def cmd_solve(case_dir: str, method: str = "claude", trials: str = "1") -> int:
    runner(method)  # a typo must fail here, not once per case
    if case_dir != "--all":
        for t in range(1, int(trials) + 1):
            print(solve(Path(case_dir), _gold_dir(Path(case_dir)), method, RESULTS, t))
        return 0
    every = [(c, t) for c in _cases() for t in range(1, int(trials) + 1)]
    todo = [
        ct for ct in every if SELECTED.force or not result_path(RESULTS, ct[0].name, method, ct[1]).exists()
    ]
    return _run_all(
        "solving",
        [(SOLVE_JOBS, todo)],  # the sim tool serializes builds per image itself
        lambda ct: f"{ct[0].name} t{ct[1]}",
        lambda ct: solve(ct[0], _gold_dir(ct[0]), method, RESULTS, ct[1]),
    )


def cmd_check(case_dir: str) -> int:
    """Re-run a case's test in a container (clean must PASS, buggy must FAIL) and re-validate STEAD."""
    cases = _cases() if case_dir == "--all" else [Path(case_dir)]
    return _run_all(
        "checking",
        _by_repo(cases, lambda c: c.parent.name),
        lambda c: c.name,
        lambda c: check(c, _gold_dir(c)),
        lambda why: "" if why == "ok" else why,
    )


def cmd_table() -> int:
    """Write results/index.html -- the page, ready to serve -- and print the leaderboard here."""
    results = []
    for path in sorted(RESULTS.glob("*/*.score.json")):
        verdict = json.loads(path.read_text())
        if not SELECTED.keep(verdict.get("repo", "?"), verdict.get("case", "?")):
            continue
        # the page links out to what is on disk: the transcript, and the submission behind an error
        for key, name in (
            ("trajectory", path.name.replace(".score.json", ".trajectory.jsonl")),
            ("submission", path.name.replace(".score.json", ".json")),
        ):
            if path.with_name(name).exists():
                verdict[key] = f"{path.parent.name}/{name}"
        results.append(verdict)
    out = RESULTS / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(results))
    print(summary(results))
    print(f"\n{out}")
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


def _take_options(argv: list[str]) -> list[str]:
    """Pull --repo, --case and --force out of argv wherever they sit; return the positional rest.

    --repo and --case narrow what a command walks; both repeat and both take a comma-separated list
    (`--repo ibex,scr1`, `--case=scr1-0001`). --force makes solve and score redo work that already
    has a result on disk, instead of skipping it. Bake never redoes: delete the case dir for that.
    """
    into = {"--repo": SELECTED.repos, "--case": SELECTED.cases}
    rest, args = [], iter(argv)
    for arg in args:
        name, equals, value = arg.partition("=")
        if arg == "--force":
            SELECTED.force = True
        elif name in into:
            into[name].extend(v for v in (value if equals else next(args, "")).split(",") if v)
        else:
            rest.append(arg)
    return rest


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    progress.setup()
    argv = _take_options(argv)
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
