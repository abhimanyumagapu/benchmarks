"""The results page (results/index.html) and the leaderboard `stead table` prints.

One row per method with its resolved rate (cases whose gold line is in the agent's top k), what ran,
when, and the totals; then per method every trial of every case, and the same numbers cut by repo and
by bug class. A case counts once however many trials it has: it is hit or fixed if any trial is,
which is pass@k.

The page is one self-contained file -- no fonts, no CDN, no build step -- so `results/` can be served
as it stands. Tables are rendered here rather than by script, so the page still reads with JavaScript
off; the script only adds sorting and the filter box.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------- numbers


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


def _by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key, "?"))].append(r)
    return groups


def _counts(rows: list[dict]) -> tuple[int, int, int, int]:
    """(cases, hit in any trial, file hit in any trial, fixed in any trial).

    A case counts once however many trials it has, which is what makes these pass@k.
    """
    cases = list(_by(rows, "case").values())

    def in_any_trial(is_win) -> int:
        return sum(any(is_win(r) for r in trials) for trials in cases)

    return (
        len(cases),
        in_any_trial(lambda r: _hit(r, "hit@")),
        in_any_trial(lambda r: _hit(r, "file@")),
        in_any_trial(_fixed),
    )


def _fence(r: dict) -> str:
    """Why a run is not evidenced as confined, in words that stand on their own in a list."""
    if r.get("sandbox") == "none":
        return "no sandbox available on the machine that ran it"
    return "no sandbox recorded; this run predates the check"


def _who(r: dict) -> str:
    """A run, named the way a reader would look it up."""
    return f"{r.get('case', '?')} · trial {r.get('trial', 1)}"


def _one_line(text: str | None, width: int = 150) -> str:
    return " ".join((text or "").split())[:width]


def leaderboard(results: list[dict]) -> list[dict]:
    """One row per method, best resolved rate first, then cheapest."""
    rows = []
    for method, group in _by(results, "method").items():
        n, hit, file_, fixed = _counts(group)
        ran = sorted(r["ran_at"][:16].replace("T", " ") for r in group if r.get("ran_at"))
        rows.append(
            {
                "method": method,
                "resolved": 100 * hit / n if n else 0.0,
                "agent": ", ".join(sorted({r.get("agent") or "?" for r in group})),
                "effort": ", ".join(sorted({r.get("effort") or "default" for r in group})),
                "trials": max((r.get("trial", 1) for r in group), default=1),
                "ran": f"{ran[0]} to {ran[-1]}" if ran else "?",
                "cases": n,
                "hit": hit,
                "file": file_,
                "fixed": fixed,
                "errors": sum(bool(r.get("error")) for r in group),
                "flagged": sum(bool(r.get("flags")) for r in group),
                # what is behind each count, so the number can be opened rather than explained
                "detail": {
                    "errors": [
                        {"who": _who(r), "why": _one_line(r.get("error"))} for r in group if r.get("error")
                    ],
                    "flagged": [
                        {"who": _who(r), "why": _one_line("; ".join(r["flags"]))}
                        for r in group
                        if r.get("flags")
                    ],
                    "unconfined": [
                        {"who": _who(r), "why": _fence(r)}
                        for r in group
                        if r.get("sandbox") not in ("seatbelt", "userns")
                    ],
                },
                # Runs not evidenced as confined. "none" is a probe that found no fence; "" is a
                # run from before the harness recorded one. Both are counted, because absence of
                # evidence is not evidence of confinement, and a results page must not claim a
                # control it cannot show. Distinct from `flagged`, which is what the agent did.
                "unconfined": sum(r.get("sandbox") not in ("seatbelt", "userns") for r in group),
                "usd": sum(_cost(r, "usd") for r in group),
                "wall_s": sum(_cost(r, "wall_s") for r in group),
                "score_s": sum(r.get("score_wall_s") or 0 for r in group),
            }
        )
    return sorted(rows, key=lambda r: (-r["resolved"], r["usd"]))


def _breakdown(rows: list[dict], key: str) -> list[dict]:
    out = []
    for name, group in sorted(_by(rows, key).items()):
        n, hit, file_, fixed = _counts(group)
        out.append(
            {
                "name": name,
                "cases": n,
                "hit": hit,
                "file": file_,
                "fixed": fixed,
                "usd": sum(_cost(r, "usd") for r in group) / n if n else 0.0,
                "wall_s": sum(_cost(r, "wall_s") for r in group) / n if n else 0.0,
            }
        )
    return out


# ---------------------------------------------------------------- terminal


def summary(results: list[dict]) -> str:
    """The leaderboard as plain text, for the terminal `stead table` was run from."""
    if not results:
        return "no verdicts yet: run `stead score --all` first"
    head = f"{'method':<34}{'resolved':>9}{'hit@k':>8}{'file@k':>8}{'fixed':>8}{'usd':>9}{'wall':>9}"
    lines = [head, "-" * len(head)]
    for r in leaderboard(results):
        n = r["cases"]
        hit, file_, fixed = (f"{r[k]}/{n}" for k in ("hit", "file", "fixed"))
        lines.append(
            f"{r['method'][:33]:<34}{r['resolved']:>8.0f}%{hit:>8}{file_:>8}{fixed:>8}"
            f"{r['usd']:>9.2f}{_dur(r['wall_s']):>9}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- page

CSS = """
:root{color-scheme:light;
--bg:#fff;--ink:#0f1720;--body:#39444f;--dim:#6a7683;--faint:#9aa5b1;
--rule:#e3e8ed;--hair:#eef1f4;
--blue:#1d64c4;--blue-deep:#154a94;--wash:#f4f8fd;
--good:#0f6b47;--bad:#b03028}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--body);
font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:72px 32px 128px}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}

h1{margin:0;color:var(--ink);font-size:clamp(28px,4vw,38px);font-weight:650;
line-height:1.1;letter-spacing:-.03em}
.lede{max-width:64ch;margin:16px 0 0;font-size:16px;line-height:1.65}
.meta{margin:22px 0 0;color:var(--dim);font-size:13.5px}
.meta b{color:var(--blue);font-weight:650}
.count{padding:0;border:0;background:none;color:var(--bad);font:inherit;font-weight:600;
cursor:pointer;border-bottom:1px dotted currentColor}
.count:hover{color:var(--ink)}
.detail{margin:14px 0 0;padding:13px 0 0;border-top:1px solid var(--rule);font-size:13px}
.detail h4{margin:0 0 8px;color:var(--bad);font-size:11px;font-weight:600;
text-transform:uppercase;letter-spacing:.1em}
.detail ul{margin:0;padding:0;list-style:none}
.detail li{padding:4px 0;color:var(--body);white-space:normal;line-height:1.5}
.detail li b{color:var(--ink);font-weight:600}

h2{margin:0;color:var(--ink);font-size:20px;font-weight:600;letter-spacing:-.02em}
h3{margin:0 0 12px;color:var(--blue);font-size:11px;font-weight:600;
text-transform:uppercase;letter-spacing:.12em}
section{margin-top:76px}
.sub-note{margin:-6px 0 18px;color:var(--dim);font-size:13.5px}

.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{position:sticky;top:0;z-index:1;background:var(--bg);
padding:0 15px 10px;text-align:left;white-space:nowrap;
color:var(--faint);font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;
border-bottom:1.5px solid var(--ink)}
tbody td{padding:14px 15px;border-bottom:1px solid var(--hair);
white-space:nowrap;vertical-align:baseline}
/* every cell is padded on both sides; only the table's outer edges sit flush */
th:first-child,td:first-child{padding-left:0}
th:last-child,td:last-child{padding-right:0}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--wash)}
th.num,td.num{text-align:right}
th[data-sort]{cursor:pointer;user-select:none}
th[data-sort]:hover{color:var(--blue)}
th[data-sort]::after{content:"";padding-left:6px;opacity:0}
th.asc::after{content:"↑";opacity:1;color:var(--blue)}
th.desc::after{content:"↓";opacity:1;color:var(--blue)}

.rank{width:34px;color:var(--faint);font-size:12.5px}
.name{color:var(--ink);font-weight:600;font-size:14.5px;letter-spacing:-.01em}
.method{color:var(--blue);font-weight:650}
.agent{display:block;margin-top:3px;color:var(--faint);font-size:11.5px;font-weight:400;letter-spacing:0}
.pct{color:var(--blue);font-weight:650}
.good{color:var(--good)}.bad{color:var(--bad)}.dim{color:var(--dim)}.faint{color:var(--faint)}
.state.good{color:var(--good);font-weight:500}
.state.bad{color:var(--bad);font-weight:500}
.state.none{color:var(--faint)}

.filter{width:100%;max-width:300px;margin:0 0 20px;padding:7px 0;
border:0;border-bottom:1px solid var(--rule);background:none;color:var(--ink);font:inherit;font-size:14px}
.filter::placeholder{color:var(--faint)}
.filter:focus{outline:0;border-bottom-color:var(--blue)}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:52px}
.txt{white-space:normal;max-width:460px;color:var(--dim);font-size:12.5px;line-height:1.5}
footer{max-width:70ch;margin:112px 0 0;padding-top:24px;border-top:1px solid var(--rule);
color:var(--faint);font-size:12.5px;line-height:1.75}
@media(max-width:640px){.wrap{padding:48px 20px 80px}section{margin-top:56px}.grid{gap:36px}
tbody td{padding:12px 12px 12px 0}}
"""

JS = """
document.querySelectorAll('table').forEach(function(t){
  var body=t.tBodies[0]; if(!body) return;
  t.querySelectorAll('th[data-sort]').forEach(function(th){
    th.addEventListener('click',function(){
      var desc=!th.classList.contains('desc');
      t.querySelectorAll('th').forEach(function(o){o.classList.remove('asc','desc')});
      th.classList.add(desc?'desc':'asc');
      var idx=Array.prototype.indexOf.call(th.parentNode.children,th);
      var key=function(tr){var c=tr.children[idx];
        var v=c.dataset.v!==undefined?c.dataset.v:c.textContent.trim();
        var n=parseFloat(v); return isNaN(n)?v.toLowerCase():n;};
      Array.from(body.rows).sort(function(a,b){
        var x=key(a),y=key(b); if(x<y)return desc?1:-1; if(x>y)return desc?-1:1; return 0;
      }).forEach(function(tr){body.appendChild(tr)});
    });
  });
});
document.addEventListener('click',function(e){
  var b=e.target.closest('.count');
  if(!b) return;
  var open=document.querySelector('.detail'), same=open&&open.dataset.for===b.dataset.title;
  if(open) open.remove();
  if(same) return;
  var d=document.createElement('div');
  d.className='detail'; d.dataset.for=b.dataset.title;
  var h=document.createElement('h4'); h.textContent=b.dataset.title;
  var ul=document.createElement('ul');
  JSON.parse(b.dataset.items||'[]').forEach(function(it){
    var li=document.createElement('li'), who=document.createElement('b');
    who.textContent=it.who;
    li.appendChild(who);
    li.appendChild(document.createTextNode(it.why ? ' \u2014 ' + it.why : ''));
    ul.appendChild(li);
  });
  d.appendChild(h); d.appendChild(ul);
  b.closest('.scroll').after(d);
});
var box=document.getElementById('filter');
if(box) box.addEventListener('input',function(){
  var q=box.value.toLowerCase();
  document.querySelectorAll('table.rows tbody tr').forEach(function(tr){
    tr.style.display=tr.textContent.toLowerCase().indexOf(q)>-1?'':'none';
  });
});
"""


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _cell(text: str | None, width: int = 140) -> str:
    return _e(" ".join((text or "").split())[:width])


def _th(cols: list[tuple[str, bool]]) -> str:
    """Header cells; the flag marks a numeric column, which is right-aligned."""
    return "".join(f'<th data-sort class="{"num" if num else ""}">{_e(name)}</th>' for name, num in cols)


def _table(cols: list[tuple[str, bool]], body: str, klass: str = "") -> str:
    return (
        f'<div class="scroll"><table class="{klass}"><thead><tr>{_th(cols)}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _alarm(n: int, title: str = "", items: list[dict] | None = None) -> str:
    """A count that is only ever bad news: errors, flagged runs, unconfined runs.

    A non-zero count carries what is behind it, so a reader opens the number instead of going to the
    json to find out which run it means. Zero is not a button: there is nothing to open.
    """
    if not n:
        return '<td class="num faint" data-v="0">0</td>'
    # JSON, not a delimiter. A separator inside the payload is how the last version broke, and any
    # escape written here must survive being a Python string before it is ever JavaScript.
    detail = _e(json.dumps(items or []))
    return (
        f'<td class="num" data-v="{n}">'
        f'<button class="count" data-title="{_e(title)}" data-items="{detail}">{n}</button></td>'
    )


def _rank(v) -> str:
    """A rank cell. A miss shows as a dash and sorts last, not first."""
    if not v:
        return '<td class="num faint" data-v="9999">&mdash;</td>'
    return f'<td class="num" data-v="{v}">{v}</td>'


def _ratio(part: int, whole: int) -> str:
    klass = "good" if whole and part == whole else ("faint" if not part else "")
    return f'<td class="num {klass}" data-v="{part}">{part}/{whole}</td>'


def _agent(r: dict) -> str:
    """What actually ran, under the method name, when it is not simply the method again.

    For an API model the two are the same string and a column of its own would be a column of
    duplicates. For Claude Code it is the CLI version, which a published result needs.
    """
    agent = _cell(r.get("agent"), 40)
    base = r["method"].partition("+")[0]  # effort rides on the method, not the agent
    return f'<span class="agent">{agent}</span>' if agent and agent != base else ""


def _leaderboard_html(results: list[dict]) -> str:
    cols = [
        ("", False),
        ("method", False),
        ("resolved", True),
        ("hit@k", True),
        ("file@k", True),
        ("patch fixed", True),
        ("cases", True),
        ("trials", True),
        ("usd", True),
        ("solve", True),
        ("errors", True),
        ("flagged", True),
        ("unconfined", True),
    ]
    body = []
    for i, r in enumerate(leaderboard(results), start=1):
        pct = r["resolved"]
        body.append(
            f'<tr><td class="rank">{i}</td>'
            f'<td class="method">{_e(r["method"])}{_agent(r)}</td>'
            f'<td class="num" data-v="{pct:.1f}"><span class="pct">{pct:.0f}%</span></td>'
            f"{_ratio(r['hit'], r['cases'])}{_ratio(r['file'], r['cases'])}"
            f"{_ratio(r['fixed'], r['cases'])}"
            f'<td class="num">{r["cases"]}</td><td class="num">{r["trials"]}</td>'
            f'<td class="num">${r["usd"]:.2f}</td>'
            f'<td class="num" data-v="{r["wall_s"]:.0f}">{_dur(r["wall_s"])}</td>'
            + "".join(
                _alarm(r[k], f"{r['method']} — {k}", r["detail"][k])
                for k in ("errors", "flagged", "unconfined")
            )
            + "</tr>"
        )
    return _table(cols, "".join(body))


def _state(r: dict) -> str:
    if not r.get("patch"):
        return '<span class="state none">none</span>'
    if _fixed(r):
        return '<span class="state good">fixed</span>'
    return '<span class="state bad">not fixed</span>'


def _flag_items(r: dict) -> list[dict]:
    """A run's audit hits, split into the turn it happened on and what matched."""
    items = []
    for flag in r.get("flags") or []:
        turn, _, what = flag.partition(": ")
        items.append({"who": turn, "why": what or turn})
    return items


def _error(r: dict) -> str:
    """The error, linked to the submission holding it in full.

    The verdict truncates the message at 1500 characters, and the submission beside it also carries
    the agent's raw final message -- which is what a reader needs in order to see why a run failed.
    """
    text = _cell(r.get("error"), 200)
    if not text:
        return '<span class="faint">&mdash;</span>'
    if r.get("submission"):
        return f'<a class="bad" href="{_e(r["submission"])}">{text}</a>'
    return f'<span class="bad">{text}</span>'


def _cases_html(rows: list[dict]) -> str:
    """Every trial of every case. Timings are deliberately absent: they say what the harness cost,
    not how well the method did, and both are in the json for anyone measuring the harness."""
    cols = [
        ("case", False),
        ("trial", True),
        ("repo", False),
        ("class", False),
        ("hit rank", True),
        ("file rank", True),
        ("patch", False),
        ("usd", True),
        ("flags", True),
        ("transcript", False),
        ("error", False),
    ]
    body = []
    for r in sorted(rows, key=lambda r: (r["case"], r.get("trial", 1))):
        link = r.get("trajectory")
        run = f'<a href="{_e(link)}">open</a>' if link else '<span class="faint">&mdash;</span>'
        body.append(
            f'<tr><td class="name">{_e(r["case"])}</td><td class="num">{r.get("trial", 1)}</td>'
            f'<td class="dim">{_e(r.get("repo", "?"))}</td>'
            f'<td class="dim">{_e(r.get("class", "?"))}</td>'
            + "".join(_rank(r.get(k)) for k in ("hit_rank", "file_rank"))
            + f"<td>{_state(r)}</td>"
            f'<td class="num">${_cost(r, "usd"):.2f}</td>'
            + _alarm(len(r.get("flags") or []), f"{_who(r)} · reached outside", _flag_items(r))
            + f'<td>{run}</td><td class="txt">{_error(r)}</td></tr>'
        )
    return _table(cols, "".join(body), klass="rows")


def _breakdown_html(rows: list[dict], key: str) -> str:
    cols = [
        (key, False),
        ("cases", True),
        ("hit@k", True),
        ("file@k", True),
        ("patch fixed", True),
        ("mean usd", True),
        ("mean solve", True),
    ]
    body = "".join(
        f'<tr><td class="name">{_e(b["name"])}</td><td class="num">{b["cases"]}</td>'
        f"{_ratio(b['hit'], b['cases'])}{_ratio(b['file'], b['cases'])}{_ratio(b['fixed'], b['cases'])}"
        f'<td class="num">${b["usd"]:.2f}</td>'
        f'<td class="num" data-v="{b["wall_s"]:.0f}">{_dur(b["wall_s"])}</td></tr>'
        for b in _breakdown(rows, key)
    )
    return _table(cols, body)


def page(results: list[dict]) -> str:
    """The whole page, as one string. `results` is every verdict on disk."""
    when = datetime.now().astimezone().strftime("%d %B %Y")
    cases = len({r["case"] for r in results})
    repos = len({r.get("repo") for r in results})
    methods = _by(results, "method")

    out = [
        "<div class='wrap'>",
        "<h1>STEAD-Bench</h1>",
        "<p class='lede'>Functional RTL debug on real open-source cores, scored by simulation. Each "
        "case is one bug on a production core: the failing test, its logs and waveforms, and the "
        "signal that first went wrong. A tool returns ranked candidate lines and a patch; both are "
        "scored by rebuilding the tree and re-running the test in a container.</p>",
        f"<p class='meta'><b>{cases}</b> case{'s' * (cases != 1)} across <b>{repos}</b> "
        f"core{'s' * (repos != 1)} &middot; <b>{len(methods)}</b> "
        f"method{'s' * (len(methods) != 1)} &middot; updated {_e(when)}</p>",
    ]
    if not results:
        return _shell("<div class='wrap'><h1>STEAD-Bench</h1><p class='lede'>No verdicts yet.</p></div>")

    out += ["<section><h3>Leaderboard</h3>", _leaderboard_html(results), "</section>"]
    for method, rows in sorted(methods.items()):
        out += [
            f"<section><h2>{_e(method)}</h2>",
            "<p class='sub-note'>Every trial of every case. A case counts once: it is resolved if "
            "any trial finds the line.</p>",
            "<input id='filter' class='filter' placeholder='Filter cases' autocomplete='off'>",
            _cases_html(rows),
            "<div class='grid' style='margin-top:52px'>",
            f"<div><h3>By core</h3>{_breakdown_html(rows, 'repo')}</div>",
            f"<div><h3>By bug class</h3>{_breakdown_html(rows, 'class')}</div>",
            "</div></section>",
        ]
    out.append(
        "<footer>Ranked lines are scored hit@k against a hidden gold window. A patch is never "
        "compared with the reference fix: it must touch only DUT paths, apply over the bug, build, "
        "and take the named test and every <code>also_fails</code> test from FAIL to PASS in a fresh "
        "container. Generated by <code>stead table</code>.</footer></div>"
    )
    return _shell("".join(out))


def _shell(body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>STEAD-Bench results</title>"
        f"<style>{CSS}</style></head><body>{body}<script>{JS}</script></body></html>"
    )
