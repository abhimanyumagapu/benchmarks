# cva6-0001

Repo `cva6` (https://github.com/openhwgroup/cva6.git) at `e643a3953d3945319ef5a95b6091b510fb8f157d`. Test `rv64ui-p-xor` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['core/**']) or in the testbench (['corev_apu/tb/**', 'verif/**', 'tools/**', 'config/**']); say which.
- `logs/fail.log` — the failing run's verdict, and next to it every other log that run wrote
  (traces, console, bus logs). `tools/` — scripts for them; the skill says what each does.
- `waves/` — the failing run's dump (`waves/fail.fst`).

## STEAD

| | |
|---|---|
| Signal | `TOP.ariane_testharness.i_ariane.i_cva6.wdata_commit_id` |
| Time | 966 |
| Expected | `0xf00ff00f` |
| Actual | `0xf00ff01f` |
| Dump | `waves/fail.fst` |

## Hand back

One JSON file:

    {"method", "case": "cva6-0001", "k", "lines": [{"file", "line", "confidence"}],
     "patch", "text", "cost": {"usd", "wall_s"}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`rv64ui-p-xor` go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
