#!/bin/bash
# scr1 recipe. Contract: see stead/recipe.py.
#   run.sh build <tree>                                   builds the Verilator TB (AXI, FST) and every test hex
#   run.sh run   <tree> <test.hex> <out> [--dump=on|off]  runs one test; sim.log + dump.fst in <out>
#   run.sh suite <tree> <out> [<regex>]                    every hex in the build's test_info (221)
# The TB (shimmed, see shim.patch) prints the STEAD FAIL line itself and a "Summary: n/1 tests passed".
set -u
. "$(dirname "$0")/../env.sh"
verb=$1; tree=$(cd "$2" && pwd)
B=$tree/build/verilator_wf_AXI_MAX_imc_IPIC_1_TCM_1_VIRQ_1_TRACE_1
SIM=$B/verilator/Vscr1_top_tb_axi
case $verb in
  build)
    # run_verilator_wf is the only target that builds both the sim and the test hexes; it also runs
    # the suite once (~1 min), which we ignore.
    make -C "$tree" BUS=AXI TRACE=1 run_verilator_wf TARGETS="riscv_isa riscv_compliance riscv_arch isr_sample" \
      > "$tree/build.log" 2>&1
    [ -x "$SIM" ] || { grep -m3 -E "%Error|error:" "$tree/build.log"; exit 2; }
    exit 0 ;;
  run)
    test=$3; out=$(mkdir -p "$4" && cd "$4" && pwd); dump=${5:---dump=on}
    [ -x "$SIM" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    [ -f "$B/$test" ] || { echo "no such test hex: $test" > "$out/sim.log"; exit 2; }
    echo "$test" > "$out/test_info"
    plus=""; [ "$dump" = --dump=on ] && plus="+dump_file=$out/dump.fst"
    ( cd "$B" && ./verilator/Vscr1_top_tb_axi +test_info="$out/test_info" +test_results="$out/results.txt" $plus ) \
      2>&1 | sed 's/\x1b\[[0-9;]*m//g' > "$out/sim.log"
    grep -q "^# Summary: " "$out/sim.log" || exit 3          # no summary: the sim died or hung
    grep -q "^# Summary: 1/1" "$out/sim.log" && exit 0
    exit 1 ;;
  suite)
    cat "$B/test_info" | stead_suite "$0" "$tree" "$(mkdir -p "$3" && cd "$3" && pwd)" "${4:-.}" ;;
  *) echo "usage: run.sh build <tree> | run <tree> <test> <out> [--dump=on|off] | suite <tree> <out> [<regex>]" >&2; exit 64 ;;
esac
