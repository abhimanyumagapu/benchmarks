# rocket-chip

Rocket Chip: the Rocket in-order RV64GC core and its SoC generator, written in Chisel (Scala).
The simulator is Verilator over the Verilog that firtool emits from the Scala. You edit Scala; the
build regenerates the Verilog. The wave shows the generated names, which follow the Scala closely.

## Layout, `src/main/scala/`

| path | role |
|---|---|
| `rocket/RocketCore.scala` | the 5-stage pipeline: decode, execute, memory, writeback, bypass network, hazards |
| `rocket/ALU.scala` | the ALU: `io.fn` selects the operation, `io.dw` picks 32-bit (`DW_32`) results on RV64 |
| `rocket/IDecode.scala`, `rocket/Decode.scala`, `rocket/Instructions.scala` | decode tables: opcode → control signals |
| `rocket/Multiplier.scala` | mul/div |
| `rocket/CSR.scala` | CSRs, exceptions, interrupts, privilege |
| `rocket/DCache.scala`, `rocket/HellaCache.scala`, `rocket/NBDcache.scala` | data cache: `io.dmem` requests, `s1_data` is the store data one cycle after the request |
| `rocket/Frontend.scala`, `rocket/ICache.scala`, `rocket/IBuf.scala`, `rocket/RVC.scala`, `rocket/BTB.scala` | fetch, instruction buffer, RVC expansion, prediction |
| `rocket/TLB.scala`, `rocket/PTW.scala`, `rocket/PMP.scala` | address translation and protection |
| `tile/`, `subsystem/`, `tilelink/`, `diplomacy/` | the tile and SoC plumbing; rarely where a functional core bug lives |

Rocket's store data leaves the core on `io.dmem.s1_data.data`; the value is replicated across the
64-bit bus for narrow stores, so a 32-bit wrong word appears twice.

## Testbench and check

The Verilator emulator (`src/main/resources/csrc/emulator.cc`, shimmed) runs a riscv-compliance
ELF; at the end the signature is read out of memory and compared with the reference. The STEAD
line is made from the `+verbose` commit log: the shim prints `STEAD t=<clock>` before each cycle's
commit lines, S-type stores are decoded from the instruction word, and S is the core's dmem store
data (`io_dmem_s1_data_data`) one cycle before the storing instruction commits. E and A are
replicated across both halves of the 64-bit bus, as the hardware does.

Test names are `<isa>/<test>` from riscv-compliance's rv64 sets, for example `rv64i/SUBW`.

## Logs shipped

- `logs/run.log`: the commit log. `STEAD t=<clock>` marks the clock count, then one line per
  committed instruction: `C0: <mcycle> [1] pc=[<pc>] W[r<rd>=<value>][<wen>] R[r<rs1>=<v>]
  R[r<rs2>=<v>] inst=[<word>] DASM(<word>)`. mcycle pauses on stalls; the `STEAD t` clock does not.
- `logs/sig.raw`: the signature the emulator read out, 32 hex chars per line, most significant
  word first.
- `logs/fail.log`: the verdict line.

## Wave

Hierarchy: `TOP.TestHarness.ldut.tile_prci_domain.element_reset_domain_rockettile.` then `core`
(Rocket: `core.alu`, `core.div`, `core.csr`, `core.ibuf`, `core.bpu`), `dcache`, `frontend`
(`frontend.icache`, `frontend.tlb`, `frontend.btb`), `fpuOpt`. Chisel names: `io_<bundle>_<field>`
for ports (`io_dmem_s1_data_data`, `io_imem_resp_bits_pc`), register names as in the Scala
(`ex_reg_pc`, `mem_reg_wdata`, `wb_reg_wdata`), `_T_n`/`_GEN_n` for anonymous intermediates.
Dump time = 2 × clock (clock low) and 2 × clock + 1 (clock high); so T / 2 is the `STEAD t` value
of the cycle, and the storing instruction's commit line is the next cycle's.

From S at T: the store commits at clock T/2 + 1; its `R[r rs2]` operand is the wrong value; the
`W[r rd]` line that produced that register is the instruction whose result is wrong; then its
operands, the ALU function, and `dw` at that clock in `core`.

## Tools

- `python tools/commits.py logs/run.log --time <T> [--window 8]`: commit lines around a dump time.
- `python tools/commits.py logs/run.log --reg 14`: every write to a register.
- `python tools/commits.py logs/run.log --pc 0x<addr>`: every commit of a PC.

## Quirks

- The Scala is the source of truth; the Verilog under `build/` is generated and not shipped. A
  fix is a Scala edit; the sim tool regenerates and rebuilds (about a minute).
- Rocket is 64-bit: `SUBW`, `ADDW` and friends sign-extend a 32-bit result, selected by `io.dw`.
- Bypass: an operand may come from `mem_reg_wdata` or `wb_reg_wdata` rather than the register file.
- The FPU (`fpuOpt`) and the accelerator interface are present but idle for integer tests.
