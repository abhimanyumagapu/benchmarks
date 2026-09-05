# rocket-chip-0001

Repo `rocket-chip` (https://github.com/chipsalliance/rocket-chip.git) at `55bcad0f59436de98ea510334121de8546b9e9d7`. Test `rv64i/SUBW` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['src/main/scala/**']) or in the testbench (['src/main/resources/**', 'build.sc', 'dependencies/**']); say which.
- `logs/fail.log`, `logs/pass.log` — the failing run and the clean-tree run of the same test.
- `waves/` — the dumps of both runs (`waves/fail.fst` is the fail wave).

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
