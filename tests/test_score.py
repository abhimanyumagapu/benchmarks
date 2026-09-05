import json

from stead.bake import BakeSpec, bake
from stead.gold import Gold
from stead.recipe import ScriptRecipe
from stead.score import Submission, score_lines, score_patch, score_submission
from tests.conftest import FIX

G = Gold(file="rtl/ibex_alu.sv", start=384, end=388, klass="logic")


def ranked(*pairs):
    return [{"file": f, "line": n} for f, n in pairs]


def test_hit_at_k_counts_only_first_k():
    lines = ranked(("rtl/ibex_decoder.sv", 10), ("rtl/ibex_alu.sv", 386))
    assert score_lines(G, lines, k=1) == {"hit@1": False, "file@1": False, "hit_rank": 2, "file_rank": 2}
    assert score_lines(G, lines, k=2) == {"hit@2": True, "file@2": True, "hit_rank": 2, "file_rank": 2}


def test_file_hit_without_line_hit():
    lines = ranked(("rtl/ibex_alu.sv", 12))
    r = score_lines(G, lines, k=1)
    assert r["file@1"] and not r["hit@1"] and r["hit_rank"] is None and r["file_rank"] == 1


def test_submission_json_roundtrip(tmp_path):
    p = tmp_path / "sub.json"
    p.write_text(
        json.dumps(
            {
                "method": "claude",
                "case": "fake-0001",
                "k": 2,
                "lines": [{"file": "rtl/alu.sv", "line": 2, "confidence": 0.9}],
                "patch": None,
                "text": "bit 4 flipped",
                "cost": {"usd": 0.5, "wall_s": 30},
            }
        )
    )
    s = Submission.load(p)
    assert s.method == "claude" and s.k == 2 and s.lines[0]["line"] == 2 and s.cost["usd"] == 0.5


def _baked(src_repo, bug_patch, tmp_path):
    r = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
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
    return bake(spec, r), r


def test_patch_that_fixes_goes_fail_to_pass(src_repo, bug_patch, fix_patch, tmp_path):
    case_dir, r = _baked(src_repo, bug_patch, tmp_path)
    res = score_patch(case_dir, r, fix_patch)
    assert res == {"applied": True, "dut_only": True, "fixed": True, "status": "PASS"}
    # the case tree itself is untouched
    assert "BUG" in (case_dir / "tree" / "rtl" / "alu.sv").read_text()


def test_patch_touching_checker_is_rejected(src_repo, bug_patch, tmp_path):
    case_dir, r = _baked(src_repo, bug_patch, tmp_path)
    cheat = "--- a/dv/tb.sv\n+++ b/dv/tb.sv\n@@ -1,2 +1,2 @@\n module tb;\n-endmodule\n+endmodule // x\n"
    res = score_patch(case_dir, r, cheat)
    assert res["dut_only"] is False and res["fixed"] is False


def test_score_submission_combines(src_repo, bug_patch, tmp_path):
    case_dir, r = _baked(src_repo, bug_patch, tmp_path)
    sub = Submission(
        method="m",
        case="fake-0001",
        k=1,
        lines=[{"file": "rtl/alu.sv", "line": 2}],
        patch=None,
        text="flipped bit",
        cost={"usd": 0.1, "wall_s": 5},
    )
    res = score_submission(case_dir, tmp_path / "gold" / "fake" / "fake-0001", sub, r)
    assert res["hit@1"] and res["file@1"] and res["patch"] is None and res["text"] == "flipped bit"
    assert res["method"] == "m" and res["case"] == "fake-0001" and res["cost"]["usd"] == 0.1
