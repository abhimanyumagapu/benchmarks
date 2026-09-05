"""One Markdown row per method over everything in results/."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def _row(method: str, rows: list[dict]) -> str:
    n = len(rows)
    hit = sum(any(v for k, v in r.items() if k.startswith("hit@")) for r in rows)
    file_ = sum(any(v for k, v in r.items() if k.startswith("file@")) for r in rows)
    fixed = sum(bool(r.get("patch") and r["patch"].get("fixed")) for r in rows)
    usd = sum(r.get("cost", {}).get("usd", 0) for r in rows) / n
    wall = sum(r.get("cost", {}).get("wall_s", 0) for r in rows) / n
    return f"| {method} | {n} | {hit}/{n} | {file_}/{n} | {fixed}/{n} | {usd:.2f} | {wall:.0f} |"


def table(results_root: Path) -> str:
    by_method: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(results_root.glob("*/*.json")):
        r = json.loads(p.read_text())
        by_method[r["method"]].append(r)
    head = [
        "| method | cases | hit@k | file@k | patch fixed | mean usd | mean wall_s |",
        "|---|---|---|---|---|---|---|",
    ]
    return "\n".join(head + [_row(m, rows) for m, rows in sorted(by_method.items())])
