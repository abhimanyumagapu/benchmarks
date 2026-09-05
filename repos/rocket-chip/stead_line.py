#!/usr/bin/env python3
"""PASS or STEAD FAIL line for one rocket-chip riscv-compliance run.

usage: stead_line.py <test> <reference_output> <sig.raw> <elf> <run.log> <dump>

E and A come from the signature diff. S and T come from the +verbose commit log: the shimmed
emulator.cc prints "STEAD t=<clock>" before each cycle's commit lines, and S-type stores are
decoded from the instruction word to find the last store to each wrong signature byte.
S is the core's dmem store data (io_dmem_s1_data_data), one cycle before the store commits;
rocket replicates the stored bytes across all 8 lanes, so E and A are replicated the same way.
"""

import re
import subprocess
import sys
from pathlib import Path

SIG = "TOP.TestHarness.ldut.tile_prci_domain.element_reset_domain_rockettile.core.io_dmem_s1_data_data"
COMMIT = re.compile(  # C0: <mcycle> [1] pc=[..] W[r 0=..][0] R[r 8=<rs1>] R[r 9=<rs2>] inst=[<word>]
    r"C0:\s+(\d+) \[1\] pc=\[[0-9a-f]+\] W\[r\s*\d+=[0-9a-f]+\]\[\d\] "
    r"R\[r\s*\d+=([0-9a-f]+)\] R\[r\s*\d+=([0-9a-f]+)\] inst=\[([0-9a-f]+)\]"
)
DUMP_TIME = 2  # dump stamp = 2*cycle (clk low) / 2*cycle+1 (clk high), see emulator.cc
STORE_LAG = -1  # the store's s1_data cycle relative to its commit cycle


def ref_words(path):
    return [int(w, 16) for w in Path(path).read_text().split()]


def sig_words(path):
    """The emulator writes 32 hex chars per line, most significant word first; the compliance
    Makefile splits each line into 8-char words and reverses them. Same here."""
    out = []
    for line in Path(path).read_text().split():
        chunks = [line[i : i + 8] for i in range(0, len(line), 8)]
        out += [int(c, 16) for c in reversed(chunks)]
    return out


def replicate(v, n):
    v &= (1 << (8 * n)) - 1
    while n < 8:
        v |= v << (8 * n)
        n *= 2
    return v


def last_stores(log):
    last, tc = {}, None
    for line in Path(log).read_text(errors="replace").splitlines():
        if line.startswith("STEAD t="):
            tc = int(line[8:])
            continue
        m = COMMIT.search(line)
        if not m or tc is None:
            continue
        rs1, rs2, inst = int(m.group(2), 16), int(m.group(3), 16), int(m.group(4), 16)
        if inst & 0x7F != 0x23:  # 32-bit S-type store only
            continue
        n = 1 << ((inst >> 12) & 3)
        imm = ((inst >> 25) << 5) | ((inst >> 7) & 0x1F)
        imm -= 1 << 12 if imm & 0x800 else 0
        addr = (rs1 + imm) & 0xFFFFFFFFFFFFFFFF
        for k in range(n):
            last[addr + k] = (tc, rs2, n, addr)
    return last


def main(test, ref_path, sig_path, elf, log, dump):
    ref, act = ref_words(ref_path), sig_words(sig_path)
    if ref == act:
        print(f"PASS  test={test}")
        return
    nm = subprocess.run(["riscv64-unknown-elf-nm", elf], capture_output=True, text=True, check=True).stdout
    base = int(re.search(r"([0-9a-f]+) . begin_signature", nm).group(1), 16)
    last = last_stores(log)
    best = None
    for i, (e, a) in enumerate(zip(ref, act, strict=False)):
        if e == a:
            continue
        for j in range(4):
            if (e >> (8 * j)) & 0xFF == (a >> (8 * j)) & 0xFF:
                continue
            st = last.get(base + 4 * i + j)
            if st and (best is None or st[0] < best[0]):
                best = st
    if best is None:
        i = next(i for i, (e, a) in enumerate(zip(ref, act, strict=False)) if e != a)
        print(
            f"NOTE  test={test}  signature word addr=0x{base + 4 * i:08x}  expected=0x{ref[i]:08x}  actual=0x{act[i]:08x}  (never stored)"
        )
        return
    cyc, a_val, n, addr = best
    e_val = a_val
    for k in range(n):  # stored byte k is signature byte addr+k-base
        off = addr + k - base
        e_val = (e_val & ~(0xFF << (8 * k))) | (((ref[off // 4] >> (8 * (off % 4))) & 0xFF) << (8 * k))
    t = DUMP_TIME * (cyc + STORE_LAG) + 1
    print(
        f"FAIL  test={test}  signal={SIG}  time={t}  expected=0x{replicate(e_val, n):016x}  actual=0x{replicate(a_val, n):016x}  dump={dump}"
    )


if __name__ == "__main__":
    main(*sys.argv[1:7])
