"""The whole loop runs from the command line: bake, score, table, ship; --all keeps going."""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

from stead.__main__ import bake_all
from stead.ship import ship, ship_set
from tests.conftest import BROKEN, BUG_PATCH, COMMIT

ENV = {
    "PYTHONPATH": str(Path(__file__).parent.parent),
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def stead(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "stead", *args], text=True, capture_output=True, cwd=cwd, env=ENV, check=False
    )


def bench(root: Path) -> None:
    """A bench root with the fake repo's repo.yaml."""
    (root / "repos" / "fake").mkdir(parents=True)
    (root / "repos" / "fake" / "repo.yaml").write_text(
        yaml.safe_dump(
            {
                "url": "https://example.org/fake.git",
                "commit": COMMIT,
                "validated_on": "fake-sim",
                "dut_paths": ["rtl/**"],
                "checker_paths": ["dv/**"],
                "jobs": 2,
            }
        )
    )


def write_spec(specs, sid, test, patch=BUG_PATCH, **extra):
    specs.mkdir(parents=True, exist_ok=True)
    (specs / f"{sid}.patch").write_text(patch)
    (specs / f"{sid}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": sid,
                "test": test,
                "bug_patch": f"{sid}.patch",
                "gold": {"file": "rtl/alu.sv", "start": 2, "end": 2, "class": "logic"},
                **extra,
            }
        )
    )


def test_bake_score_table_from_the_command_line(tmp_path):
    bench(tmp_path)
    write_spec(tmp_path / "specs" / "fake", "fake-0001", "xor_test")
    r = stead("bake", "specs/fake/fake-0001.yaml", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    sub = tmp_path / "claude.json"
    sub.write_text(
        json.dumps(
            {
                "method": "claude",
                "case": "fake-0001",
                "k": 1,
                "lines": [{"file": "rtl/alu.sv", "line": 2}],
                "cost": {"usd": 1, "wall_s": 60},
            }
        )
    )
    assert json.loads(stead("score", str(sub), cwd=tmp_path).stdout)["hit@1"] is True
    scored = tmp_path / "results" / "fake-0001" / "claude.score.json"
    assert (
        json.loads(sub.read_text())["lines"] == json.loads(scored.read_text())["lines"]
    )  # submission kept as is
    miss = scored.with_name("claude.t2.score.json")  # a second trial that missed
    miss.write_text(json.dumps({**json.loads(scored.read_text()), "trial": 2, "hit@1": False}))
    out = stead("table", cwd=tmp_path).stdout
    # one case, two trials, hit in one of them: pass@k counts it once
    assert "claude" in out and "100%" in out and "1/1" in out
    html = (tmp_path / "results" / "index.html").read_text()
    assert html.startswith("<!doctype html>") and "</html>" in html
    assert "<title>STEAD-Bench results</title>" in html
    assert "cdn" not in html.lower() and "<script src" not in html  # self-contained: servable as it is
    # the accent must actually be spent, not merely declared: a palette nobody can see is the bug
    assert html.count("var(--blue)") >= 3
    # The page's script has been broken three times by a Python escape reaching the browser: an
    # octal \2191 that printed "91", and a \n that opened a string literal and never closed it. A
    # stray newline inside a quoted string leaves that line with an odd number of quotes, and one
    # bad line kills every behaviour on the page at once.
    script = html[html.index("<script>") + 8 : html.index("</script>")]
    assert not [ln for ln in script.splitlines() if ln.count("'") % 2], "broken string literal"
    assert "\\2" not in html  # no raw escape sequences survived into the page
    # 4 table headers, then a leaderboard row, two trial rows, one repo row and one class row
    assert html.count("<tr>") == 4 + 1 + 2 + 1 + 1
    assert ">fake-0001<" in html and ">fake<" in html and ">logic<" in html
    assert "100%" in html and "1/1" in html
    assert not (tmp_path / "results" / "table.md").exists()  # the page is html now


def test_bake_all_skips_existing_and_reports_failures(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bench(tmp_path)
    specs = tmp_path / "specs" / "fake"
    write_spec(specs, "fake-0001", "xor_test")
    write_spec(specs, "fake-0002", "add_test")  # passes on the buggy tree
    write_spec(specs, "fake-0003", "xor_test", commit=BROKEN)  # another commit of the core: its own image
    assert bake_all(tmp_path / "specs") == 2
    out = capsys.readouterr().out
    # a run prints its counter and its failures, nothing per success
    assert "baking [####################]  3/3  2 failed" in out
    assert "fake-0002  FAILED  BakeError: buggy tree must FAIL" in out
    # fake-0003 is baked on stead-fake:1111111, its own commit's image
    assert "fake-0003  FAILED  BakeError: clean tree must PASS" in out
    assert "fake-0001" not in out.replace("fake-0001  exists", "")  # the one that worked stayed quiet
    assert bake_all(tmp_path / "specs") == 2  # the baked one is skipped, the two failures retried
    assert capsys.readouterr().out.splitlines()[0].startswith("fake-0001  exists")


def test_ship_tars_the_case_folder_with_a_tree_and_no_gold(baked_case, tmp_path):
    gold_dir = tmp_path / "gold" / "fake" / "fake-0001"
    with tarfile.open(ship(baked_case, gold_dir, tmp_path / "out")) as t:
        names = t.getnames()
    assert "fake-0001/case.yaml" in names and "fake-0001/tree/rtl/alu.sv" in names
    assert not any("gold" in n or "bug.patch" in n or "build" in n for n in names)
    assert not (baked_case / "tree").exists()


def test_ship_all_packs_a_repo_set_that_unpacks_at_the_bench_root(baked_case, tmp_path):
    """The pre-baked set spares a bake, so it must carry everything a bake produces and land where
    the harness already looks. It carries gold -- unlike a single shipped case -- because solve
    cannot build the buggy tree without the bug patch. It carries no tree: that comes from the
    image, which is why cases and images travel apart."""
    tar_path = ship_set("fake", [baked_case], tmp_path / "gold", tmp_path / "out")
    with tarfile.open(tar_path) as t:
        names = t.getnames()
        manifest = json.loads(t.extractfile("MANIFEST.json").read())
    assert tar_path.name == "stead-cases-fake.tar.gz"
    # paths are relative to the bench root, so `tar xzf` in it puts both trees where they belong
    assert "cases/fake/fake-0001/case.yaml" in names
    assert "gold/fake/fake-0001/bug.patch" in names and "gold/fake/fake-0001/gold.yaml" in names
    assert not any("/tree/" in n for n in names)  # materialized from the image, never shipped
    # the manifest says which images this set needs, before anyone downloads gigabytes of them
    case = yaml.safe_load((baked_case / "case.yaml").read_text())
    assert manifest["repo"] == "fake" and manifest["images"] == [case["image"]]
    assert manifest["cases"][0]["image_digest"] == case["image_digest"]  # check --all can verify it
    assert [c["id"] for c in manifest["cases"]] == ["fake-0001"]
    assert manifest["cases"][0]["class"] == "logic"
