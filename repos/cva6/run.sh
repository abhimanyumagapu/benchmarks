#!/bin/bash
# cva6 recipe. Contract: see stead/recipe.py.
#   run.sh build <tree>                                      make verilate (cv64a6_imafdc_sv39, Spike tandem, FST)
#   run.sh run   <tree> <rv64ui-p-xor> <out> [--dump=on|off] compile the riscv-tests p-test, run it in tandem
#   run.sh suite <tree> <out> [<regex>]                      the 124 rv64 p-tests (~25 s each); pass a regex for a subset
# The shimmed spike.sv (shim.patch) prints the STEAD FAIL line on the first rd mismatch.
set -u
. "$(dirname "$0")/../env.sh"
export RISCV=$STEAD_TOOLS/riscv-gcc VERILATOR_INSTALL_DIR=$STEAD_TOOLS/verilator NUM_JOBS=8 SPIKE_TANDEM=1
ulimit -s unlimited          # the tandem's RVFI structs overflow the default 8 MB stack
verb=$1; tree=$(cd "$2" && pwd)
SIM=$tree/work-ver/Variane_testharness
case $verb in
  build)
    cd "$tree" || exit 2
    # once, in the image build: tools/spike for the tandem and the pinned riscv-tests clone (both gitignored upstream)
    bash verif/regress/install-riscv-tests.sh > tests.log 2>&1 || { tail -3 tests.log; exit 2; }
    bash verif/regress/install-spike.sh > spike.log 2>&1 || { tail -3 spike.log; exit 2; }
    make verilate target=cv64a6_imafdc_sv39 TRACE_COMPACT=1 > build.log 2>&1
    [ -x "$SIM" ] || { grep -m3 -E "%Error|error:" build.log; exit 2; }
    exit 0 ;;
  run)
    test=$3; out=$(mkdir -p "$4" && cd "$4" && pwd); dump=${5:---dump=on}
    [ -x "$SIM" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    dir=${test%%-p-*}; name=${test##*-p-}; T=$tree/verif/tests/riscv-tests/isa
    src=$T/$dir/$name.S; elf=$out/$test.elf
    [ -f "$src" ] || { echo "no such test: $src" > "$out/sim.log"; exit 2; }
    "$RISCV/bin/riscv-none-elf-gcc" -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles -march=rv64gc -mabi=lp64d \
      -I"$T/macros/scalar" -I"$T/../env/p" -I"$T/../riscv-target/spike" -I"$tree/verif/sim/dv/user_extension" \
      -T"$tree/config/gen_from_riscv_config/linker/link.ld" "$src" -o "$elf" > "$out/cc.log" 2>&1 || { cat "$out/cc.log" > "$out/sim.log"; exit 2; }
    tohost=$(riscv64-unknown-elf-nm -B "$elf" | grep -w tohost | cut -d' ' -f1)
    plus=""; [ "$dump" = --dump=on ] && plus="+dump_file=$out/dump.fst"
    ( cd "$out" && "$SIM" $plus "$elf" +debug_disable=1 +UVM_VERBOSITY=UVM_NONE ++"$elf" +elf_file="$elf" \
        +core_name=cv64a6_imafdc_sv39 +tohost_addr="$tohost" > sim.log 2>&1 )
    grep -qE "^(FAIL|NOTE) " "$out/sim.log" && exit 1
    grep -q "SUCCESS" "$out/sim.log" && exit 0
    grep -q "FAILED" "$out/sim.log" && exit 1
    exit 3 ;;
  suite)
    grep -o "riscv-tests/isa/rv64[a-z]*/[a-z0-9_]*\.S" "$tree/verif/tests/testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml" | while read -r s; do echo "$(basename "$(dirname "$s")")-p-$(basename "$s" .S)"; done | stead_suite "$0" "$tree" "$(mkdir -p "$3" && cd "$3" && pwd)" "${4:-.}" ;;
  *) echo "usage: run.sh build <tree> | run <tree> <test> <out> [--dump=on|off] | suite <tree> <out> [<regex>]" >&2; exit 64 ;;
esac
