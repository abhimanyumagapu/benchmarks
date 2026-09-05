import pytest

from stead.recipe import BuildError, RunStatus, ScriptRecipe
from tests.conftest import FIX


def tree_with(tmp_path, alu_text):
    t = tmp_path / "tree"
    (t / "rtl").mkdir(parents=True)
    (t / "rtl" / "alu.sv").write_text(alu_text)
    return t


def test_clean_tree_passes(tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    t = tree_with(tmp_path, "clean")
    r.build(t)
    res = r.run(t, "xor_test", tmp_path / "out")
    assert res.status is RunStatus.PASS
    assert res.log.read_text().startswith("PASS")
    assert res.dump is not None and res.dump.exists()
    assert res.stead is None


def test_buggy_tree_fails_with_stead(tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    t = tree_with(tmp_path, "BUG")
    r.build(t)
    res = r.run(t, "xor_test", tmp_path / "out")
    assert res.status is RunStatus.FAIL
    assert res.stead is not None and res.stead.time == 100
    assert res.dump == tmp_path / "out" / "dump.vcd"


def test_build_error_status(tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    t = tree_with(tmp_path, "SYNTAX_ERROR")

    with pytest.raises(BuildError):
        r.build(t)


def test_crash_status_is_not_fail(tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
    t = tree_with(tmp_path, "HANG")
    r.build(t)
    assert r.run(t, "xor_test", tmp_path / "out").status is RunStatus.CRASH
