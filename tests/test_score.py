"""Ranked lines score against the gold window; a patch scores only by going FAIL -> PASS on the
named test and every test in also_fails, without touching the checker; the LLM's answer is
parsed, not trusted."""

import json
import shutil
from pathlib import Path

import pytest

from stead.bake import bake
from stead.gold import Gold
from stead.score import Submission, score_lines, score_patch, score_submission
from stead.solve import parse_submission, solve
from tests.conftest import FIX, FIX_PATCH, alu_patch, spec

G = Gold(file="rtl/ibex_alu.sv", start=384, end=388, klass="logic")
NO_NET = 101 if shutil.which("unshare") else 111  # unreachable with the namespace, refused without it


def gold_dir(case_dir: Path) -> Path:
    return case_dir.parent.parent.parent / "gold" / "fake" / case_dir.name


def test_hit_and_file_at_k_count_only_the_first_k():
    lines = [{"file": "rtl/ibex_decoder.sv", "line": 10}, {"file": "rtl/ibex_alu.sv", "line": 386}]
    assert score_lines(G, lines, k=1) == {"hit@1": False, "file@1": False, "hit_rank": 2, "file_rank": 2}
    assert score_lines(G, lines, k=2) == {"hit@2": True, "file@2": True, "hit_rank": 2, "file_rank": 2}
    r = score_lines(G, [{"file": "rtl/ibex_alu.sv", "line": 12}], k=1)
    assert r["file@1"] and not r["hit@1"]


def test_patch_scores_by_rerun_and_never_touches_the_case(baked_case):
    res = score_patch(baked_case, gold_dir(baked_case), FIX_PATCH)
    assert res == {"applied": True, "dut_only": True, "fixed": True, "status": {"xor_test": "PASS"}}
    assert not (baked_case / "tree").exists()  # the case never grows a tree
    cheat = "--- a/dv/tb.sv\n+++ b/dv/tb.sv\n@@ -1,2 +1,2 @@\n module tb;\n-endmodule\n+endmodule // x\n"
    assert score_patch(baked_case, gold_dir(baked_case), cheat)["dut_only"] is False


def test_patch_must_also_green_every_test_in_also_fails(tmp_path):
    case_dir = bake(spec(tmp_path, test="auto", bug_patch=alu_patch("  assign y = a; // BUG XORBUG")))
    half = alu_patch("  assign y = a; // XORBUG").replace(
        "-  assign y = a ^ b;", "-  assign y = a; // BUG XORBUG"
    )
    res = score_patch(case_dir, gold_dir(case_dir), half)
    assert res["fixed"] is False and res["status"] == {"sub_test": "PASS", "xor_test": "FAIL"}


def test_score_submission_combines_lines_patch_text_cost_and_gold_class(baked_case):
    sub = Submission(
        method="m",
        case="fake-0001",
        k=1,
        lines=[{"file": "rtl/alu.sv", "line": 2}],
        patch=None,
        text="flipped bit",
        cost={"usd": 0.1, "wall_s": 5},
    )
    res = score_submission(baked_case, gold_dir(baked_case), sub)
    assert (
        res["hit@1"] and res["patch"] is None and res["text"] == "flipped bit" and res["cost"]["usd"] == 0.1
    )
    assert res["repo"] == "fake" and res["class"] == "logic" and res["lines"] == sub.lines


def test_llm_answer_is_the_json_block_and_prose_alone_is_kept_as_text(tmp_path):
    assert parse_submission('Reasoning.\n```json\n{"k": 1, "lines": []}\n```\n') == {"k": 1, "lines": []}
    assert parse_submission("no idea") == {"text": "no idea"}
    braces = (
        'The concat {carry, sum} is wrong.\n```json\n{"k": 1, "lines": [{"file": "a.sv", "line": 5}]}\n```'
    )
    assert parse_submission(braces) == {"k": 1, "lines": [{"file": "a.sv", "line": 5}]}
    # parsed, not trusted: malformed ranked lines are dropped and k is coerced, so scoring never crashes
    p = tmp_path / "sub.json"
    p.write_text(
        json.dumps(
            {
                "method": "m",
                "case": "c",
                "k": "3",
                "lines": [
                    {"path": "a.sv", "line": 5},
                    {"file": "a.sv", "line": "5-7"},
                    "a.sv:5",
                    {"file": "b.sv", "line": "6"},
                ],
                "extra": "ignored",
            }
        )
    )
    sub = Submission.load(p)
    assert sub.k == 3 and sub.lines == [{"file": "b.sv", "line": 6}]
    assert score_lines(G, sub.lines, sub.k)["hit_rank"] is None


def test_solve_gives_the_agent_a_writable_tree_and_takes_the_diff_as_patch(baked_case, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{FIX / 'fakeclaude'}:/usr/bin:/bin")
    monkeypatch.setenv("FAKECLAUDE_LOG", str(tmp_path / "argv.log"))
    path = solve(baked_case, gold_dir(baked_case), "claude+high", tmp_path / "results", trial=2)
    assert path.name == "claude+high.t2.json"
    sub = json.loads(path.read_text())
    assert sub["lines"][0]["line"] == 2 and sub["cost"]["usd"] == 0.5 and sub["cost"]["wall_s"] > 0
    assert sub["agent"] == "claude 9.9.9 (fake)" and sub["ran_at"][:2] == "20" and sub["error"] is None
    assert sub["effort"] == "high" and sub["trial"] == 2 and sub["attempts"] == 1 and sub["flags"] == []
    assert "-  assign y = (a ^ b) ^ 32'h10; // BUG" in sub["patch"] and "+++ b/rtl/alu.sv" in sub["patch"]
    assert "+++ b/rtl/new.sv" in sub["patch"]  # a file the agent created is part of the fix
    assert not (baked_case / "tree").exists()  # the case itself is untouched
    argv = (tmp_path / "argv.log").read_text()
    assert not argv.startswith(str(baked_case))  # ran in the copy, not the case
    assert "--effort\nhigh\n" in argv and "stream-json" in argv
    assert f"net: [Errno {NO_NET}]" in argv and "docker: open" not in argv  # no network, no docker
    assert "sim: PASS xor_test" in argv and sub["cost"]["sims"] == 1  # it ran its fix in the core's simulator
    assert (Path(__file__).parent.parent / "skills" / "rtl-debug" / "SKILL.md").read_text().strip() in argv
    assert score_patch(baked_case, gold_dir(baked_case), sub["patch"])["fixed"] is True


def test_solve_runs_any_api_model_in_our_loop_with_tools_sandboxed_to_the_copy(
    baked_case, tmp_path, monkeypatch
):
    from tests.fixtures import fakellm

    monkeypatch.setenv("OPENAI_API_BASE", fakellm.serve())
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("FAKELLM_LOG", str(tmp_path / "system.md"))
    path = solve(baked_case, gold_dir(baked_case), "openai/gpt-4o+low", tmp_path / "results")
    assert path.name == "openai-gpt-4o+low.json"
    sub = json.loads(path.read_text())
    assert sub["lines"][0]["line"] == 2 and sub["agent"] == "openai/gpt-4o" and sub["error"] is None
    assert sub["cost"]["usd"] > 0 and sub["cost"]["turns"] == 5 and sub["cost"]["tokens_in"] == 5000
    assert sub["cost"]["sims"] == 1
    assert sub["effort"] == "low"
    assert sub["flags"] == ["turn 1: docker", "turn 1: https://github.com/syntacore/scr1", "turn 1: socket"]
    transcript = [json.loads(ln) for ln in path.with_suffix(".trajectory.jsonl").read_text().splitlines()]
    assert [m["role"] for m in transcript] == ["user", *["assistant", "tool"] * 4, "assistant"]
    assert transcript[8]["content"].startswith("PASS xor_test")  # the sim tool's verdict on the fixed tree
    probe = transcript[2]["content"]
    assert f"net: [Errno {NO_NET}]" in probe and "docker: open" not in probe  # no network, no docker
    assert "-  assign y = (a ^ b) ^ 32'h10; // BUG" in sub["patch"]
    assert not (baked_case / "tree").exists() and "FAIL" in (baked_case / "logs" / "fail.log").read_text()
    system = (tmp_path / "system.md").read_text()
    root = Path(__file__).parent.parent
    assert system.startswith((root / "prompts" / "system.md").read_text())
    assert (root / "skills" / "rtl-debug" / "SKILL.md").read_text() in system
    assert score_patch(baked_case, gold_dir(baked_case), sub["patch"])["fixed"] is True


def test_an_agent_crash_is_a_recorded_miss_not_a_lost_case(baked_case, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="no-such-agent"):  # a typo is refused before anything runs
        solve(baked_case, gold_dir(baked_case), "no-such-agent", tmp_path / "results")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # no `claude` here: the agent crashes at once
    sub = Submission.load(solve(baked_case, gold_dir(baked_case), "claude", tmp_path / "results"))
    assert sub.error.startswith("FileNotFoundError") and sub.lines == [] and sub.patch is None
    assert sub.attempts == 3  # retried twice, then recorded
    res = score_submission(baked_case, gold_dir(baked_case), sub)
    assert res["hit@3"] is False and res["error"] == sub.error
