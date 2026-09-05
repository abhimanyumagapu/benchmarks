"""The results page (results/table.md): one leaderboard row per method with its resolved rate (cases
whose gold line is in the agent's top k, as a percentage), when it ran, what ran, totals; then per
method the per-case rows (one per trial) and the by-repo and by-class rows. A case counts once however
many trials it has; it is hit or fixed if any trial is (pass@k)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

COLS = "| cases | hit@k | file@k | patch fixed | mean usd | mean wall_s |"


def _hit(r: dict, prefix: str) -> bool:
    return any(v for k, v in r.items() if k.startswith(prefix))


def _fixed(r: dict) -> bool:
    return bool(r.get("patch") and r["patch"].get("fixed"))


def _cost(r: dict, key: str) -> float:
    return r.get("cost", {}).get(key, 0) or 0


def _dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def _cell(text: str | None, width: int = 80) -> str:
    return " ".join((text or "").split()).replace("|", "/")[:width]


def _by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key, "?"))].append(r)
    return groups


def _counts(rows: list[dict]) -> tuple[int, int, int, int]:
    """(cases, hit in any trial, file hit in any trial, fixed in any trial)."""
    cases = _by(rows, "case").values()
    any_ = lambda f: sum(any(f(r) for r in trials) for trials in cases)  # noqa: E731  three one-liners
    return len(cases), any_(lambda r: _hit(r, "hit@")), any_(lambda r: _hit(r, "file@")), any_(_fixed)


def _row(rows: list[dict]) -> str:
    n, hit, file_, fixed = _counts(rows)
    usd, wall = (sum(_cost(r, k) for r in rows) / n for k in ("usd", "wall_s"))
    return f"| {n} | {hit}/{n} | {file_}/{n} | {fixed}/{n} | {usd:.2f} | {wall:.0f} |"


def _section(rows: list[dict], by: str) -> list[str]:
    lines = [f"| {by} |" + COLS, "|---|" + "---|" * 6]
    return lines + [f"| {key} " + _row(group) for key, group in sorted(_by(rows, by).items())]


def _leaderboard(groups: dict[str, list[dict]]) -> list[str]:
    lines = [
        "| method | resolved | agent | effort | trials | ran | cases | hit@k | file@k | patch fixed | errors "
        "| flagged | total usd | total wall |",
        "|" + "---|" * 14,
    ]
    for method, rows in sorted(groups.items()):
        n, hit, file_, fixed = _counts(rows)
        ran = sorted(r["ran_at"][:16].replace("T", " ") for r in rows if r.get("ran_at"))
        when = f"{ran[0]} to {ran[-1]}" if ran else "?"
        agent = ", ".join(sorted({_cell(r.get("agent")) or "?" for r in rows}))
        effort = ", ".join(sorted({r.get("effort") or "default" for r in rows}))
        trials = max(r.get("trial", 1) for r in rows)
        errors, flagged = (sum(bool(r.get(k)) for r in rows) for k in ("error", "flags"))
        usd, wall = (sum(_cost(r, k) for r in rows) for k in ("usd", "wall_s"))
        lines.append(
            f"| {method} | {100 * hit / n:.0f}% | {agent} | {effort} | {trials} | {when} | {n} "
            f"| {hit}/{n} | {file_}/{n} | {fixed}/{n} | {errors} | {flagged} | {usd:.2f} | {_dur(wall)} |"
        )
    return lines


def _cases(rows: list[dict]) -> list[str]:
    lines = [
        "| case | trial | repo | class | hit rank | file rank | patch | usd | wall_s | flags | error |",
        "|" + "---|" * 11,
    ]
    for r in sorted(rows, key=lambda r: (r["case"], r.get("trial", 1))):
        patch = "fixed" if _fixed(r) else ("not fixed" if r.get("patch") else "no patch")
        lines.append(
            f"| {r['case']} | {r.get('trial', 1)} | {r.get('repo', '?')} | {r.get('class', '?')} "
            f"| {r.get('hit_rank') or '-'} | {r.get('file_rank') or '-'} | {patch} "
            f"| {_cost(r, 'usd'):.2f} | {_cost(r, 'wall_s'):.0f} | {len(r.get('flags') or [])} "
            f"| {_cell(r.get('error'))} |"
        )
    return lines


def table(results_root: Path) -> str:
    results = [json.loads(p.read_text()) for p in sorted(results_root.glob("*/*.score.json"))]
    groups = _by(results, "method")
    when = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    n = len({r["case"] for r in results})
    out = [
        "# STEAD-Bench results",
        "",
        f"Generated {when}. {n} cases, {len(groups)} methods.",
        "",
        *_leaderboard(groups),
    ]
    for method, rows in sorted(groups.items()):
        out += [
            "",
            f"## {method}",
            "",
            *_cases(rows),
            "",
            *_section(rows, "repo"),
            "",
            *_section(rows, "class"),
        ]
    return "\n".join(out)
