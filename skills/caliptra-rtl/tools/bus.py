#!/usr/bin/env python3
"""caliptra AHB-lite bus log reader (logs/lsu_master_ahb_trace.log, written with +CLP_BUS_LOGS).

    python tools/bus.py <log> --time <T> [--window N]   transfers around a dump time (cycle = (T-50)/100)
    python tools/bus.py <log> --cycle <n> [--window N]  transfers around a bus-log cycle
    python tools/bus.py <log> --addr 0x<addr>           every access to an address (32-bit aligned)
    python tools/bus.py <log> --data 0x<value>          every transfer carrying a value (read or written)
    python tools/bus.py <log> --writes                  writes only
    python tools/bus.py <log> --reads                   reads only

AHB-lite is pipelined: the address is on the bus one cycle, its data the next (with hready=1). A row
here is one transfer, stamped with the cycle its DATA landed, which is the cycle the STEAD line names.

Rows: cycle  dump_t  R|W  addr  data(the 32-bit lane the address selects)  hsize
"""

import re
import sys
from pathlib import Path

# cycleCnt : 0xhaddr hsize htrans hwrite 0xhrdata_hi_lo 0xhwdata_hi_lo hready hresp
LSU = re.compile(
    r"^\s*(\d+) : 0x([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([01]) 0x([0-9a-f]{8})_([0-9a-f]{8}) "
    r"0x([0-9a-f]{8})_([0-9a-f]{8}) ([01]) ([01])"
)
TRANS_NONSEQ = 2

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
path, opts = args[0], args[1:]

rows, pending = [], None
for line in Path(path).read_text(errors="replace").splitlines():
    m = LSU.match(line)
    if not m:
        continue
    cyc, haddr, hsize = int(m.group(1)), int(m.group(2), 16), m.group(3)
    htrans, hwrite, hready = int(m.group(4), 16), m.group(5) == "1", m.group(10) == "1"
    rdata = (int(m.group(6), 16) << 32) | int(m.group(7), 16)
    wdata = (int(m.group(8), 16) << 32) | int(m.group(9), 16)
    if pending and hready:  # data phase of the transfer whose address went out last cycle
        addr, write, size = pending
        both = wdata if write else rdata
        rows.append((cyc, addr, write, (both >> 32) if addr & 4 else (both & 0xFFFFFFFF), size))
        pending = None
    if htrans == TRANS_NONSEQ and hready:  # address phase
        pending = (haddr, hwrite, hsize)
if not rows:
    sys.exit("no transfers found")


def show(sel):
    for cyc, addr, write, data, hsize in sel:
        print(
            f"cycle={cyc:<8} dump_t={100 * cyc + 50:<10} {'W' if write else 'R'} 0x{addr:08x} 0x{data:08x} hsize={hsize}"
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
