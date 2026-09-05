#!/bin/bash
# rocket-chip recipe. Contract: see stead/recipe.py.
#   run.sh build <tree>                                          mill: Verilator emulator, DefaultConfig (FST via shim.patch)
#   run.sh run   <tree> <rv64i/SUBW> <out> [--dump=on|off]       one riscv-compliance test from $STEAD_TOOLS/riscv-compliance
#   run.sh suite <tree> <out> [<regex>]                          the 13 rv64i/rv64im compliance tests
# stead_line.py joins the signature diff with the +verbose commit log the shimmed emulator.cc stamps.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../env.sh"
export SPIKE_ROOT=$STEAD_TOOLS/spike RISCV=$STEAD_TOOLS/riscv-gcc _JAVA_OPTIONS=-Xmx3g MILL_VERSION=0.11.12
COMP=$STEAD_TOOLS/riscv-compliance
verb=$1; tree=$(cd "$2" && pwd)
EMU=$tree/out/emulator/freechips.rocketchip.system.TestHarness/freechips.rocketchip.system.DefaultConfig/verilator/elf.dest/emulator
case $verb in
  build)
    cd "$tree" || exit 2
    rm -rf out/emulator/*/*/verilator            # never trust a copied emulator: mill misses RTL/emulator.cc edits
    mill -i "emulator[freechips.rocketchip.system.TestHarness,freechips.rocketchip.system.DefaultConfig].elf" > build.log 2>&1
    [ -x "$EMU" ] || { grep -m3 -i "error" build.log; exit 2; }
    exit 0 ;;
  run)
    isa=${3%%/*}; test=${3#*/}; out=$(mkdir -p "$4" && cd "$4" && pwd); dump=${5:---dump=on}
    elf=$COMP/work/$isa/$test.elf; ref=$COMP/riscv-test-suite/$isa/references/$test.reference_output
    [ -x "$EMU" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    [ -f "$elf" ] || { echo "no prebuilt test: $elf (run the compliance make once)" > "$out/sim.log"; exit 2; }
    v=""; [ "$dump" = --dump=on ] && v="-v $out/dump.fst"
    ( cd "$out" && "$EMU" $v +verbose +signature=sig.raw "$elf" > run.log 2>&1 )
    [ -s "$out/sig.raw" ] || { cp "$out/run.log" "$out/sim.log"; exit 3; }
    python3 "$HERE/stead_line.py" "$test" "$ref" "$out/sig.raw" "$elf" "$out/run.log" "$out/dump.fst" > "$out/sim.log" || exit 3   # the joiner crashed: a crash, not a verdict
    grep -q "^PASS " "$out/sim.log" && exit 0
    exit 1 ;;
  suite)
    for isa in rv64i rv64im; do for r in "$COMP/riscv-test-suite/$isa/references"/*.reference_output; do echo "$isa/$(basename "$r" .reference_output)"; done; done | stead_suite "$0" "$tree" "$(mkdir -p "$3" && cd "$3" && pwd)" "${4:-.}" ;;
  *) echo "usage: run.sh build <tree> | run <tree> <test> <out> [--dump=on|off] | suite <tree> <out> [<regex>]" >&2; exit 64 ;;
esac
