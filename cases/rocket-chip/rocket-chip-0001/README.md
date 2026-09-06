# rocket-chip-0001

Repo `rocket-chip` (https://github.com/chipsalliance/rocket-chip.git) at `55bcad0f59436de98ea510334121de8546b9e9d7`. Test `rv64i/SUBW` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['src/main/scala/**']) or in the testbench (['src/main/resources/**', 'build.sc', 'dependencies/**']); say which.
- `logs/fail.log` — the failing run's verdict, and next to it every other log that run wrote
  (traces, console, bus logs). `tools/` — scripts for them; the skill says what each does.
- `waves/` — the failing run's dump (`waves/fail.fst`).

## STEAD

| | |
|---|---|
| Signal | `TOP.TestHarness.ldut.tile_prci_domain.element_reset_domain_rockettile.core.io_dmem_s1_data_data` |
| Time | 207335 |
| Expected | `0x0` |
| Actual | `0x1000000010` |
| Dump | `waves/fail.fst` |

## Hand back

One JSON file:

    {"method", "case": "rocket-chip-0001", "k", "lines": [{"file", "line", "confidence"}],
     "patch", "text", "cost": {"usd", "wall_s"}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`rv64i/SUBW` go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
