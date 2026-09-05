#!/usr/bin/env python3
"""PASS or STEAD FAIL line for one ibex riscv-compliance run.

usage: stead_line.py <test> <reference_output> <stdout> <trace.log> <dump>

E and A come from the signature diff (reference vs the SIGNATURE: lines the sim printed).
S and T come from the RVFI trace: the earliest store that last wrote a wrong signature byte.
S is rvfi_mem_wdata, the unshifted store data bus, so E is rebuilt byte by byte onto A.
Prints NOTE instead of FAIL when the wrong word was never stored (no STEAD, still a fail).
"""

import re
import sys
from pathlib import Path

SIG = "TOP.ibex_riscv_compliance.u_top.u_ibex_top.rvfi_mem_wdata"
STORE = re.compile(
    r"^\s*(\d+)\s+\d+\s+[0-9a-f]+\s+[0-9a-f]+\s+(c\.)?(sw|sh|sb)[a-z]*\s.*PA:0x([0-9a-f]+)\s+store:0x([0-9a-f]+)"
)
SIZE = {"sw": 4, "sh": 2, "sb": 1}


def words(path, pattern=None):
    """Hex words, one per line; with `pattern`, only matching lines and only group 1."""
    out = []
    for raw in Path(path).read_text().splitlines():
        text = raw.rstrip("\r")
        if pattern:
            m = re.match(pattern, text)
            if not m:
                continue
            text = m.group(1)
        if text:
            out.append(int(text, 16))
    return out


def last_stores(trace):
    """byte address -> (time, store data, size, address offset) of the last store to it."""
    last = {}
    for line in Path(trace).read_text(errors="replace").splitlines():
        m = STORE.match(line)
        if not m:
            continue
        t, pa, val = int(m.group(1)), int(m.group(4), 16), int(m.group(5), 16)
        n = SIZE[m.group(3)]
        for k in range(n):
            last[pa + k] = (t, val, n, pa & 3)
    return last


def main(test, ref_path, stdout, trace, dump):
    ref = words(ref_path)
    act = words(stdout, r"SIGNATURE: 0x([0-9a-fA-F]+)")
    if ref == act:
        print(f"PASS  test={test}")
        return
    m = re.search(r"Reading signature from 0x([0-9a-f]+)", Path(stdout).read_text(errors="replace"))
    base = int(m.group(1), 16) if m else None
    if base is None:
        print(f"NOTE  test={test}  signature differs, no signature base in stdout")
        return
    last = last_stores(trace)
    best = None
    for i, (e, a) in enumerate(zip(ref, act, strict=False)):
        if e == a:
            continue
        for j in range(4):
            if (e >> (8 * j)) & 0xFF == (a >> (8 * j)) & 0xFF:
                continue
            st = last.get(base + 4 * i + j)
            if st and (best is None or st[0] < best[0][0]):
                best = (st, e)
    if best is None:
        i = next(i for i, (e, a) in enumerate(zip(ref, act, strict=False)) if e != a)
        print(
            f"NOTE  test={test}  signature word addr=0x{base + 4 * i:08x}  expected=0x{ref[i]:08x}  actual=0x{act[i]:08x}  (never stored)"
        )
        return
    (t, a_val, n, off), e_word = best
    e_val = a_val
    for k in range(n):  # stored bytes are the low bytes of rvfi_mem_wdata
        e_val = (e_val & ~(0xFF << (8 * k))) | (((e_word >> (8 * (off + k))) & 0xFF) << (8 * k))
    print(
        f"FAIL  test={test}  signal={SIG}  time={t}  expected=0x{e_val:08x}  actual=0x{a_val:08x}  dump={dump}"
    )


if __name__ == "__main__":
    main(*sys.argv[1:6])
