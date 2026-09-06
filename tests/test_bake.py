"""A case is real only if the clean tree passes, the buggy tree fails on a value check,
patches stay on their side of the DUT/checker line, and gold never ships with the case.
A tree that leaves the image is exactly the manifest, bug applied, nothing else."""

import pytest
import yaml

from stead import container
from stead.bake import BakeError, bake
from stead.case import Case
from stead.gold import Gold
from stead.image import apply_shim, build_core, export
from stead.recipe import BuildError, RunStatus, build, run
from stead.tree import materialize
from tests.conftest import BUG_PATCH, FAKE, alu_patch, git, spec


def test_bake_writes_case_with_stead_and_gold_outside_it(tmp_path):
    case_dir = bake(spec(tmp_path))
    c = Case.load(case_dir / "case.yaml")
    assert c.image == FAKE and c.image_digest.startswith("sha256:") and c.dump == "waves/fail.vcd"
    assert c.stead.actual == 0xFFFFF810 and c.stead.dump == "waves/fail.vcd" and c.also_fails == []
    assert not (case_dir / "tree").exists()
    assert not (case_dir / "logs" / "pass.log").exists() and not (case_dir / "waves" / "pass.vcd").exists()
    assert not list(case_dir.rglob("gold.yaml")) and not list(case_dir.rglob("bug.patch"))
    g = Gold.load(tmp_path / "gold" / "fake" / "fake-0001" / "gold.yaml")
    assert g.hit("rtl/alu.sv", 2) and not g.hit("rtl/alu.sv", 3) and not g.hit("dv/tb.sv", 2)


def test_bug_patch_must_stay_in_dut_and_shim_must_stay_out(src_repo, tmp_path, monkeypatch):
    with pytest.raises(BakeError, match="dut_paths"):
        bake(spec(tmp_path, bug_patch=BUG_PATCH.replace("rtl/alu.sv", "dv/tb.sv")))
    recipe = tmp_path / "repos" / "fake"
    recipe.mkdir(parents=True)
    (recipe / "repo.yaml").write_text(
        yaml.safe_dump({"commit": git(src_repo, "rev-parse", "HEAD").strip(), "dut_paths": ["rtl/**"]})
    )
    (recipe / "shim.patch").write_text(BUG_PATCH)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="shim patch touches dut_paths"):
        build_core("fake", src_repo)  # refused before any docker build


def test_clean_must_pass_and_buggy_must_fail_not_crash(tmp_path):
    with pytest.raises(BakeError, match="CRASH"):
        bake(spec(tmp_path, bug_patch=alu_patch("  // HANG")))
    with pytest.raises(BakeError, match="clean tree must PASS"):
        bake(spec(tmp_path, image=f"{FAKE}:broken"))


def test_stead_that_disagrees_with_dump_is_dropped_not_fatal(tmp_path):
    case_dir = bake(spec(tmp_path, bug_patch=alu_patch("  assign y = a ^ b; // BUG LIE")))
    c = Case.load(case_dir / "case.yaml")
    assert c.stead is None and "dump@t" in c.notes


def test_auto_test_is_found_by_the_suite_and_the_rest_are_recorded(tmp_path):
    case_dir = bake(spec(tmp_path, test="auto", bug_patch=alu_patch("  assign y = a; // BUG XORBUG")))
    c = Case.load(case_dir / "case.yaml")
    assert c.test == "sub_test" and c.also_fails == ["xor_test"]
    assert c.stead is not None
    with pytest.raises(BakeError, match="suite passed"):
        bake(spec(tmp_path, id="fake-0002", test="auto", bug_patch=alu_patch("  assign y = a; // harmless")))


def test_recipe_exit_codes_map_to_status_and_crash_is_never_fail(tmp_path):
    c = container.start(FAKE)
    try:
        container.put(c, "module alu; // SYNTAX_ERROR\nendmodule\n", "/work/tree/rtl/alu.sv")
        with pytest.raises(BuildError):
            build(c)
        for text, status in [("clean", RunStatus.PASS), ("BUG", RunStatus.FAIL), ("HANG", RunStatus.CRASH)]:
            container.put(c, f"module alu; // {text}\nendmodule\n", "/work/tree/rtl/alu.sv")
            build(c)
            res = run(c, "xor_test", tmp_path / f"out-{text}")
            assert res.status is status
        assert res.log.read_text().strip() == "timeout"  # a recipe's own crash log is kept
    finally:
        container.stop(c)


def test_materialized_tree_is_exactly_the_manifest_with_the_bug_applied(tmp_path):
    materialize(FAKE, BUG_PATCH, tmp_path / "tree")
    files = sorted(
        str(p.relative_to(tmp_path / "tree")) for p in (tmp_path / "tree").rglob("*") if p.is_file()
    )
    assert files == ["dv/tb.sv", "rtl/alu.sv"]  # no build/, no .git, no patch file
    assert "BUG" in (tmp_path / "tree" / "rtl" / "alu.sv").read_text()


def test_export_is_the_commit_with_submodules_and_nothing_untracked(src_repo, tmp_path):
    sub = tmp_path / "sub"
    (sub / "vendor").mkdir(parents=True)
    (sub / "vendor" / "lib.sv").write_text("module lib; endmodule\n")
    git(sub, "init", "-q")
    git(sub, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(sub, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "lib")
    git(src_repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "deps/sub")
    git(src_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "add sub")
    commit = git(src_repo, "rev-parse", "HEAD").strip()
    (src_repo / "rtl" / "alu.sv").write_text("dirty working tree\n")  # must not leak into the export
    (src_repo / "build").mkdir()
    (src_repo / "build" / "sim").write_text("untracked build product\n")

    out = tmp_path / "out"
    manifest = export(src_repo, commit, out)
    assert (out / "deps" / "sub" / "vendor" / "lib.sv").read_text() == "module lib; endmodule\n"
    assert "a ^ b" in (out / "rtl" / "alu.sv").read_text()
    assert not (out / "build").exists() and not list(out.rglob(".git"))
    assert manifest == sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert "deps/sub/vendor/lib.sv" in manifest and ".gitmodules" in manifest


def test_shim_applies_per_file_and_a_hunk_already_upstream_is_skipped(src_repo, tmp_path):
    tree = tmp_path / "tree"
    export(src_repo, "HEAD", tree)
    shim = tmp_path / "shim.patch"
    hunk = '@@ -1,2 +1,3 @@\n module tb;\n+  initial $display("STEAD");\n endmodule\n'
    shim.write_text("--- a/dv/tb.sv\n+++ b/dv/tb.sv\n" + hunk)
    assert apply_shim(tree, shim) == []  # applied
    assert apply_shim(tree, shim) == ["dv/tb.sv"]  # a second time: already there, skipped, not an error
    (tree / "dv" / "tb.sv").write_text("module tb;\n  something else entirely\nendmodule\n")
    with pytest.raises(ValueError, match="does not fit dv/tb.sv"):
        apply_shim(tree, shim)
