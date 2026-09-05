"""A case is real only if the clean tree passes, the buggy tree fails on a value check,
patches stay on their side of the DUT/checker line, and gold never ships with the case."""

import pytest

from stead.bake import BakeError, BakeSpec, bake
from stead.case import Case
from stead.gold import Gold
from stead.recipe import BuildError, RunStatus, ScriptRecipe
from tests.conftest import FIX, git

RECIPE = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")


def spec(src_repo, bug_patch, tmp_path, **kw):
    d = dict(
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
    return BakeSpec(**{**d, **kw})


def edit_and_diff(src_repo, rel, text):
    (src_repo / rel).write_text(text)
    diff = git(src_repo, "diff")
    git(src_repo, "checkout", "--", ".")
    return diff


def test_bake_writes_case_with_stead_and_gold_outside_it(src_repo, bug_patch, tmp_path):
    case_dir = bake(spec(src_repo, bug_patch, tmp_path), RECIPE)
    c = Case.load(case_dir / "case.yaml")
    assert len(c.commit) == 40 and c.dump == "waves/fail.vcd"
    assert c.stead.actual == 0xFFFFF810 and c.stead.dump == "waves/fail.vcd"
    assert "BUG" in (case_dir / "tree" / "rtl" / "alu.sv").read_text()
    assert not (case_dir / "tree" / ".git").exists()
    assert (case_dir / "logs" / "pass.log").exists() and (case_dir / "waves" / "pass.vcd").exists()
    assert not list(case_dir.rglob("gold.yaml")) and not list(case_dir.rglob("bug.patch"))
    g = Gold.load(tmp_path / "gold" / "fake" / "fake-0001" / "gold.yaml")
    assert g.hit("rtl/alu.sv", 2) and not g.hit("rtl/alu.sv", 3) and not g.hit("dv/tb.sv", 2)


def test_bug_patch_must_stay_in_dut_and_shim_must_stay_out(src_repo, bug_patch, tmp_path):
    with pytest.raises(BakeError, match="dut_paths"):
        bake(spec(src_repo, bug_patch.replace("rtl/alu.sv", "dv/tb.sv"), tmp_path), RECIPE)
    with pytest.raises(BakeError, match="shim patch touches dut_paths"):
        bake(spec(src_repo, bug_patch, tmp_path, shim_patch=bug_patch), RECIPE)


def test_shim_is_applied_before_the_clean_run(src_repo, bug_patch, tmp_path):
    shim = edit_and_diff(src_repo, "dv/tb.sv", "module tb; // STEAD write tracker\nendmodule\n")
    case_dir = bake(spec(src_repo, bug_patch, tmp_path, shim_patch=shim), RECIPE)
    assert "write tracker" in (case_dir / "tree" / "dv" / "tb.sv").read_text()


def test_clean_must_pass_and_buggy_must_fail_not_crash(src_repo, bug_patch, tmp_path):
    hang = edit_and_diff(src_repo, "rtl/alu.sv", "module alu; // HANG\nendmodule\n")
    with pytest.raises(BakeError, match="CRASH"):
        bake(spec(src_repo, hang, tmp_path), RECIPE)
    (src_repo / "rtl" / "alu.sv").write_text("module alu; // BUG already here\nendmodule\n")
    git(src_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "broken")
    with pytest.raises(BakeError, match="clean tree must PASS"):
        bake(spec(src_repo, bug_patch, tmp_path), RECIPE)


def test_stead_that_disagrees_with_dump_is_dropped_not_fatal(src_repo, bug_patch, tmp_path):
    lying = tmp_path / "lying.sh"
    lying.write_text(
        (FIX / "fakerepo" / "run.sh")
        .read_text()
        .replace("actual=0xfffff810", "actual=0x00001234")
        .replace('HERE=$(cd "$(dirname "$0")" && pwd)', f"HERE={FIX}/fakerepo")
    )
    lying.chmod(0o755)
    c = Case.load(bake(spec(src_repo, bug_patch, tmp_path), ScriptRecipe("fake", lying)) / "case.yaml")
    assert c.stead is None and "dump@t" in c.notes


def test_recipe_exit_codes_map_to_status_and_crash_is_never_fail(tmp_path):
    def tree(text):
        t = tmp_path / text
        (t / "rtl").mkdir(parents=True)
        (t / "rtl" / "alu.sv").write_text(text)
        return t

    with pytest.raises(BuildError):
        RECIPE.build(tree("SYNTAX_ERROR"))
    for text, status in [("clean", RunStatus.PASS), ("BUG", RunStatus.FAIL), ("HANG", RunStatus.CRASH)]:
        t = tree(text)
        RECIPE.build(t)
        assert RECIPE.run(t, "xor_test", tmp_path / f"out-{text}").status is status
