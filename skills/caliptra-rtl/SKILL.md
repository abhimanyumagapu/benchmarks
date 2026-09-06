# caliptra-rtl

Caliptra: a root-of-trust subsystem, SystemVerilog. A VeoR EL2 RISC-V core runs firmware that
drives cryptographic accelerators and vaults over an AHB-lite bus; the test is a firmware program
whose own checks print to the console. Bugs here live in the accelerator and interface blocks, not
in a CPU pipeline.

## Layout, `src/<block>/rtl/`

| block | role |
|---|---|
| `sha256`, `sha512`, `sha512_masked`, `sha3`, `kmac` | hash engines: a controller with the register interface (`*_ctrl.sv` or `<block>.sv`) around a core (`*_core.v`) with its message schedule and constants |
| `hmac`, `hmac_drbg` | HMAC and the DRBG built on it |
| `aes` | AES engine (GCM, key-vault reads) |
| `ecc`, `mldsa`, `abr` | ECC, ML-DSA and the shared arithmetic |
| `keyvault`, `pcrvault`, `datavault` | the vaults: key slots, PCRs, data registers with lock and clear rules |
| `doe`, `csrng`, `entropy_src`, `edn`, `entropy_combiner` | deobfuscation and entropy |
| `soc_ifc` | the SoC interface: mailbox, fuses, boot FSM, registers the SoC and firmware both see |
| `ahb_lite_bus`, `axi`, `caliptra_tlul` | the fabric: address decode, one AHB-lite responder per block |
| `integration/rtl/caliptra_top.sv` | wires the core, the bus and every block together |
| `riscv_core` | the VeoR EL2 core (vendored; treat as correct) |

Every accelerator has the same shape: the firmware writes control and data registers over AHB,
the block's controller starts the core, the result lands in registers the firmware reads back.
The register map for each block is generated from its `rdl`; the `hwif_in`/`hwif_out` structs in
the controller connect registers to the datapath.

## Testbench and check

`src/integration/tb/caliptra_top_tb.sv` instantiates `caliptra_top_dut`, boots the firmware from
`src/integration/test_suites/<test>/` (C, compiled on the spot into ROM and ICCM), and watches the
console. The firmware prints `Expected data: 0x..` and `Actual   data: 0x..` when a check fails
and ends with `TESTCASE PASSED` or `TESTCASE FAILED`. The STEAD line is made afterwards: E and A
are the firmware's own expected and actual prints, S is `initiator_inst.hrdata`, the AHB-lite
read-data bus into the core, T is the dump time of the last 32-bit AHB read that returned A
before the print, found in the bus log.

Tests are the L0 smoke tests, `smoke_test_<block>` and a few others: `smoke_test_sha256`,
`smoke_test_hmac`, `smoke_test_kv`, `smoke_test_mbox`, `iccm_lock`, `hello_world_iccm`. One test
takes about three minutes.

## Logs shipped

- `logs/console.log`: everything the firmware printed, including the expected and actual values
  and which register or step failed.
- `logs/lsu_master_ahb_trace.log`: every AHB-lite transfer the core made: `cycle : 0xaddr hsize
  htrans hwrite 0xhrdata_hi_lo 0xhwdata_hi_lo hready hresp`. A read of a result register shows
  what the block returned; a write shows what the firmware configured.
- `logs/verilator_sim.log`, `logs/run.log`: the simulator's log and the build/run output.
- `logs/fail.log`: the verdict line.

## Wave

Hierarchy: `TOP.caliptra_top_tb.caliptra_top_dut.` then the block instances, whose names do not
follow one rule: `sha256`, `sha512`, `sha3`, `hmac`, `doe`, `csrng`, `entropy_src1`, `key_vault1`,
`pcr_vault1`, `data_vault1`, `ecc_top1`, `soc_ifc_top1`, `aes_inst`, `abr_inst`, and the core
`rvtop`. The bus is `ahb_lite_bus_i` with `responder_inst[0..18]`, and `initiator_inst` carries the
AHB signals `haddr`, `hwdata`, `hrdata`, `hwrite`, `htrans`, `hready`. Dump time of clock edge n is 100 × n + 50 (100 ps steps, the clock toggles
every 50), so the bus log's cycle n is at T = 100n + 50.

From S at T: the bus log line at cycle (T - 50) / 100 gives the address read (AHB is pipelined, so
that cycle is the data phase and the address went out the cycle before; `tools/bus.py` pairs them); the block's register map
says which result register that is; inside the block, the value came from `hwif_in.<REG>.next`
in the controller, fed by the core's output; walk the core's datapath back from the cycle it
finished (`ready`/`valid` in the controller) to the round or step whose value is off.

## Tools

- `python tools/bus.py logs/lsu_master_ahb_trace.log --time <T> [--window 12]`: transfers around a
  dump time.
- `python tools/bus.py logs/lsu_master_ahb_trace.log --addr 0x<addr>`: every access to an address.
- `python tools/bus.py logs/lsu_master_ahb_trace.log --data 0x<value>`: every transfer carrying a value.
- `python tools/bus.py ... --writes`: writes only (the firmware's configuration and inputs).

## Quirks

- The firmware compares against known-answer vectors; E is the standard's value, so an A off by
  a bit in one word usually points at the last transformation of that word in the datapath.
- A 32-bit result is read one dword at a time; the wrong dword's index tells you which lane.
- Vault and lock rules (`keyvault`, `pcrvault`, `soc_ifc`) fail as a wrong status or a zeroed
  value rather than a wrong number; check the lock and clear conditions at the write.
- Rebuilding takes about five minutes with the warm cache; one simulator run about three. Confirm
  once.
