import json

from stead.table import table


def test_table_aggregates_per_method(tmp_path):
    r = tmp_path / "results"
    for case, method, hit, file_, usd in [
        ("c1", "claude", True, True, 1.0),
        ("c2", "claude", False, True, 3.0),
        ("c1", "crux", True, True, 0.0),
    ]:
        d = r / case
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{method}.json").write_text(
            json.dumps(
                {
                    "method": method,
                    "case": case,
                    "k": 2,
                    "hit@2": hit,
                    "file@2": file_,
                    "patch": {"fixed": hit} if method == "claude" else None,
                    "cost": {"usd": usd, "wall_s": 60},
                }
            )
        )
    out = table(r)
    assert out.splitlines()[0] == "| method | cases | hit@k | file@k | patch fixed | mean usd | mean wall_s |"
    assert "| claude | 2 | 1/2 | 2/2 | 1/2 | 2.00 | 60 |" in out
    assert "| crux | 1 | 1/1 | 1/1 | 0/1 | 0.00 | 60 |" in out
