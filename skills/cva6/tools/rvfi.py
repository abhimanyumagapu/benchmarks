#!/usr/bin/env python3
"""cva6 tandem log reader (the RVFI lines the Spike tandem prints into the sim log).

    python tools/rvfi.py logs/fail.log --time <T> [--window N]   RVFI lines around a dump time (cycle = T/2)
    python tools/rvfi.py logs/fail.log --mismatch                 mismatch lines with [REF] and [CORE]
    python tools/rvfi.py logs/fail.log --reg 14                   every write to x14
    python tools/rvfi.py logs/fail.log --pc 0x<addr>              every retirement of a PC

Fields: ns | RVFI | hart | trap | pc | insn | priv | rd | rd_wdata | rs1 | rs1_rdata | rs2 | rs2_rdata | disasm
"""

import re
import sys
from pathlib import Path

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
path, opts = args[0], args[1:]
rows, mism = [], []
for line in Path(path).read_text(errors="replace").splitlines():
    if "Mismatch" in line or ("UVM_ERROR" in line and "RVFI" in line):
        mism.append(line)
    m = re.search(r"(\d+)\s*\|\s*RVFI\s*\|(.*)$", line)
    if m:
        f = [x.strip() for x in m.group(2).split("|")]
        rows.append((int(m.group(1)), f, m.group(0).strip()))
if not rows:
    sys.exit("no RVFI lines found")


def show(sel):
    for ns, _fields, text in sel:
        print(f"cycle={ns:<8} dump_t={2 * ns:<9} {text}")


if "--time" in opts:
    cyc = int(opts[opts.index("--time") + 1]) // 2
    n = int(opts[opts.index("--window") + 1]) if "--window" in opts else 8
    i = min(range(len(rows)), key=lambda i: abs(rows[i][0] - cyc))
    show(rows[max(0, i - n) : i + n + 1])
elif "--mismatch" in opts:
    print("\n".join(mism) or "no mismatch lines")
elif "--reg" in opts:
    r = "x" + opts[opts.index("--reg") + 1].lstrip("x")
    show([row for row in rows if len(row[1]) > 5 and row[1][5] == r])
elif "--pc" in opts:
    pc = f"{int(opts[opts.index('--pc') + 1], 16):x}"
    show([row for row in rows if len(row[1]) > 2 and row[1][2].lstrip("0") == pc.lstrip("0")])
else:
    show(rows)
