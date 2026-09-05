#!/bin/bash
# Fake repo runner implementing the STEAD run.sh contract, for harness tests. Runs in the
# stead-fake image (Dockerfile next to it) exactly like a core's run.sh runs in its image.
#   run.sh build <tree>                                  exit 0 ok, 2 build error
#   run.sh run   <tree> <test> <out_dir> [--dump=on|off] exit 0 PASS, 1 FAIL, 2 build error, 3 crash
#   run.sh suite <tree> <out_dir> [<regex>]              exit 0 ran, 2 build error
# The "DUT" is <tree>/rtl/alu.sv. Tokens in it drive the outcome: BUG fails xor_test and sub_test,
# XORBUG fails xor_test only (add_test always passes), HANG crashes, SYNTAX_ERROR breaks the build, LIE makes
# the FAIL line claim a value the dump does not show.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
verb=$1; tree=$2
case $verb in
  build)
    [ -f "$tree/rtl/alu.sv" ] || exit 2
    grep -q SYNTAX_ERROR "$tree/rtl/alu.sv" && exit 2
    mkdir -p "$tree/build" && echo "built from: $(cat "$tree/rtl/alu.sv")" > "$tree/build/ok"; exit 0 ;;
  run)
    test=$3; out=$4; dump=${5:---dump=on}; mkdir -p "$out"
    [ -f "$tree/build/ok" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    grep -q HANG "$tree/rtl/alu.sv" && { echo "timeout" > "$out/sim.log"; exit 3; }
    [ "$dump" = --dump=on ] && cp "$HERE/../mini.vcd" "$out/dump.vcd"
    actual=0xfffff810; grep -q LIE "$tree/rtl/alu.sv" && actual=0x00001234
    if { [ "$test" = sub_test ] && grep -qw BUG "$tree/rtl/alu.sv"; } || { [ "$test" = xor_test ] && grep -qwE "BUG|XORBUG" "$tree/rtl/alu.sv"; }; then
      echo "FAIL  test=$test  signal=TOP.dut.rvfi_mem_wdata  time=100  expected=0xfffff800  actual=$actual  dump=$out/dump.vcd" > "$out/sim.log"
      exit 1
    fi
    echo "PASS  test=$test" > "$out/sim.log"; exit 0 ;;
  suite)
    out=$3; pat=${4:-.}; mkdir -p "$out"; : > "$out/summary.txt"
    for t in add_test sub_test xor_test; do
      echo "$t" | grep -qE "$pat" || continue
      "$0" run "$tree" "$t" "$out/$t" --dump=off; rc=$?
      [ $rc -eq 2 ] && exit 2
      [ $rc -eq 0 ] && rm -rf "$out/$t"
      echo "$rc $t" >> "$out/summary.txt"
    done
    exit 0 ;;
  *) exit 64 ;;
esac
