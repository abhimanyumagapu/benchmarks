---
name: rtl-debug
description: Debug a failing RTL simulation like a DV engineer and hand back a ranked root cause and a fix.
---

# RTL debug

You are in a STEAD-Bench case folder. A test failed on this tree and passes on the unmodified
commit. Find the RTL line that caused it, fix it, and show your evidence.

## Read in this order

1. `README.md`: the test, the repo, the STEAD record if there is one.
2. `logs/fail.log`: the checker's own words. The `FAIL` line names the signal (S), the time (T)
   it held the wrong value, expected (E) and actual (A). Trust S and T over anything you infer.
3. `logs/`: everything else the failing run wrote: the instruction trace, the console, the bus log.
   The core's skill section below says what each file is and which tool reads it.
4. `waves/fail.*`: the dump. Read it with a tool, never by eye:

   ```
   python tools/wave.py waves/fail.fst <full.signal.name> [<time>]     one value, or all changes
   ```
   or pywellen directly: `w = pywellen.Waveform(path); w[name].signal.value_at(t)`.
5. `tree/`: the source. `case.yaml` lists `dut_paths` (where the bug is) and `checker_paths`
   (the testbench; it is correct and off limits).

## Tools in the folder

- `tools/wave.py <dump> <signal> [<time>]`: a signal's value at a time, or all its changes; an
  unknown name lists candidates.
- The simulator: `sim` if you have it as a tool, otherwise `stead-sim <test> [--dump]`. It rebuilds
  your edited `tree/` and runs one test in the core's own simulator, and returns PASS, FAIL,
  BUILD_ERROR or CRASH with the log; `--dump` also writes `waves/sim.fst`. The test from the README
  is the one to run. A rebuild takes seconds on small cores and minutes on cva6 and caliptra: use it
  to confirm a fix, not to explore.
- `tools/` may hold scripts specific to this core; the core's skill section says what they do.
- Write your own. A query you would run twice belongs in a script under `tools/`: one purpose,
  standard library plus pywellen, a docstring with the usage line, arguments not hard-coded values,
  prints what it found and nothing else. `tools/` is yours to extend; it is not part of the patch.

## Method

1. **Triage.** From the fail log, state in one line what the checker compared and what it saw:
   a wrong value, a missing or extra event, a hang. Note the test's intent (which instruction,
   which feature) from its name and source. If there is a STEAD record, that is your anchor.
2. **Anchor.** Confirm S at T in the dump shows A, and find when S last held the right value. Map
   T to the core's cycle count and to the trace line it belongs to; the core's skill section gives
   the arithmetic. From here on every claim carries a time.
3. **Trace backward, one stage at a time.** S is driven by some logic from some inputs. At time T,
   read those inputs in the dump. Decide for each whether it is right, using what the design should
   have produced: the ISA semantics of the instruction in flight, the reference model's value, the
   spec. Follow the wrong input back through its own driver. Stop at the first point where a wrong
   output has only right inputs: that block, at that time, holds the bug. Keep the chain as a list
   of (signal, time, value, should be); it is your evidence.
4. **Find the line.** Read the block's source at that point. Name the mechanism in one sentence:
   the constant, the wrong select, the missing case. It must explain E, A and T exactly, including
   why the value is off by that amount and why it appears at that time. A theory that explains most
   of the symptom is a symptom, not a cause.
5. **Argue against yourself before you commit.** Write two reasons this line is the root cause and
   two reasons it could be a symptom of something earlier (a wrong operand arriving here, a control
   signal set upstream). Check the earlier candidates in the dump. Models assume logic is fine when
   the code looks plausible; forced counter-arguments are what catch inverted conditions and bad
   constants.
6. **Smallest fix.** One line where one line explains it. Do not refactor, rename, or clean up.
7. **Confirm.** Rebuild and run the failing test with the simulator tool; it must PASS. Ask what
   else the same line affects: other instructions through the same path, other tests; run one if
   in doubt. A fix that greens the named test but breaks the path for its siblings is not a fix.
8. **Report** with the evidence chain, DUT or TB for every claim, and the answer block below.

## What to look for

Injected and real RTL bugs cluster in a few shapes. Check them in this order at the suspect block:

- **A stray constant or flipped bit**: `^ 32'h10`, `| 1'b1`, an off-by-one literal, a wrong reset
  value. E and A differ by a single bit or a small constant.
- **Wrong bit select or width**: `[31:1]` for `[30:0]`, sign extension where zero extension is
  meant, a truncated concatenation, byte lanes swapped. A differs in the top or bottom bits.
- **Wrong operand, mux select, or opcode case**: the right operation on the wrong input, a case
  item pointing at a neighbour's result, a missing `default`. A equals some other correct value.
- **Inverted or missing condition**: `!` dropped or added, `==` for `!=`, a valid or enable
  ignored. The wrong value appears only under one condition; check the condition's inputs at T.
- **Off by a cycle**: a register stage added or removed, a bypass or forwarding path that returns
  the previous value, a stall that does not hold. A is a value the signal held one cycle earlier or
  later; the trace shows the right value one instruction away.
- **Control**: a state machine transition, a priority order in `if`/`else`, a CSR write mask or
  read mux, an exception or interrupt taken or not taken. The symptom is far from the cause; the
  backward trace is the only way there.

## Traps

- Signal and variable names lie. Read the assignment, not the name.
- Widths and signedness: check the declaration of every operand in a suspect expression.
- `x` or `z` at T means an uninitialised or undriven path; follow it to the reset or the enable.
- The checker is right by construction. If the testbench looks wrong, you have not found the bug.
- The first plausible line is rarely the last. Finish the backward trace before you edit.
- Keep the time with every value you quote; a value without a time is not evidence.
- No network, no history. Do not search the web, fetch anything, or look up the repo's history.
  The folder is all the evidence there is.
- Fix it in place: edit the file under `tree/` when you are confident. Your edits to `tree/` are
  taken as the patch. Never edit anything outside `tree/`, and nothing under the checker paths.

## Answer

Finish with one JSON object in a ```json block, and nothing after it:

```json
{"k": 3,
 "lines": [{"file": "rtl/<file>.sv", "line": 123, "confidence": 0.7}],
 "text": "<one paragraph: what is wrong and why, with the evidence chain: signal, time, value, should be>"}
```

`lines` is best first, at most `k`. Paths are relative to `tree/`. The patch is whatever you
changed under `tree/`; it may touch `dut_paths` only.
