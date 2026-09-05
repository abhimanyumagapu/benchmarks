import json
from pathlib import Path

from stead.solve import parse_submission, solve
from tests.conftest import FIX


def test_parse_submission_takes_the_json_block_out_of_prose():
    text = 'Some reasoning.\n```json\n{"k": 1, "lines": [{"file": "a.sv", "line": 3}]}\n```\n'
    assert parse_submission(text) == {"k": 1, "lines": [{"file": "a.sv", "line": 3}]}


def test_parse_submission_without_json_keeps_the_text():
    assert parse_submission("no idea") == {"text": "no idea"}


def test_solve_runs_claude_in_the_case_and_writes_the_submission(baked_case, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{FIX / 'fakeclaude'}:/usr/bin:/bin")
    log = tmp_path / "argv.log"
    monkeypatch.setenv("FAKECLAUDE_LOG", str(log))
    out = solve(baked_case, "claude", tmp_path / "results")
    assert out == tmp_path / "results" / "fake-0001" / "claude.json"
    sub = json.loads(out.read_text())
    assert sub["method"] == "claude" and sub["case"] == "fake-0001" and sub["k"] == 2
    assert sub["lines"][0] == {"file": "rtl/alu.sv", "line": 2, "confidence": 0.9}
    assert sub["cost"] == {"usd": 0.5, "wall_s": 30.0}
    argv = log.read_text().splitlines()
    assert Path(argv[0]) == baked_case  # ran inside the case folder
    assert "-p" in argv and "--output-format" in argv
    skill = (Path(__file__).parent.parent / "skills" / "rtl-debug" / "SKILL.md").read_text()
    assert skill.strip() in "\n".join(argv)  # the skill rides in the system prompt
