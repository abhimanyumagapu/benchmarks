#!/usr/bin/env python3
"""ibex RVFI trace reader.

    python tools/trace.py logs/trace.log --time <T> [--window N]   lines around a dump time (default N=12)
    python tools/trace.py logs/trace.log --reg x14                  every write to a register
    python tools/trace.py logs/trace.log --store 0x<addr>           every store to an address
    python tools/trace.py logs/trace.log --pc 0x<addr>              every retirement of a PC

Columns: Time  Cycle  PC  Insn  Decoded  Register and memory contents (x5=.. write, x5:.. read,
PA:0x.. store:0x.. / load:0x..). Time is the dump time of the retirement.
"""

import re
import sys
from pathlib import Path

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
path, opts = args[0], args[1:]
rows = []
for line in Path(path).read_text(errors="replace").splitlines():
    m = re.match(r"\s*(\d+)\s+(\d+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(.*)", line)
    if m:
        rows.append((int(m.group(1)), int(m.group(2)), int(m.group(3), 16), m.group(4), m.group(5).strip()))
if not rows:
    sys.exit("no trace lines found")


def show(sel):
    for t, cyc, pc, insn, rest in sel:
        print(f"t={t:<8} cyc={cyc:<7} pc={pc:08x} {insn}  {rest}")


if "--time" in opts:
    t = int(opts[opts.index("--time") + 1])
    n = int(opts[opts.index("--window") + 1]) if "--window" in opts else 12
    i = min(range(len(rows)), key=lambda i: abs(rows[i][0] - t))
    show(rows[max(0, i - n) : i + n + 1])
elif "--reg" in opts:
    r = opts[opts.index("--reg") + 1]
    show([row for row in rows if re.search(rf"\b{r}=0x", row[4])])
elif "--store" in opts:
    a = int(opts[opts.index("--store") + 1], 16)
    show([row for row in rows if re.search(rf"PA:0x0*{a:x}\b.*store:", row[4])])
elif "--pc" in opts:
    pc = int(opts[opts.index("--pc") + 1], 16)
    show([row for row in rows if row[2] == pc])
else:
    show(rows)
