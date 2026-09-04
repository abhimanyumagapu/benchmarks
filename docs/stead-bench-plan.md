# STEAD-Bench

A benchmark for **functional** RTL debug. Any simulator, any tool.

**STEAD** = Signal, Time, Expected, Actual, Dump (fail VCD). The best fail record we can hand out. Not something a tool has to take.

---

## What it does

A test failed. The sim log contains a value check, and there is a waveform.

```
FAIL  test=<name>  signal=<hier.S>  time=<t>  expected=<E>  actual=<A>
```

The **bench** produces a fail (and whatever else the run naturally has). Each **tool picks what it wants** — fail VCD, pass VCD, full log, spec, test source, golden/ISS. 

A **case** is three things: a buggy tree, a test that fails on it, and a hidden gold. Nothing else is fixed. STEAD is a bonus on top, not the price of entry. Compare Claude, Codex, ChipAgents, CRUX, Walker on that same fail: gold line/file, time, $.

---

## How a case runs (bird’s eye)

We do **not** check in waves. We **take a test**, sit on a **buggy commit** (HWE’s pre-fix SHA, or an inject on a known-good tree), and **run the sim on the fly**. Each case names its own **sim recipe** — tool, flags, filelist — so swapping Verilator for VCS or Xcelium changes the recipe, not the bench.

1. **Test** — an existing self-checking test (directed smoke, ISA, firmware). On the clean tree it **PASS**es. That is the sanity gate (same idea as HWE’s fail→pass, just in reverse for setup).
2. **Buggy tree** — checkout the buggy commit, or apply one RTL (or test) edit. Same test, same TB, frozen.
3. **Run** — the sim with dump on, **on the fly** (nothing pre-baked). The wave is whatever that sim writes (VCD, FSDB, SHM); the case records the format. Clean tree → PASS log + **pass VCD**. Buggy tree → FAIL log (shim writes S, t, E, A) + **fail VCD**. Specs, tests, ISS/golden stay in the tree if the repo has them.
4. **Debug** — every method may take **any subset** of that pile (Walker might only want fail VCD + log; CRUX pass+fail; ChipAgents log+wave+spec; Claude/Codex whatever the skill says). Same buggy commit, same test.
5. **Score** — hidden gold is the line we injected (or the HWE PR). Tools answer in different shapes, so see **What a method hands back** below.

One catch when you swap sims: Verilator with `-x-assign 0` is 2-state, VCS and Xcelium are 4-state. A bug can fail on one and pass on the other. So each case records the sim it was **validated** on, and gets re-validated when you swap.

---

## A case is a folder, not a script

ChipAgents and Bronco are closed. We cannot call them from a harness. So a case ships as a **folder** — RTL tree, TB, test, logs, waves, spec, and a README saying what to find — plus a hidden gold and a scorer.

Anyone can work that folder: an agent, a vendor under NDA, a human at a desk. They hand back one file and we score it the same way. That is what makes the bench universal — not the input menu.

## What a method hands back

Tools answer in different shapes, so the submission takes all of them:

- **ranked lines** — file and line, best first. Scored pass@k, k declared up front. ChipAgents ranks by confidence and reports @1 and @2.
- **a patch** — scored by re-running the **same** test: it must go fail → pass, and the checker must be untouched.
- **free text** — a ticket or an explanation. Judged.

Walker gives one line. ChipAgents gives a ranked list plus a patch. Bronco gives a ticket. All three have to be scorable, or "swap the tool in" is not true.

---

## What we take from HWE-Bench (and what we don’t)

[HWE-Bench](https://github.com/pku-liang/hwe-bench) is the SWE-bench analog for hardware: 417 real PR bugs, container, fail→pass. We copy that **harness idea** (frozen buggy tree, hidden gold, optional patch check).

We do **not** copy the **task**. HWE gives a GitHub-style issue and asks for a patch. We produce a **failing sim** (and a passing one, and whatever else is in the repo) and ask for the cause. Each tool chooses its inputs. ChipAgents’ own bench already said VerilogEval/CVDP have “debugging, but no waveform debugging”; OSS agents scored **0% pass@3** on waves. That is the gap.

HWE already ran **Verilator** on Ibex, CVA6, Caliptra, XiangShan, and Rocket Chip (**172 / 417**). Only OpenTitan was VCS (UVM). So we can overlap HWE on open-source sim. Their `tb_script` only needed PASS/FAIL after a patch — they never printed S, t, E, A and they never shipped a VCD.

ChipAgents RCA (private injected bugs, median 5k LOC) and Bronco (customer SoC, ~50% exact RCA + 25% file, 15 min) also score **root cause from a fail**, not spec-to-RTL. We score the same kind of thing, on public cores, with a log the agent has to read.

---

## Running 80 cases

We take the HWE-Bench **arch**, not its runner. Three stages:

1. **Bake** — container, buggy tree, test, sim recipe. Run it. Keep the fail log, both waves, and the pass run. Check the case is real: clean tree **PASS**es, buggy tree **FAIL**s on the value check. Out comes the case folder. Done **once per bug**, not once per tool.
2. **Solve** — the folder goes out. An agent, a vendor under NDA, or a human works it and hands back one submission file. This stage sits **outside** the harness on purpose, because ChipAgents and Bronco cannot be called from one.
3. **Score** — read the submission. Ranked lines → pass@k against the hidden gold. Patch → apply it in the same container, re-run the same test, must go fail → pass. Text → judged.

Stages 1 and 3 are HWE (container, frozen commit, fail→pass). Stage 2 is the part HWE does not have — and the part we cannot automate for a closed tool.

80 bugs across every tool is only expensive in stage 2. Bake once, hand the same folder to everyone. Waves are the storage cost, so gate the dump around the failure instead of dumping the whole run.

---

## Repos (`work/repos`)

HWE’s six, plus two directed cores we already debug:

| Repo | In HWE? | Verilator TB | UVM TB |
|---|---|---|---|
| ibex | yes (35) | yes | yes |
| cva6 | yes (35) | yes | yes |
| caliptra-rtl | yes (16) | yes | yes (UVMF) |
| opentitan | yes (245, **VCS**) | yes, not what HWE scored | yes |
| XiangShan | yes (54) | `make emu` — `difftest/` empty until submodule init | no |
| rocket-chip | yes (32) | yes (`emulator.cc`) | no |
| openc910 | no | yes (CRUX already dumped fail VCDs) | no |
| scr1 | no | yes | no |

v1: **Ibex**. Its Spike cosim already fails per retired instruction, so the time is real with no shim, and it sits next to HWE numbers. **OpenC910** next — directed tests, and the control case where we build the write-tracker that recovers the time from an end-of-test check. SCR1 after that.

---

## What it cannot do

Not timing, CDC, RDC, or performance. Not hangs, compile crashes, silent passes, or coverage holes. No expected vs actual in the log → no STEAD line, but still a case.

---

## Lockup: STEAD shim

**This blocks STEAD, not the bench.** No TB prints that `FAIL … signal= time= expected= actual=` line. Tests already fail and waves already dump; the log is just `TEST FAIL`. **Build a shim** on the existing Verilator fail path that prints the line (`S` = a dumped DUT name). Until then there are no STEAD cases — but a case with a buggy tree, a failing test and the two waves runs today. Build the shim; do not wait on it.

UVM does **not** give STEAD either. Fail is Spike/RVFI cosim or `UVM_ERROR`; dump is FSDB/SHM of the TB top; the log still has no S, t, E, A. Same missing line, plus VCS/Xcelium. Leave UVM until the Verilator shim works.

---

## After the shim

Inject an RTL bug or break the test, keep the TB frozen, score localization.

The LLM methods get a **skill file that tells them how to debug like a DV engineer** — same idea as Bronco’s playbook and ChipAgents’ RCA loop: what to open first (log, fail wave, pass wave, spec), don’t rewrite the checker, say DUT vs TB, show your evidence. It must not hand out one tool's loop — "walk `S` backwards" is Walker's method, and giving that to everyone tests Walker, not them. That is what those companies ship; we write it down as a skill instead of a closed agent. ChipAgents/CRUX/Walker already have tools and may ignore the skill and take their usual inputs. Then run the comparison table.
