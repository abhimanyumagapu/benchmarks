# STEAD-Bench Build Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Rules: `AGENTS.md`.

**Goal:** bake real cases from Ibex and SCR1, run Claude / CRUX / Walker on them, print the table.

**Architecture:** bake / solve / score (see `docs/stead-bench-plan.md`). The harness core is done
and tested against a fake repo. Every remaining task either wraps something that already exists
(`stead-port` runners, HWE Dockerfiles, CRUX CLI, pywellen) or adds one small module. Nothing is
written from scratch that another repo on this machine already has.

**Tech stack:** Python 3.11+, pyyaml, pywellen 0.25.6 (wave read), ruff, pytest. Verilator on the
Linux box. `git` for trees. No other dependencies without a line in this plan saying why.

**Spec:** `docs/stead-bench-plan.md`. TB contract: `stead/recipe.py` docstring.

## Global constraints

- Cyclomatic complexity <= 12 per function (ruff C901); split, never raise.
- No mocks: tests use `tests/fixtures/fakerepo/run.sh` and `tests/fixtures/mini.vcd`.
- Patches touch `dut_paths` only. Gold never inside a case folder. Cores never vendored.
- Never commit; the owner commits.
- `STEAD` FAIL line: `FAIL  test=<t>  signal=<S>  time=<T>  expected=0x<E>  actual=0x<A>  dump=<D>`.
  All four or none. Exit codes: 0 PASS, 1 FAIL, 2 build error, 3 crash/hang/timeout.

## Where things come from (reuse map)

| Need | Source | Take |
|---|---|---|
| Wave read | `~/work/walker` (`walker/waveform/query.py`) | pywellen engine; `value_at` semantics, "never `var[t]`" |
| Coding rules, ruff set | `~/work/walker` branch `elaborator-v2` | `docs/coding-practices/python_rules.md` (ported), ruff `select` (ported) |
| Ibex compliance runner | `~/work/stead-port/Z/ibex/ibex.sh` | fusesoc build line, `Vibex_riscv_compliance --trace --raminit` per test |
| Ibex STEAD line | `~/work/stead-port/Z/ibex/ibex_stead.py` | signature diff + RVFI trace → S,T,E,A (move, parametrise paths) |
| SCR1 runner + shim | `~/work/stead-port/Z/scr1/scr1.sh`, `shims/scr1-stead.patch` | TB write-tracker patch, `+test_info` invocation |
| Repo pins | `~/work/stead-port/shims/README` | scr1 `ebb5e35`, riscv-compliance `d51259b` |
| Bug classes | `~/work/walker/research/dv_bug_types.md` §3, §4, §7 | mutation catalogue |
| Dockerfiles | `~/work/hwe-bench_fork/hwe_bench/harness/repos/verilog/*/` `dockerfile()` + `_prepare_dev_script()` | toolchain install per repo |
| HWE Ibex bugs | HF dataset `henryen/hwe-bench`, `ibex.jsonl` | `base.sha`, `fix_patch`, `tb_script` |
| CRUX | `~/work/crux` (`python run.py <design>`, `design_<d>/user_config.json`, `outputs/*/run_report.json`) | adapter |
| OpenC910 recipe | `~/work/vcds/README.md` | xuantie gcc, Srec2vmem, `--no-timing`, K4 bug |

## Done (39 tests, ruff clean)

`stead/fail.py` `wave.py` `validate.py` `case.py` `gold.py` `patch.py` `recipe.py` `bake.py`
`score.py` `__main__.py` (`stead bake|score|validate`). Case folder layout:
`cases/<repo>/<id>/{case.yaml,README.md,tree/,logs/{pass,fail}.log,waves/{pass,fail}.<fst|vcd>}`;
gold at `gold/<repo>/<id>/{gold.yaml,bug.patch}`; results at `results/<case>/<method>.json`.

---

### Task 1: SCR1 recipe `repos/scr1/run.sh` (Linux box)

**Reuse:** `stead-port/shims/scr1-stead.patch` (already applied on the `stead` branch of the SCR1
clone; it adds the write-tracker and the FAIL line to the TB) and the invocation in
`repos/scr1/Makefile:294` (`run_verilator_wf`): the Verilator binary takes `+test_info=<file>`, a
list of tests, so a single test is a one-line `test_info`.

**Files:** create `repos/scr1/run.sh`, `repos/scr1/NOTES.md`, `repos/scr1/dut_paths.txt`
(`src/core/**`), `repos/scr1/checker_paths.txt` (`src/tb/**`, `sim/**`, `dependencies/**`).

**Interface:** the `run.sh` contract in `stead/recipe.py`. Test name = the hex name as it appears
in `test_info` (e.g. `arch_xor-01.hex`).

- [ ] `build <tree>`: `make -C <tree> BUS=AXI TRACE=1 tests` (compiles every test hex once; RTL
  edits do not invalidate it) then `make -C <tree>/sim build_verilator_wf ...` with the same
  `SIM_CFG_DEF`/`SIM_TRACE_DEF` the top Makefile passes. Exit 2 on any make failure. Print nothing
  else.
- [ ] `run <tree> <test> <out_dir>`: `grep "^<test>" <tree>/build/.../test_info > <out_dir>/test_info`;
  cd `<out_dir>`; run `V<top> +test_info=test_info +test_results=results.txt` with the FST enabled by
  the shim (check `0002-scr1-fst-dumps.patch` for the plusarg or env var it reads; `--dump=off`
  skips it); `sed` the ANSI codes off into `sim.log`; `mv simx.fst dump.fst`. Exit: 0 if the results
  line says PASS, 1 if `sim.log` has a `FAIL ` line, 3 on non-zero sim exit or timeout.
- [ ] Verify on a clean tree: `run.sh build` then `run.sh run <tree> arch_xor-01.hex out` exits 0.
  Inject `scr1_pipe_ialu.sv:571` (XOR `^ 32'h10`), rebuild, run: exit 1, `sim.log` has a FAIL line,
  `python -m stead validate out/sim.log` prints `OK`.
- [ ] `NOTES.md`: sample fail line, how S/T are derived (write-tracker), runtime per test, the
  2-state flags used.

**Optimization:** hex compile happens once per tree and survives the bug patch (bake rebuilds in the
same tree). The FST is per test, not per batch, so no symlinking a 200-test dump.

### Task 2: Ibex recipe `repos/ibex/run.sh` (Linux box)

**Reuse:** `stead-port/Z/ibex/ibex.sh` for the fusesoc build and the per-test simulator command;
`Z/ibex/ibex_stead.py` for the STEAD line. riscv-compliance at `d51259b` with
`stead-port/shims/riscv-compliance-zicsr.patch`.

**Files:** create `repos/ibex/run.sh`, `repos/ibex/stead_line.py` (moved `ibex_stead.py`, paths
taken as arguments, `ROOT` removed), `repos/ibex/NOTES.md`, `repos/ibex/dut_paths.txt` (`rtl/**`),
`repos/ibex/checker_paths.txt` (`dv/**`, `examples/**`, `shared/**`, `vendor/**`).

**Interface:** test name = `<isa>/<test>` (`rv32i/I-XOR-01`). Env: `STEAD_COMPLIANCE` = path of the
riscv-compliance clone (set by `run.sh` itself from `~/riscv-compliance` if unset).

- [ ] `build <tree>`: fusesoc line from `ibex.sh` (drop the homebrew `-CFLAGS`, keep
  `-Wno-UNOPTFLAT`, drop `--BaseIsa`). Then, once per machine, not per tree:
  `make RISCV_ISA=<isa>` for the five ISAs in the compliance clone with
  `RISCV_TARGET=ibex RISCV_DEVICE=rv32imc RISCV_PREFIX=riscv64-unknown-elf-`, guarded by a stamp
  file, because the test ELFs do not depend on the RTL.
- [ ] `run <tree> <isa>/<test> <out_dir>`: cd `<out_dir>`;
  `Vibex_riscv_compliance --trace=dump.fst --term-after-cycles=100000 --raminit=<compliance>/work/<isa>/<test>.elf.vmem > stdout`;
  `mv trace_core_00000000.log trace.log`. Compare `SIGNATURE:` lines of `stdout` with
  `riscv-test-suite/<isa>/references/<test>.reference_output` (strip `\r`). Equal: write
  `PASS  test=<test>` to `sim.log`, exit 0. Different: `python3 stead_line.py <ref> <stdout> <trace.log> dump.fst >> sim.log`,
  exit 1. Sim exit non-zero or no `SIGNATURE:` at all: exit 3.
- [ ] `stead_line.py`: same algorithm as `ibex_stead.py` (last store per wrong byte, earliest wins,
  `rvfi_mem_wdata` byte reconstruction); prints `NOTE` when never stored. Test on the Mac with the
  fixture files copied from a Linux fail run into `tests/fixtures/ibex/` (stdout, trace.log,
  reference). `tests/test_ibex_stead_line.py`: one test, the I-XOR-01 fail gives time 108,
  `0xfffff800`/`0xfffff810`.
- [ ] Verify like Task 1 with `rtl/ibex_alu.sv:386` (XOR bit 4). Known-bad on a clean tree
  (I-EBREAK-01, I-ECALL-01, I-MISALIGN_JMP-01, I-MISALIGN_LDST-01) are never used as case tests.

**Optimization:** compliance ELFs built once per machine. Verilator build once per tree state. The
RVFI trace is what turns a signature diff into a time; it costs nothing extra.

### Task 3: first real bakes: `scr1-0001`, `ibex-0001` (Linux box)

**Files:** create `specs/scr1/scr1-0001.yaml` + `specs/scr1/scr1-0001.patch`,
`specs/ibex/ibex-0001.yaml` + `specs/ibex/ibex-0001.patch`. Spec format is what `cmd_bake` reads:

```yaml
id: ibex-0001
repo: ibex
url: https://github.com/lowRISC/ibex
commit: <sha the Linux box has running>
test: rv32i/I-XOR-01
bug_patch: ibex-0001.patch
gold: {file: rtl/ibex_alu.sv, start: 386, end: 386, class: wrong-operator}
dut_paths: [rtl/**]
checker_paths: [dv/**, examples/**, shared/**, vendor/**]
validated_on: verilator-5.0xx
```

- [ ] `stead bake specs/ibex/ibex-0001.yaml`; check `cases/ibex/ibex-0001/case.yaml` has `stead:`
  filled and `waves/fail.fst` opens with pywellen.
- [ ] Record wall time and folder size in `specs/README.md`. If clone dominates: add
  `git clone --reference-if-able $STEAD_CACHE/<repo>.git` to `_checkout` (one line, one test
  with a local mirror). If `tree/` is large because of `build/`: add `shutil.rmtree(tree/"build")`
  to `_strip_tree` and a fake-repo test asserting `build/` is gone.
- [ ] If `end_time` (streams every signal's steps) is slow on the Ibex FST: change it to stream only
  `[wave[signal]]` and rename to `last_change(wave, signal)`; validate then checks
  `T <= last_change` only. Keep the test.

### Task 4: mutation catalogue and ten cases

**Reuse:** `walker/research/dv_bug_types.md` §3 (functional mismatch), §4 (pipeline/hazard),
§7 (testbench's own bugs, for later `kind: test`).

**Files:** create `specs/README.md` (catalogue table: class, example, which test catches it),
`specs/ibex/ibex-000{2..5}.*`, `specs/scr1/scr1-000{2..5}.*`.

- [ ] Classes, one patch each per repo: wrong operator (done), inverted condition, wrong mux
  select, off-by-one shift/compare, missing register enable (stale value), wrong reset value,
  sign-extension, bit-slice. Pick the compliance test that exercises it (`TESTS.md`/`NOTES.md`).
- [ ] Bake all. Every case must FAIL, not CRASH; drop any patch that hangs (exit 3) and note it in
  `specs/README.md` as "not a STEAD case".

### Task 5: `skills/rtl-debug/SKILL.md` and `stead run-claude`

**Reuse:** the "After the shim" section of `docs/stead-bench-plan.md` for the playbook. Must not
hand out Walker's method (`docs/walk.md` is what not to copy).

**Files:** create `skills/rtl-debug/SKILL.md`, `stead/run_claude.py`; modify `stead/__main__.py`
(one entry in `cmds`); test `tests/test_run_claude.py`.

- [ ] `SKILL.md`: what to open first (README, `logs/fail.log`, STEAD, `waves/fail.*` via pywellen,
  `logs/pass.log`), DUT vs TB rule, never edit the checker, show evidence, answer as the
  submission JSON with `k` ranked lines and an optional patch against `tree/`.
- [ ] `run_claude(case_dir, k) -> Path`: `subprocess.run(["claude", "-p", prompt,
  "--output-format", "json", "--allowedTools", "Read,Grep,Glob,Bash"], cwd=case_dir)`; parse
  `result`, `total_cost_usd`, `duration_ms`; write `results/<case>/claude.json`. Test: a fake
  `claude` on `PATH` (`tests/fixtures/fakeclaude`) printing a canned JSON; assert the submission
  file has `cost.usd` and `lines`.

### Task 6: CRUX adapter `stead run-crux`

**Reuse:** `~/work/crux/design_scr1/user_config.json` (fields `bug.fail_vcd`, `bug.pass_vcds`,
`bug.failing_signal`, `bug.tests`), `python run.py <design>`, `outputs/<run>/run_report.json`.

**Files:** create `stead/run_crux.py`; test `tests/test_run_crux.py` (fixture: a copied
`run_report.json`, asserting the ranked lines come out as `{file, line, confidence}`).

- [ ] CRUX wants VCD: `fst2vcd -f waves/fail.fst -o fail.vcd` (gtkwave) into a temp dir; same for
  pass. `failing_signal` from `case.stead.signal`, tests from `case.test`. Run, parse the report,
  write `results/<case>/crux.json` with `cost` from `token_usage.json`.
- [ ] Walker adapter waits until Walker has a walk CLI (branch `elaborator-v2` has the elaborator
  and waveform only). Input it will take: `tree/`, `waves/fail.fst`, the four STEAD fields.

### Task 7: `stead table`

**Files:** create `stead/table.py`; modify `stead/__main__.py`; test `tests/test_table.py`.

- [ ] Read `results/*/*.json`; per method: cases, hit@1, file@1, patch fixed, mean usd, mean wall_s.
  Print a Markdown table. One function, one test on two hand-written result files.

### Task 8: Docker and `stead ship`

**Reuse:** `hwe-bench_fork/hwe_bench/harness/repos/verilog/ibex/ibex.py` `dockerfile()` and
`_prepare_dev_script()` (Verilator, riscv gcc, micromamba/fusesoc pins); same for `cva6`,
`caliptra`, `rocketchip`.

**Files:** create `docker/ibex.Dockerfile`, `docker/scr1.Dockerfile`, `stead/ship.py`.

- [ ] Dockerfile = HWE's base layers + `COPY repos/<repo>/run.sh`. No clone in the image; the case
  folder brings the tree.
- [ ] `ship(case_dir) -> tar.gz` of the case folder only. Test: tar members exclude `gold`.

### Task 9: HWE overlap cases (`kind: hwe`)

**Reuse:** `henryen/hwe-bench` `ibex.jsonl` (35 records: `base.sha`, `fix_patch`, `tb_script`).

**Files:** create `repos/ibex-hwe/run.sh` (runs the record's `tb_script.sh` in the tree; PASS/FAIL
from its exit code; STEAD only if the tb prints the line), `stead/hwe.py`
(`gold_from_patch(fix_patch) -> Gold`: first hunk's old-side line window; `spec_from_record`).

- [ ] Fix `docs/stead-bench-plan.md` HWE section: HWE bugs are caught by HWE's own unit-level
  Verilator TBs, not by Ibex's tests or cosim; overlap is on the buggy commit, not the test.
- [ ] Test `gold_from_patch` on one real `fix_patch` from the jsonl.

### Task 10: OpenC910

**Reuse:** `~/work/vcds/README.md`: XuanTie gcc at `~/work/xuantie/bin`, Srec2vmem via Docker,
`--no-timing`, `CODE_BASE_PATH`, K4 bug `ct_iu_mult.v:656`. Same write-tracker idea as SCR1.

- [ ] `repos/openc910/run.sh`, first case `openc910-0001` = K4. Last, hardest.

## Verify on the Linux box before Task 3

- riscv-compliance single-test path works without the Makefile (`--raminit` on a prebuilt vmem).
- SCR1 shim's FST switch (plusarg or env) and where `test_info` is written.
- Wall time of one Ibex bake (two Verilator builds) and size of `tree/`.
