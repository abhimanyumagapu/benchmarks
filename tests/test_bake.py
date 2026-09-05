import pytest

from stead.bake import BakeError, BakeSpec, bake
from stead.case import Case
from stead.gold import Gold
from stead.recipe import ScriptRecipe
from tests.conftest import FIX, git


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
    d.update(kw)
    return BakeSpec(**d)


def test_bake_writes_case_folder_and_gold(src_repo, bug_patch, tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    case_dir = bake(spec(src_repo, bug_patch, tmp_path), r)
    assert case_dir == tmp_path / "cases" / "fake" / "fake-0001"
    c = Case.load(case_dir / "case.yaml")
    assert c.test == "xor_test" and c.kind == "injected"
    assert len(c.commit) == 40  # resolved, not "HEAD"
    assert "BUG" in (case_dir / "tree" / "rtl" / "alu.sv").read_text()
    assert not (case_dir / "tree" / ".git").exists()
    assert (case_dir / "logs" / "pass.log").read_text().startswith("PASS")
    assert (case_dir / "logs" / "fail.log").read_text().startswith("FAIL")
    assert (case_dir / "waves" / "fail.vcd").exists() and (case_dir / "waves" / "pass.vcd").exists()
    assert c.dump == "waves/fail.vcd"
    assert c.stead is not None and c.stead.actual == 0xFFFFF810 and c.stead.dump == "waves/fail.vcd"
    assert (case_dir / "README.md").exists()
    g = Gold.load(tmp_path / "gold" / "fake" / "fake-0001" / "gold.yaml")
    assert g.hit("rtl/alu.sv", 2) and g.patch == "bug.patch"
    assert (tmp_path / "gold" / "fake" / "fake-0001" / "bug.patch").read_text() == bug_patch
    assert not (case_dir / "gold.yaml").exists()  # gold never inside the case folder


def test_bake_refuses_patch_outside_dut_paths(src_repo, bug_patch, tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    bad = bug_patch.replace("rtl/alu.sv", "dv/tb.sv")
    with pytest.raises(BakeError, match="dut_paths"):
        bake(spec(src_repo, bad, tmp_path), r)


def test_bake_aborts_if_clean_tree_does_not_pass(src_repo, bug_patch, tmp_path):

    (src_repo / "rtl" / "alu.sv").write_text("module alu; // BUG already here\nendmodule\n")
    git(src_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "broken")
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    with pytest.raises(BakeError, match="clean tree"):
        bake(spec(src_repo, bug_patch, tmp_path), r)


def test_bake_aborts_if_buggy_tree_crashes_instead_of_failing(src_repo, tmp_path):

    (src_repo / "rtl" / "alu.sv").write_text("module alu; // HANG\nendmodule\n")
    hang = git(src_repo, "diff")
    git(src_repo, "checkout", "--", ".")
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    with pytest.raises(BakeError, match="CRASH"):
        bake(spec(src_repo, hang, tmp_path), r)


def test_bake_drops_stead_that_does_not_match_dump(src_repo, bug_patch, tmp_path):
    # make the recipe lie: FAIL line says actual=0x1234, dump says 0xfffff810
    lying = tmp_path / "lying.sh"
    lying.write_text(
        (FIX / "fakerepo" / "run.sh")
        .read_text()
        .replace("actual=0xfffff810", "actual=0x00001234")
        .replace('HERE=$(cd "$(dirname "$0")" && pwd)', f"HERE={FIX}/fakerepo")
    )
    lying.chmod(0o755)
    r = ScriptRecipe("fake", lying)
    case_dir = bake(spec(src_repo, bug_patch, tmp_path), r)
    c = Case.load(case_dir / "case.yaml")
    assert c.stead is None
    assert "dump@t" in c.notes
