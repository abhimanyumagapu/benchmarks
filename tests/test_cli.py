import json
import subprocess
import sys
from pathlib import Path

import yaml

from tests.conftest import FIX

ENV = {
    "PYTHONPATH": str(Path(__file__).parent.parent),
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def stead(*args, cwd):
    cmd = [sys.executable, "-m", "stead", *args]
    return subprocess.run(cmd, text=True, capture_output=True, cwd=str(cwd), env=ENV, check=False)


def write_spec(tmp_path, src_repo, bug_patch):
    (tmp_path / "bug.patch").write_text(bug_patch)
    spec = {
        "id": "fake-0001",
        "repo": "fake",
        "url": str(src_repo),
        "commit": "HEAD",
        "test": "xor_test",
        "bug_patch": "bug.patch",
        "gold": {"file": "rtl/alu.sv", "start": 2, "end": 2, "class": "logic"},
        "dut_paths": ["rtl/**"],
        "checker_paths": ["dv/**"],
        "validated_on": "fake-sim",
    }
    p = tmp_path / "fake-0001.yaml"
    p.write_text(yaml.safe_dump(spec))
    return p


def test_bake_then_score_end_to_end(src_repo, bug_patch, tmp_path):
    (tmp_path / "repos" / "fake").mkdir(parents=True)
    (tmp_path / "repos" / "fake" / "run.sh").symlink_to(FIX / "fakerepo" / "run.sh")
    spec = write_spec(tmp_path, src_repo, bug_patch)
    r = stead("bake", str(spec), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    case_dir = tmp_path / "cases" / "fake" / "fake-0001"
    assert (case_dir / "case.yaml").exists()

    sub = tmp_path / "claude.json"
    sub.write_text(
        json.dumps(
            {
                "method": "claude",
                "case": "fake-0001",
                "k": 1,
                "lines": [{"file": "rtl/alu.sv", "line": 2}],
                "cost": {"usd": 1},
            }
        )
    )
    r = stead("score", str(sub), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hit@1"] is True and out["case"] == "fake-0001"
    assert (tmp_path / "results" / "fake-0001" / "claude.json").exists()


def test_validate_reports_ok_for_good_log(tmp_path):
    log = tmp_path / "fail.log"
    log.write_text(
        f"FAIL  test=t  signal=TOP.dut.rvfi_mem_wdata  time=100  expected=0xfffff800  "
        f"actual=0xfffff810  dump={FIX / 'mini.vcd'}\n"
    )
    r = stead("validate", str(log), cwd=tmp_path)
    assert r.returncode == 0 and "OK" in r.stdout


def test_validate_reports_bad_for_wrong_actual(tmp_path):
    log = tmp_path / "fail.log"
    log.write_text(
        f"FAIL  test=t  signal=TOP.dut.rvfi_mem_wdata  time=100  expected=0xfffff800  "
        f"actual=0x1  dump={FIX / 'mini.vcd'}\n"
    )
    r = stead("validate", str(log), cwd=tmp_path)
    assert r.returncode == 1 and "BAD" in r.stdout
