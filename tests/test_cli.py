"""The whole loop runs from the command line: bake, score, table, ship; bake --all keeps going."""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

from stead.__main__ import bake_all
from stead.ship import ship
from stead.table import table
from tests.conftest import FIX

ENV = {
    "PYTHONPATH": str(Path(__file__).parent.parent),
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def stead(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "stead", *args], text=True, capture_output=True, cwd=cwd, env=ENV, check=False
    )


def write_spec(specs, src_repo, bug_patch, sid, test):
    (specs / f"{sid}.patch").write_text(bug_patch)
    (specs / f"{sid}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": sid,
                "repo": "fake",
                "url": str(src_repo),
                "commit": "HEAD",
                "test": test,
                "bug_patch": f"{sid}.patch",
                "gold": {"file": "rtl/alu.sv", "start": 2, "end": 2, "class": "logic"},
                "dut_paths": ["rtl/**"],
                "checker_paths": ["dv/**"],
                "validated_on": "fake-sim",
            }
        )
    )


def test_bake_score_table_from_the_command_line(src_repo, bug_patch, tmp_path):
    (tmp_path / "repos" / "fake").mkdir(parents=True)
    (tmp_path / "repos" / "fake" / "run.sh").symlink_to(FIX / "fakerepo" / "run.sh")
    write_spec(tmp_path, src_repo, bug_patch, "fake-0001", "xor_test")
    assert stead("bake", "fake-0001.yaml", cwd=tmp_path).returncode == 0
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
    assert "| claude | 1 | 1/1 | 1/1 | 0/1 | 1.00 | 60 |" in table(tmp_path / "results")


def test_bake_all_skips_existing_and_reports_failures(src_repo, bug_patch, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repos" / "fake").mkdir(parents=True)
    (tmp_path / "repos" / "fake" / "run.sh").symlink_to(FIX / "fakerepo" / "run.sh")
    specs = tmp_path / "specs" / "fake"
    specs.mkdir(parents=True)
    write_spec(specs, src_repo, bug_patch, "fake-0001", "xor_test")
    write_spec(specs, src_repo, bug_patch, "fake-0002", "add_test")  # passes on the buggy tree
    assert bake_all(tmp_path / "specs") == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("fake-0001  baked") and out[1].startswith(
        "fake-0002  FAILED  buggy tree must FAIL"
    )
    assert bake_all(tmp_path / "specs") == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("fake-0001  exists")


def test_ship_tars_the_case_folder(baked_case, tmp_path):
    with tarfile.open(ship(baked_case, tmp_path / "out")) as t:
        names = t.getnames()
    assert "fake-0001/case.yaml" in names and "fake-0001/tree/rtl/alu.sv" in names
    assert not any("gold" in n for n in names)
