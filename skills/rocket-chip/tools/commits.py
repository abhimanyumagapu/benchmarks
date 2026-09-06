#!/usr/bin/env python3
"""rocket-chip commit log reader (the +verbose log with the shim's STEAD t= clock marks).

    python tools/commits.py logs/run.log --time <T> [--window N]   commits around a dump time (T = 2*clock)
    python tools/commits.py logs/run.log --reg 14                   every write to x14
    python tools/commits.py logs/run.log --pc 0x<addr>              every commit of a PC
    python tools/commits.py logs/run.log --clock <c> [--window N]   commits around a clock count

Each row: clock (from STEAD t=), then the commit line: C0: <mcycle> [1] pc=[..] W[r rd=v][wen]
R[r rs1=v] R[r rs2=v] inst=[word] DASM(word)
"""

import re
import sys
from pathlib import Path

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
path, opts = args[0], args[1:]
rows, clock = [], None
for line in Path(path).read_text(errors="replace").splitlines():
    m = re.match(r"STEAD t=(\d+)", line)
    if m:
        clock = int(m.group(1))
        continue
    if line.startswith("C0:"):
        pc = re.search(r"pc=\[([0-9a-f]+)\]", line)
        rows.append((clock, int(pc.group(1), 16) if pc else -1, line))
if not rows:
    sys.exit("no commit lines found")


def show(sel):
    for c, _pc, text in sel:
        print(f"clock={c:<8} dump_t={2 * c if c is not None else '?':<9} {text}")


def around(target):
    i = min(range(len(rows)), key=lambda i: abs((rows[i][0] or 0) - target))
    n = int(opts[opts.index("--window") + 1]) if "--window" in opts else 8
    show(rows[max(0, i - n) : i + n + 1])


if "--time" in opts:
    around(int(opts[opts.index("--time") + 1]) // 2)
elif "--clock" in opts:
    around(int(opts[opts.index("--clock") + 1]))
elif "--reg" in opts:
    r = int(opts[opts.index("--reg") + 1].lstrip("x"))
    show([row for row in rows if re.search(rf"W\[r\s*{r}=[0-9a-f]+\]\[1\]", row[2])])
elif "--pc" in opts:
    pc = int(opts[opts.index("--pc") + 1], 16)
    show([row for row in rows if row[1] == pc])
else:
    show(rows)
