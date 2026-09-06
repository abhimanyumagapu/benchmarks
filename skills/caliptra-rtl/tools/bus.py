#!/usr/bin/env python3
"""caliptra AHB-lite bus log reader (logs/lsu_master_ahb_trace.log, written with +CLP_BUS_LOGS).

    python tools/bus.py <log> --time <T> [--window N]   transfers around a dump time (cycle = (T-50)/100)
    python tools/bus.py <log> --cycle <n> [--window N]  transfers around a bus-log cycle
    python tools/bus.py <log> --addr 0x<addr>           every access to an address (32-bit aligned)
    python tools/bus.py <log> --data 0x<value>          every transfer carrying a value (read or written)
    python tools/bus.py <log> --writes                  writes only
    python tools/bus.py <log> --reads                   reads only

Rows: cycle  dump_t  R|W  addr  data(32-bit lane)  hsize  hresp
"""

import re
import sys
from pathlib import Path

LSU = re.compile(
    r"^\s*(\d+) : 0x([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([01]) 0x([0-9a-f]{8})_([0-9a-f]{8}) "
    r"0x([0-9a-f]{8})_([0-9a-f]{8}) ([01]) ([01])"
)
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
path, opts = args[0], args[1:]
rows = []
for line in Path(path).read_text(errors="replace").splitlines():
    m = LSU.match(line)
    if not m:
        continue
    cyc, addr, hsize, htrans, hwrite = (
        int(m.group(1)),
        int(m.group(2), 16),
        m.group(3),
        m.group(4),
        m.group(5),
    )
    if htrans in ("0", "1"):  # IDLE / BUSY carry nothing
        continue
    lane = "hi" if addr & 4 else "lo"
    rdata = m.group(6) if lane == "hi" else m.group(7)
    wdata = m.group(8) if lane == "hi" else m.group(9)
    rows.append((cyc, addr, hwrite == "1", int(wdata if hwrite == "1" else rdata, 16), hsize, m.group(11)))
if not rows:
    sys.exit("no transfers found")


def show(sel):
    for cyc, addr, w, data, hsize, hresp in sel:
        print(
            f"cycle={cyc:<8} dump_t={100 * cyc + 50:<10} {'W' if w else 'R'} 0x{addr:08x} 0x{data:08x} hsize={hsize} hresp={hresp}"
        )


def around(cyc):
    i = min(range(len(rows)), key=lambda i: abs(rows[i][0] - cyc))
    n = int(opts[opts.index("--window") + 1]) if "--window" in opts else 12
    show(rows[max(0, i - n) : i + n + 1])


if "--time" in opts:
    around((int(opts[opts.index("--time") + 1]) - 50) // 100)
elif "--cycle" in opts:
    around(int(opts[opts.index("--cycle") + 1]))
elif "--addr" in opts:
    a = int(opts[opts.index("--addr") + 1], 16) & ~3
    show([r for r in rows if (r[1] & ~3) == a])
elif "--data" in opts:
    v = int(opts[opts.index("--data") + 1], 16)
    show([r for r in rows if r[3] == v])
elif "--writes" in opts:
    show([r for r in rows if r[2]])
elif "--reads" in opts:
    show([r for r in rows if not r[2]])
else:
    show(rows)
