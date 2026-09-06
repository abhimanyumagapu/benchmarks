# cva6

OpenHW CVA6: a 6-stage in-order RV64GC core, SystemVerilog, run here as `cv64a6_imafdc_sv39` under
Verilator with Spike in tandem: every retired instruction is compared with the reference model.

## Layout, `core/`

| file | role |
|---|---|
| `cva6.sv` | the core: instantiates every stage below |
| `frontend/` (`i_frontend`) | fetch, `instr_realign.sv`, `instr_queue`, branch prediction (`bht`, `btb`, `ras`) |
| `id_stage.sv`, `decoder.sv`, `compressed_decoder.sv` | decode into a scoreboard entry: `fu`, `op`, `rs1`, `rs2`, `rd`, immediate |
| `issue_stage.sv`, `scoreboard.sv`, `issue_read_operands.sv` | in-order issue, operand read, forwarding from the scoreboard, write-back to the register file |
| `ex_stage.sv` | execute: `alu_wrapper_i` (`alu.sv`), `branch_unit_i`, `csr_buffer_i`, `i_mult` (`mult.sv`, `multiplier.sv`, `serdiv.sv`), `lsu_i` (`load_store_unit.sv`, `load_unit.sv`, `store_unit.sv`, `store_buffer.sv`), the FPU |
| `commit_stage.sv` | commit: writes the register file, resolves exceptions, orders stores |
| `csr_regfile.sv` | CSRs, privilege, traps |
| `controller.sv` | flush and halt control |
| `cache_subsystem/` (`gen_cache_wt.i_cache_subsystem`) | write-through caches and the AXI adapter |
| `cva6_mmu/`, `pmp/` | translation and protection |
| `cva6_rvfi.sv`, `cva6_rvfi_probes.sv` | the RVFI probes the tandem uses (testbench side) |

The ALU result is `ex_stage_i.alu_wrapper_i` → `alu.sv` `result_o`, a `unique case (fu_data_i.operation)`
over `ariane_pkg` operation codes. Results reach the register file through the scoreboard at commit;
`wdata_commit_id` at the core root is the value about to be written.

## Testbench and check

`corev_apu/tb/`: `ariane_testharness` with `i_ariane.i_cva6`, memory, peripherals, and
`common/spike.sv` (shimmed) which compares each committed instruction's `rd` write with Spike. The
test is a riscv-tests `p` test compiled on the spot; `*** SUCCESS ***` means `tohost` was written
with 0. The STEAD line is printed by the shim on the first `rd` mismatch: S is
`i_cva6.wdata_commit_id`, T is two cycles before the compare (the RVFI value is registered twice on
its way), E is the register file value with Spike's `rd` in the mismatching lane.

Test names are riscv-tests p tests, `<set>-p-<name>`: `rv64ui-p-xor`, `rv64um-p-mulw`,
`rv64ua-p-amoadd_w`, and so on.

## Logs shipped

- `logs/fail.log`: the simulator's own output, about 50 lines. The Spike banner, then only the
  instructions the tandem disagreed on: a `CSR ... Mismatch` or `UVM_ERROR` line with `[REF]` and
  `[CORE]` values, each with its RVFI line
  `<ns> | RVFI | <hart> | <trap> | <pc> | <insn> | <priv> | x<rd> | <rd_wdata> | x<rs1> | <rs1_rdata>
  | x<rs2> | <rs2_rdata> | <disasm>`, and last the STEAD `FAIL` or `NOTE` line. It is not the whole
  trace: for that use the three below.
- `logs/trace_hart_0.dasm`: every retired instruction, `<cycle> <pc> <priv> (<word>) DASM(<word>)`.
  The cycle column is the tandem's ns, so dump time is twice it.
- `logs/trace_rvfi_hart_00.dasm`: the same retirements with their register writes,
  `<n> <pc> (<word>) x <rd> 0x<value>`.
- `logs/tandem.log`: Spike's own commit log, `core 0: <pc> (<word>) <disasm>` and its register
  writes. This is the reference: what the instruction should have produced.
- `logs/iti.traces`, `logs/encaps.traces`: the instruction-trace encoder's output; rarely useful.
- `logs/cc.log`: the test's compile log.

## Wave

Hierarchy: `TOP.ariane_testharness.i_ariane.i_cva6.` then the stage instances above; signals at the
core root include `wdata_commit_id`, `waddr_commit_id`, `we_gpr_commit_id`, `commit_instr_id_commit`.
Dump time is 2 × cycle on clock low and 2 × cycle + 1 on clock high; the tandem log's `ns` column
is cycle × 1 ns. So T / 2 is the cycle, and the RVFI line for the compare is at about T / 2 + 2 ns.

From S at T: the RVFI line two cycles later names the instruction, its operands and Spike's
expected `rd`; the instruction's `fu` and `operation` are in the scoreboard entry
(`issue_stage_i.i_scoreboard`); its result is at `ex_stage_i.<unit>` one cycle earlier; its
operands come from `issue_stage_i.i_issue_read_operands`, possibly forwarded.

## Tools

- `python tools/rvfi.py logs/fail.log --mismatch`: the mismatch lines with REF and CORE values.
- `python tools/rvfi.py logs/fail.log --time <T> [--window 8]`: the mismatching RVFI lines around a
  dump time. Each mismatch appears twice, the reference then the core; the second is the DUT's value.
- `python tools/rvfi.py logs/trace_rvfi_hart_00.dasm --reg 14`: over the full trace instead, for
  every write to x14.

## Quirks

- Spike is the oracle: a `[REF]`/`[CORE]` pair on a mismatch line is E and A in the ISA's terms.
- The `p` tests run from `0x80000000` in machine mode with no MMU activity; MMU code is inactive.
- Rebuilding after an edit takes about 4 minutes; use the simulator to confirm, not to explore.
- `rd = x0` writes are excluded from the compare; a bug that only corrupts x0 is invisible to it.
