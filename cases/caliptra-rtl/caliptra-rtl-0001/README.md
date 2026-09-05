# caliptra-rtl-0001

Repo `caliptra-rtl` (https://github.com/chipsalliance/caliptra-rtl.git) at `1f272de5be683cce9146614a1537bb0db45ec392`. Test `smoke_test_sha256` fails on this tree; it passes on the
unmodified commit. Find the cause.

## What you get

- `tree/` — the full buggy source tree, design docs included. The bug may be in the DUT
  (['src/*/rtl/**']) or in the testbench (['src/integration/tb/**', 'src/integration/test_suites/**', 'src/integration/stimulus/**', 'tools/**']); say which.
- `logs/fail.log`, `logs/pass.log` — the failing run and the clean-tree run of the same test.
- `waves/` — the dumps of both runs (`waves/fail.fst` is the fail wave).

## STEAD

| | |
|---|---|
| Signal | `TOP.caliptra_top_tb.caliptra_top_dut.initiator_inst.hrdata` |
| Time | 6181450 |
| Expected | `0xba7816bf` |
| Actual | `0xba7816af` |
| Dump | `waves/fail.fst` |

## Hand back

One JSON file:

    {"method", "case": "caliptra-rtl-0001", "k", "lines": [{"file", "line", "confidence"}],
     "patch", "text", "cost": {"usd", "wall_s"}}

Ranked lines are scored hit@k against the hidden gold window. A patch is re-run and must make
`smoke_test_sha256` go FAIL -> PASS, touching only the side
the bug is on. Text is judged.
