# ibex-0001

Repo `ibex` (https://github.com/lowRISC/ibex.git) at `34b0705760ef3dfa00e99637432473d2be8f22f3`. Test `rv32i/I-XOR-01` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['rtl/**']) or in the testbench (['dv/**', 'examples/**', 'shared/**', 'vendor/**', 'util/**']); say which.
- `logs/fail.log` — the failing run's verdict, and next to it every other log that run wrote
  (traces, console, bus logs). `tools/` — scripts for them; the skill says what each does.
- `waves/` — the failing run's dump (`waves/fail.fst`).

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
