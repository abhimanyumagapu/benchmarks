"""The whole loop runs from the command line: bake, score, table, ship; --all keeps going."""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

from stead.__main__ import bake_all
from stead.ship import ship
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
    # one case, two trials, hit in one of them: pass@k counts it once; nothing recorded about who ran when
    assert "| claude | 100% | ? | default | 2 | ? | 1 | 1/1 | 1/1 | 0/1 | 0 | 0 | 2.00 | 2m00s |" in out
    assert "| fake-0001 | 1 | fake | logic | 1 | 1 | no patch | 1.00 | 60 | 0 |  |" in out
    assert "| fake-0001 | 2 | fake | logic | 1 | 1 | no patch | 1.00 | 60 | 0 |  |" in out
    assert "| fake | 1 | 1/1 |" in out and "| logic | 1 | 1/1 |" in out
    assert (tmp_path / "results" / "table.md").read_text() == out.rstrip("\n")  # the page on disk is the same


def test_bake_all_skips_existing_and_reports_failures(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bench(tmp_path)
    specs = tmp_path / "specs" / "fake"
    write_spec(specs, "fake-0001", "xor_test")
    write_spec(specs, "fake-0002", "add_test")  # passes on the buggy tree
    write_spec(specs, "fake-0003", "xor_test", commit=BROKEN)  # another commit of the core: its own image
    assert bake_all(tmp_path / "specs") == 2
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("fake-0001  baked")
    assert out[1].startswith("fake-0002  FAILED  BakeError: buggy tree must FAIL")
    assert out[2].startswith(
        "fake-0003  FAILED  BakeError: clean tree must PASS"
    )  # baked on stead-fake:1111111
    assert bake_all(tmp_path / "specs") == 2  # the baked one is skipped, the two failures retried
    assert capsys.readouterr().out.splitlines()[0].startswith("fake-0001  exists")


def test_ship_tars_the_case_folder_with_a_tree_and_no_gold(baked_case, tmp_path):
    gold_dir = tmp_path / "gold" / "fake" / "fake-0001"
    with tarfile.open(ship(baked_case, gold_dir, tmp_path / "out")) as t:
        names = t.getnames()
    assert "fake-0001/case.yaml" in names and "fake-0001/tree/rtl/alu.sv" in names
    assert not any("gold" in n or "bug.patch" in n or "build" in n for n in names)
    assert not (baked_case / "tree").exists()
