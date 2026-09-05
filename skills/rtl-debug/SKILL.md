---
name: rtl-debug
description: Debug a failing RTL simulation like a DV engineer and hand back a ranked root cause.
---

# RTL debug

You are in a STEAD-Bench case folder. A test failed on this tree and passes on the unmodified
commit. Find the RTL line that caused it.

## Read in this order

1. `README.md`: the test, the repo, the STEAD record if there is one.
2. `logs/fail.log`: the checker's own words. The `FAIL` line names the signal (S), the time (T)
   it held the wrong value, expected (E) and actual (A). Trust S and T over anything you infer.
3. `logs/pass.log`: the same test on the clean tree, for comparison.
4. `waves/fail.*`: the dump. Open it with pywellen (`python -c`), never by eye:

   ```python
   import pywellen
   w = pywellen.Waveform("waves/fail.fst")
   w["<full.signal.name>"].signal.value_at(<t>)      # int, or a string with x/z, or None before first change
   list(w["<full.signal.name>"].tv)                   # all (time, value) changes
   ```

   `waves/pass.*` is the same test on the clean tree; the same signal at the same time there is
   the value that was expected.
5. `tree/`: the source. `case.yaml` lists `dut_paths` (where the bug is) and `checker_paths`
   (the testbench; it is correct and off limits).

## How to work

- Start at S and T and go backwards through the logic that drives S, one stage at a time,
  checking each input against the pass dump until the wrong value has no wrong input.
- Say DUT or TB for every claim. The checker is right by construction here; do not rewrite it.
- Show evidence: a signal name, a time, a value, a file:line. No evidence, no claim.
- Prefer the smallest cause. A one-line RTL edit that explains the whole fail beats a theory.
- Do not modify anything under this folder. If you propose a patch, put it in the answer.

## Answer

Finish with one JSON object in a ```json block, and nothing after it:

```json
{"k": 3,
 "lines": [{"file": "rtl/<file>.sv", "line": 123, "confidence": 0.7}],
 "patch": "<unified diff against tree/, paths relative to tree/, or null>",
 "text": "<one paragraph: what is wrong and why>"}
```

`lines` is best first, at most `k`. Paths are relative to `tree/`. The patch may touch
`dut_paths` only.
