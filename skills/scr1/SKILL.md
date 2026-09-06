# scr1

Syntacore SCR1: a small in-order RV32IMC core with a 2 to 4 stage pipeline, SystemVerilog. The
testbench here is the AXI top-level with the tightly coupled memory, run under Verilator.

## Layout, `src/core/`

| file | role |
|---|---|
| `scr1_core_top.sv` | the core: pipeline, debug, clock and reset control |
| `pipeline/scr1_pipe_top.sv` | wires the pipeline stages |
| `pipeline/scr1_pipe_ifu.sv` | instruction fetch unit and its queue |
| `pipeline/scr1_pipe_idu.sv` | decoder: instruction → `idu2exu_cmd` (ALU command, operands, immediates, LSU command) |
| `pipeline/scr1_pipe_exu.sv` | execute: operand selection, jump and branch resolution, exceptions, writeback of `exu2mprf_rd_data` |
| `pipeline/scr1_pipe_ialu.sv` | the integer ALU: `SCR1_IALU_CMD_*` cases for add, sub, logic, shifts, compares, plus mul/div |
| `pipeline/scr1_pipe_lsu.sv` | loads and stores: address, size, sign extension, misalignment |
| `pipeline/scr1_pipe_mprf.sv` | the register file |
| `pipeline/scr1_pipe_csr.sv`, `scr1_pipe_ipic.sv`, `scr1_pipe_hdu.sv`, `scr1_pipe_tdu.sv` | CSRs, interrupt controller, debug and trigger units |
| `pipeline/scr1_tracelog.sv` | the tracer (testbench side) |
| `scr1_tcm.sv`, `scr1_dmem_router.sv`, `scr1_imem_router.sv`, `scr1_timer.sv` | memory and routing outside the pipeline (in `src/top/` for the AXI wrapper) |

The ALU result is `scr1_pipe_ialu` `ialu2exu_main_res_o` in an `always_comb` case over
`exu2ialu_cmd_i`; the EXU muxes it with the LSU and CSR data into the register write.

## Testbench and check

`src/tb/scr1_top_tb_axi.sv` with `scr1_top_tb_runtests.sv` (shimmed) loads one test hex into
memory, runs it, and reads the result: the test writes a pass or fail word, and for the arch and
compliance tests a signature. The shim tracks every data-memory write on the AXI bus and prints
the STEAD line on the first wrong signature word: S is `i_top.io_axi_dmem_wdata`, the data write
bus, T is when the wrong word was written, E the reference word.

Test names are the hex files of the built test set: riscv-tests `<name>.hex` (`add.hex`, `bltu.hex`),
compliance `compliance_<NAME>.hex` (`compliance_I-BLTU-01.hex`), arch tests `arch_<name>.hex`
(`arch_xor-01.hex`), and `isr_sample.hex`. The whole set of 221 runs in about two minutes.

## Logs shipped

- `logs/fail.log`: the testbench's log: the test name, the STEAD line, `Test failed`, and the
  summary.
- `logs/results.txt`: the per-test result line the testbench writes; `logs/test_info` names the test.

## Wave

Hierarchy: `TOP.scr1_top_tb_axi.i_top.` then `i_core_top.i_pipe_top.<unit>`: `i_pipe_ifu`,
`i_pipe_idu`, `i_pipe_exu`, `i_pipe_mprf`, `i_pipe_csr`, `i_pipe_hdu`, `i_pipe_tdu`, `i_pipe_ipic`,
and the tracer `i_tracelog`. The IALU and the LSU are inside the EXU: `i_pipe_exu.i_ialu` and
`i_pipe_exu.i_lsu` (there is no `i_pipe_lsu` in the wave, though the source file is
`pipeline/scr1_pipe_lsu.sv`). The stage-to-stage buses are signals on `i_pipe_top` itself:
`idu2exu_cmd`, `exu2mprf_rd_data`, `mprf2exu_rs1_data`, `lsu2tdu_d_mon`. The AXI
memories are `i_dmem_axi` and `i_imem_axi`, the TCM is `i_tcm`. Dump time is in the testbench's
time units with a 10-unit clock period; T is the write on the bus.

From S at T: the write on `io_axi_dmem_wdata` came from a store; in `i_pipe_exu.i_lsu` the data is
`exu2lsu_...` at the cycle before, which is a register value; in `i_pipe_mprf` find the write of
that register (`exu2mprf_rd_data` with `exu2mprf_w_req`), which is the result of the instruction
under suspicion; then `i_pipe_exu` and `i_ialu` at that cycle for the operation and operands.

## Tools

- `python tools/dmem.py waves/fail.fst --time <T> [--window 200]`: the data-memory writes and
  register-file writes around a dump time, from the wave.
- `python tools/dmem.py waves/fail.fst --value 0x<hex>`: every time a bus or register write
  carried a value.

## Quirks

- The core tracer (`i_tracelog`) exists in the wave but its file is not shipped; the register file
  write port (`i_pipe_mprf`) is the closest thing to a commit trace.
- Compare instructions (`SLT`, `SLTU`, branches) share the IALU's subtractor and its flags; a bug in
  the flags shows up in branches first.
- The arch tests store a signature per instruction; the wrong word's index in the signature tells
  you which test vector failed, and the test source in the riscv-arch suite says which operands.
