# scr1-0001

Repo `scr1` (https://github.com/syntacore/scr1.git) at `ebb5e3551a9d93c0ee95f0b767dd878b8927e702`. Test `arch_xor-01.hex` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['src/core/**']) or in the testbench (['src/tb/**', 'sim/**', 'dependencies/**', 'Makefile']); say which.
- `logs/fail.log` — the failing run's verdict, and next to it every other log that run wrote
  (traces, console, bus logs). `tools/` — scripts for them; the skill says what each does.
- `waves/` — the failing run's dump (`waves/fail.fst`).

## STEAD

| | |
|---|---|
| Signal | `TOP.scr1_top_tb_axi.i_top.io_axi_dmem_wdata` |
| Time | 1166 |
| Expected | `0x66666666` |
| Actual | `0x66666676` |
| Dump | `waves/fail.fst` |

## Hand back

One JSON file:

    {"method", "case": "scr1-0001", "k", "lines": [{"file", "line", "confidence"}],
     "patch", "text", "cost": {"usd", "wall_s"}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`arch_xor-01.hex` go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
