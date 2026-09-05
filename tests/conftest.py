import subprocess
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout


@pytest.fixture
def src_repo(tmp_path: Path) -> Path:
    """A tiny git repo shaped like a core: rtl/ (DUT) and dv/ (checker)."""
    repo = tmp_path / "src"
    (repo / "rtl").mkdir(parents=True)
    (repo / "dv").mkdir()
    (repo / "rtl" / "alu.sv").write_text("module alu;\n  assign y = a ^ b;\nendmodule\n")
    (repo / "dv" / "tb.sv").write_text("module tb;\nendmodule\n")
    git(repo, "init", "-q")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "clean")
    return repo


@pytest.fixture
def bug_patch(src_repo: Path) -> str:
    """Unified diff flipping bit 4 of the XOR result (touches rtl/ only)."""
    alu = src_repo / "rtl" / "alu.sv"
    alu.write_text("module alu;\n  assign y = (a ^ b) ^ 32'h10; // BUG\nendmodule\n")
    diff = git(src_repo, "diff")
    git(src_repo, "checkout", "--", ".")
    return diff


@pytest.fixture
def fix_patch(src_repo: Path) -> str:
    """The reverse of bug_patch: applied to the buggy tree it restores the clean RTL."""
    alu = src_repo / "rtl" / "alu.sv"
    alu.write_text("module alu;\n  assign y = (a ^ b) ^ 32'h10; // BUG\nendmodule\n")
    diff = git(src_repo, "diff", "-R")
    git(src_repo, "checkout", "--", ".")
    return diff


@pytest.fixture
def baked_case(src_repo: Path, bug_patch: str, tmp_path: Path) -> Path:
    """A real baked case (fake repo, XOR bit-4 bug) under tmp_path/cases."""
    from stead.bake import BakeSpec, bake
    from stead.gold import Gold
    from stead.recipe import ScriptRecipe

    spec = BakeSpec(
        id="fake-0001",
        repo="fake",
        url=str(src_repo),
        commit="HEAD",
        test="xor_test",
        bug_patch=bug_patch,
        gold=Gold(file="rtl/alu.sv", start=2, end=2, klass="logic"),
        dut_paths=["rtl/**"],
        checker_paths=["dv/**"],
        validated_on="fake-sim",
        out_root=tmp_path / "cases",
        gold_root=tmp_path / "gold",
    )
    return bake(spec, ScriptRecipe("fake", FIX / "fakerepo" / "run.sh"))
