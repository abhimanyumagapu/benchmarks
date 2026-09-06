#!/usr/bin/env python3
"""scr1 write tracker from the wave: data-memory bus writes and register-file writes.

    python tools/dmem.py waves/fail.fst --time <T> [--window N]   writes within N time units of T (default 200)
    python tools/dmem.py waves/fail.fst --value 0x<hex>            every write carrying a value

Rows: time  bus|rf  address-or-register  data
"""

import sys

import pywellen

TOP = "TOP.scr1_top_tb_axi.i_top"
MPRF = f"{TOP}.i_core_top.i_pipe_top.i_pipe_mprf"

args = sys.argv[1:]
if len(args) < 2:
    sys.exit(__doc__)
w = pywellen.Waveform(args[0])
opts = args[1:]


names = {v.full_name for v in w.all_vars()}


def changes(name):
    return list(w[name].tv) if name in names else []


def value(name, t):
    return w[name].signal.value_at(t) if name in names else None


rows = []
# AXI data-memory write channel: data valid with the address of the same transaction
for t, valid in changes(f"{TOP}.io_axi_dmem_wvalid"):
    if valid == 1:
        rows.append((t, "bus", value(f"{TOP}.io_axi_dmem_awaddr", t), value(f"{TOP}.io_axi_dmem_wdata", t)))
# register-file writes
for t, req in changes(f"{MPRF}.exu2mprf_w_req_i"):
    if req == 1:
        rows.append(
            (t, "rf", f"x{value(f'{MPRF}.exu2mprf_rd_addr_i', t)}", value(f"{MPRF}.exu2mprf_rd_data_i", t))
        )
rows.sort(key=lambda r: r[0])
if not rows:
    sys.exit("no writes found; check the signal names in the wave with tools/wave.py")


def fmt(v):
    return f"0x{v:08x}" if isinstance(v, int) else str(v)


def show(sel):
    for t, kind, where, data in sel:
        print(f"t={t:<10} {kind:3} {fmt(where) if isinstance(where, int) else where:<12} {fmt(data)}")


if "--time" in opts:
    t = int(opts[opts.index("--time") + 1])
    n = int(opts[opts.index("--window") + 1]) if "--window" in opts else 200
    show([r for r in rows if abs(r[0] - t) <= n])
elif "--value" in opts:
    v = int(opts[opts.index("--value") + 1], 16)
    show([r for r in rows if r[3] == v])
else:
    show(rows)
