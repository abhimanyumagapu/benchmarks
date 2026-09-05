#!/bin/bash
# ibex recipe. Contract: see stead/recipe.py.
#   run.sh build <tree>                                        fusesoc Verilator build of ibex_riscv_compliance
#   run.sh run   <tree> <isa>/<test> <out> [--dump=on|off]     one riscv-compliance test, e.g. rv32i/I-XOR-01
#   run.sh suite <tree> <out> [<regex>]                        the 88 compliance tests minus the four known clean-tree fails
# No repo edit: the STEAD line is made afterwards by stead_line.py from the signature diff and the
# RVFI trace the sim writes. Test ELFs come prebuilt from $STEAD_TOOLS/riscv-compliance/work/<isa>/.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../env.sh"
export PATH=$STEAD_TOOLS/venvs/ibex/bin:$PATH
COMP=$STEAD_TOOLS/riscv-compliance
KNOWN="I-EBREAK-01 I-ECALL-01 I-MISALIGN_JMP-01 I-MISALIGN_LDST-01"   # trap tests the 2019 suite and ibex disagree on
verb=$1; tree=$(cd "$2" && pwd)
SIM=$tree/build/lowrisc_ibex_ibex_riscv_compliance_0.1/sim-verilator/Vibex_riscv_compliance
case $verb in
  build)
    cd "$tree" || exit 2
    OPTS=$(python3 util/ibex_config.py small fusesoc_opts | tr ' ' '\n' | grep -v '^--BaseIsa=' | tr '\n' ' ')
    fusesoc --cores-root=. run --target=sim --setup --build lowrisc:ibex:ibex_riscv_compliance $OPTS \
      --verilator_options="-Wno-UNOPTFLAT" > build.log 2>&1
    [ -x "$SIM" ] || { grep -m3 -E "%Error|error:" build.log; exit 2; }
    exit 0 ;;
  run)
    isa=${3%%/*}; test=${3#*/}; out=$(mkdir -p "$4" && cd "$4" && pwd); dump=${5:---dump=on}
    vmem=$COMP/work/$isa/$test.elf.vmem; ref=$COMP/riscv-test-suite/$isa/references/$test.reference_output
    [ -x "$SIM" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    [ -f "$vmem" ] || { echo "no prebuilt test: $vmem (run the compliance make once)" > "$out/sim.log"; exit 2; }
    trace=""; [ "$dump" = --dump=on ] && trace="--trace=$out/dump.fst"
    ( cd "$out" && "$SIM" --raminit="$vmem" $trace --term-after-cycles=100000 > stdout 2>&1; mv -f trace_core_00000000.log trace.log 2>/dev/null )
    grep -q "^SIGNATURE: " "$out/stdout" || { cp "$out/stdout" "$out/sim.log"; exit 3; }
    python3 "$HERE/stead_line.py" "$test" "$ref" "$out/stdout" "$out/trace.log" "$out/dump.fst" > "$out/sim.log" || exit 3   # the joiner crashed: a crash, not a verdict
    grep -q "^PASS " "$out/sim.log" && exit 0
    exit 1 ;;
  suite)
    for isa in rv32i rv32im rv32imc rv32Zicsr rv32Zifencei; do for r in "$COMP/riscv-test-suite/$isa/references"/*.reference_output; do t=$(basename "$r" .reference_output); case " $KNOWN " in *" $t "*) ;; *) echo "$isa/$t";; esac; done; done | stead_suite "$0" "$tree" "$(mkdir -p "$3" && cd "$3" && pwd)" "${4:-.}" ;;
  *) echo "usage: run.sh build <tree> | run <tree> <test> <out> [--dump=on|off] | suite <tree> <out> [<regex>]" >&2; exit 64 ;;
esac
