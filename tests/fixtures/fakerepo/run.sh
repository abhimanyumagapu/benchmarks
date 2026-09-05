#!/bin/bash
# Fake repo runner implementing the STEAD run.sh contract, for harness tests.
#   run.sh build <tree>                      exit 0 ok, 2 build error
#   run.sh run   <tree> <test> <out_dir>     exit 0 PASS, 1 FAIL, 2 build error, 3 crash
# The "DUT" is <tree>/rtl/alu.sv; it is buggy if it contains the token BUG.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
verb=$1; tree=$2
case $verb in
  build)
    [ -f "$tree/rtl/alu.sv" ] || exit 2
    grep -q SYNTAX_ERROR "$tree/rtl/alu.sv" && exit 2
    mkdir -p "$tree/build" && touch "$tree/build/ok"; exit 0 ;;
  run)
    test=$3; out=$4; mkdir -p "$out"
    [ -f "$tree/build/ok" ] || { echo "not built" > "$out/sim.log"; exit 2; }
    grep -q HANG "$tree/rtl/alu.sv" && { echo "timeout" > "$out/sim.log"; exit 3; }
    if [ "$test" = xor_test ] && grep -q BUG "$tree/rtl/alu.sv"; then
      cp "$HERE/../mini.vcd" "$out/dump.vcd"
      echo "FAIL  test=$test  signal=TOP.dut.rvfi_mem_wdata  time=100  expected=0xfffff800  actual=0xfffff810  dump=$out/dump.vcd" > "$out/sim.log"
      exit 1
    fi
    cp "$HERE/../mini.vcd" "$out/dump.vcd"
    echo "PASS  test=$test" > "$out/sim.log"; exit 0 ;;
  *) exit 64 ;;
esac
