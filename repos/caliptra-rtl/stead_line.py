#!/usr/bin/env python3
"""STEAD FAIL line for a caliptra-rtl smoke-test fail.

usage: stead_line.py <rundir> <test> <dump>   (rundir holds console.log and lsu_master_ahb_trace.log)

E and A come from the firmware's own "Expected data: 0x.." / "Actual   data: 0x.." console prints.
S and T come from the LSU AHB trace (written with +CLP_BUS_LOGS): the last 32-bit read whose data
equals A before the print. Prints NOTE when the firmware gave no E/A pair or the read was not found.
"""

import re
import sys
from pathlib import Path

SIG = "TOP.caliptra_top_tb.caliptra_top_dut.initiator_inst.hrdata"
# cycleCnt : 0xhaddr hsize htrans hwrite 0xhrdata_hi_lo 0xhwdata_hi_lo hready hresp
LSU = re.compile(
    r"^\s*(\d+) : 0x([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([01]) 0x([0-9a-f]{8})_([0-9a-f]{8}) "
    r"0x([0-9a-f]{8})_([0-9a-f]{8}) ([01]) ([01])"
)
CON = re.compile(r"(Expected|Actual)\s+data: 0x([0-9a-fA-F]+)")


def dump_time(n):
    """Dump stamp of posedge n: 100 ps steps, clk toggles every 50, posedge n at 100n+50."""
    return 100 * n + 50


def expected_actual(console):
    exp = act = None
    for m in CON.finditer(Path(console).read_text(errors="replace")):
        if m.group(1) == "Expected" and exp is None:
            exp = int(m.group(2), 16)
        if m.group(1) == "Actual" and act is None:
            act = int(m.group(2), 16)
    return exp, act


def last_read_of(trace, value):
    """(cycle, addr, hrdata) of the last AHB-lite 32-bit read that returned `value`."""
    best = pending = None
    for line in Path(trace).read_text(errors="replace").splitlines():
        m = LSU.match(line)
        if not m:
            continue
        n, haddr, htrans, hwrite = int(m.group(1)), int(m.group(2), 16), int(m.group(4), 16), m.group(5)
        hrdata, hready = (int(m.group(6), 16) << 32) | int(m.group(7), 16), m.group(10)
        if pending is not None and hready == "1":  # data phase of the pending read
            half = (hrdata >> 32) if pending & 4 else (hrdata & 0xFFFFFFFF)
            if half == value:
                best = (n, pending, hrdata)
            pending = None
        if htrans == 2 and hwrite == "0" and hready == "1":  # address phase of a read
            pending = haddr
    return best


def main(rundir, test, dump):
    exp, act = expected_actual(f"{rundir}/console.log")
    if exp is None or act is None:
        print(f"NOTE  test={test}  no Expected/Actual pair in console.log")
        return
    best = last_read_of(f"{rundir}/lsu_master_ahb_trace.log", act)
    if best is None:
        print(
            f"NOTE  test={test}  expected=0x{exp:08x}  actual=0x{act:08x}  (no LSU read of the actual value found)"
        )
        return
    n, addr, a_val = best
    e_val = (a_val & 0xFFFFFFFF) | (exp << 32) if addr & 4 else (a_val & ~0xFFFFFFFF) | exp
    print(
        f"FAIL  test={test}  signal={SIG}  time={dump_time(n)}  expected=0x{e_val:016x}  actual=0x{a_val:016x}  dump={dump}"
    )  # noqa: E501


if __name__ == "__main__":
    main(*sys.argv[1:4])
