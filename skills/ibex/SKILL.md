# ibex

lowRISC Ibex: a 2-stage (optionally 3-stage) in-order RV32 core, SystemVerilog. This case runs the
`small` configuration (RV32IMC, no branch predictor, fast multiplier off) in the riscv-compliance
testbench under Verilator.

## Layout, `rtl/`

| file | role |
|---|---|
| `ibex_top.sv`, `ibex_core.sv` | wrapper and core; the pipeline is instantiated in `ibex_core` |
| `ibex_if_stage.sv`, `ibex_prefetch_buffer.sv`, `ibex_fetch_fifo.sv`, `ibex_compressed_decoder.sv` | fetch: PC, prefetch, RVC expansion |
| `ibex_id_stage.sv`, `ibex_decoder.sv`, `ibex_controller.sv` | decode, operand select, the controller (exceptions, stalls, jumps) |
| `ibex_ex_block.sv`, `ibex_alu.sv`, `ibex_multdiv_fast.sv`, `ibex_multdiv_slow.sv` | execute: ALU (also branch compare, bit-manipulation), mul/div |
| `ibex_load_store_unit.sv` | LSU: address, byte lanes, misaligned split, sign extension of loads |
| `ibex_wb_stage.sv`, `ibex_register_file_ff.sv` | writeback and the register file (`gen_regfile_ff`) |
| `ibex_cs_registers.sv`, `ibex_csr.sv`, `ibex_counter.sv`, `ibex_pmp.sv` | CSRs, counters, PMP |
| `ibex_tracer.sv`, `ibex_top_tracing.sv` | the RVFI tracer (testbench side of the core, not a bug site) |

The ALU result is `ibex_ex_block` → `alu_i.result_o`; the ID stage picks operands and the
controller decides stalls. Loads and stores go through `load_store_unit_i` with `data_wdata_o`
built from the register value and the byte offset.

## Testbench and check

`dv/riscv_compliance/`: `ibex_riscv_compliance` instantiates `u_top` (the traced core) and `u_ram`.
A test is a prebuilt riscv-compliance ELF; at the end the core writes its signature to memory and
the testbench prints it as `SIGNATURE:` lines. The check compares those lines with the reference
signature; the first wrong word is the fail. The STEAD line is made afterwards from the RVFI
trace: S is `rvfi_mem_wdata`, the store data bus, at the time of the earliest store that last
wrote a wrong signature byte. E is the reference word rebuilt onto the actual bus value byte by
byte, so E and A differ only in the wrong bytes.

Test names are `<isa>/<test>`: `rv32i`, `rv32im`, `rv32imc`, `rv32Zicsr`, `rv32Zifencei`, for
example `rv32i/I-XOR-01`. Four trap tests are excluded as known clean-tree disagreements:
`I-EBREAK-01 I-ECALL-01 I-MISALIGN_JMP-01 I-MISALIGN_LDST-01`.

## Logs shipped

- `logs/trace.log`: the RVFI instruction trace, tab separated: `Time  Cycle  PC  Insn  Decoded
  instruction  Register and memory contents`. `x10=0x..` is a write, `x10:0x..` a read,
  `PA:0x.. store:0x..` and `load:0x..` are memory accesses. Time is the dump time.
- `logs/stdout`: the simulator's stdout with the `SIGNATURE:` lines.
- `logs/fail.log`: the verdict line.

## Wave

Hierarchy: `TOP.ibex_riscv_compliance.u_top.u_ibex_top.` then `u_ibex_core.<stage>_i`:
`if_stage_i`, `id_stage_i`, `ex_block_i` (with `alu_i` inside), `load_store_unit_i`,
`wb_stage_i`, `cs_registers_i`; the register file is `gen_regfile_ff.register_file_i`. RVFI
signals (`rvfi_pc_rdata`, `rvfi_insn`, `rvfi_rd_wdata`, `rvfi_mem_addr`, `rvfi_mem_wdata`) sit at
the `u_ibex_top` level and show each retired instruction one cycle after it retires. Dump time
equals the trace's Time column; the clock is 2 time units, so cycle ≈ (Time − 8) / 2.

From S at T, the instruction that stored the wrong value is the trace line with `store:` at Time
T; its data register was written by an earlier line, `x<n>=`; find that line and you have the
instruction whose result is wrong, then follow its operands into `ex_block_i` at that Time.

## Tools

- `python tools/trace.py logs/trace.log --time <T> [--window 12]`: the trace around a dump time.
- `python tools/trace.py logs/trace.log --reg x14`: every write to a register.
- `python tools/trace.py logs/trace.log --store 0x<addr>`: every store to an address.

## Quirks

- The core tree here is the CHERIoT-flavoured ibex (`g_cheriot_ex`, `ibex_trvk`); the compliance
  config runs plain RV32IMC, so the CHERI paths are inactive. Bugs land in the ordinary files.
- Misaligned accesses are split in the LSU into two transfers; the trace shows one instruction.
- The compliance signature is written with `sw`; a byte-wide bug shows up as one wrong byte in a
  whole word.
