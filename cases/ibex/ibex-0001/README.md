# ibex-0001

Repo `ibex` (https://github.com/lowRISC/ibex.git) at `34b0705760ef3dfa00e99637432473d2be8f22f3`. Test `rv32i/I-XOR-01` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['rtl/**']) or in the testbench (['dv/**', 'examples/**', 'shared/**', 'vendor/**', 'util/**']); say which.
- `logs/fail.log`, `logs/pass.log` — the failing run and the clean-tree run of the same test.
- `waves/` — the dumps of both runs (`waves/fail.fst` is the fail wave).

## STEAD

| | |
|---|---|
| Signal | `TOP.ibex_riscv_compliance.u_top.u_ibex_top.rvfi_mem_wdata` |
| Time | 126 |
| Expected | `0x0` |
| Actual | `0x10` |
| Dump | `waves/fail.fst` |

## Hand back

One JSON file:

    {"method", "case": "ibex-0001", "k", "lines": [{"file", "line", "confidence"}],
     "patch", "text", "cost": {"usd", "wall_s"}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`rv32i/I-XOR-01` go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
