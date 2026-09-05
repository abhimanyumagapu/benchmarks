"""Ranked lines score against the gold window; a patch scores only by going FAIL -> PASS
without touching the checker; the LLM's answer is parsed, not trusted."""

import json
from pathlib import Path

from stead.gold import Gold
from stead.recipe import ScriptRecipe
from stead.score import Submission, score_lines, score_patch, score_submission
from stead.solve import parse_submission, solve
from tests.conftest import FIX

RECIPE = ScriptRecipe("fake", FIX / "fakerepo" / "run.sh")
G = Gold(file="rtl/ibex_alu.sv", start=384, end=388, klass="logic")


def test_hit_and_file_at_k_count_only_the_first_k():
    lines = [{"file": "rtl/ibex_decoder.sv", "line": 10}, {"file": "rtl/ibex_alu.sv", "line": 386}]
    assert score_lines(G, lines, k=1) == {"hit@1": False, "file@1": False, "hit_rank": 2, "file_rank": 2}
    assert score_lines(G, lines, k=2) == {"hit@2": True, "file@2": True, "hit_rank": 2, "file_rank": 2}
    r = score_lines(G, [{"file": "rtl/ibex_alu.sv", "line": 12}], k=1)
    assert r["file@1"] and not r["hit@1"]


def test_patch_scores_by_rerun_and_never_touches_the_case_tree(baked_case, fix_patch):
    res = score_patch(baked_case, RECIPE, fix_patch)
    assert res == {"applied": True, "dut_only": True, "fixed": True, "status": "PASS"}
    assert "BUG" in (baked_case / "tree" / "rtl" / "alu.sv").read_text()
    cheat = "--- a/dv/tb.sv\n+++ b/dv/tb.sv\n@@ -1,2 +1,2 @@\n module tb;\n-endmodule\n+endmodule // x\n"
    assert score_patch(baked_case, RECIPE, cheat)["dut_only"] is False


def test_score_submission_combines_lines_patch_text_cost(baked_case, tmp_path):
    sub = Submission(
        method="m",
        case="fake-0001",
        k=1,
        lines=[{"file": "rtl/alu.sv", "line": 2}],
        patch=None,
        text="flipped bit",
        cost={"usd": 0.1, "wall_s": 5},
    )
    res = score_submission(baked_case, tmp_path / "gold" / "fake" / "fake-0001", sub, RECIPE)
    assert (
        res["hit@1"] and res["patch"] is None and res["text"] == "flipped bit" and res["cost"]["usd"] == 0.1
    )


def test_llm_answer_is_the_json_block_and_prose_alone_is_kept_as_text():
    assert parse_submission('Reasoning.\n```json\n{"k": 1, "lines": []}\n```\n') == {"k": 1, "lines": []}
    assert parse_submission("no idea") == {"text": "no idea"}


def test_solve_runs_the_agent_inside_the_case_with_the_skill(baked_case, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{FIX / 'fakeclaude'}:/usr/bin:/bin")
    monkeypatch.setenv("FAKECLAUDE_LOG", str(tmp_path / "argv.log"))
    sub = json.loads(solve(baked_case, "claude", tmp_path / "results").read_text())
    assert sub["lines"][0]["line"] == 2 and sub["cost"] == {"usd": 0.5, "wall_s": 30.0}
    argv = (tmp_path / "argv.log").read_text()
    assert argv.startswith(str(baked_case))
    assert (Path(__file__).parent.parent / "skills" / "rtl-debug" / "SKILL.md").read_text().strip() in argv
