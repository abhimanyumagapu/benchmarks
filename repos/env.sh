# Sourced by every repos/<repo>/run.sh. Tool paths, and the one loop the `suite` verb shares.
# STEAD_TOOLS holds verilator, riscv gcc, spike, the riscv-compliance suite, per-repo venvs.
export STEAD_TOOLS=${STEAD_TOOLS:-$HOME/repos/tools}
export PATH=$STEAD_TOOLS/verilator/bin:$STEAD_TOOLS/bin:$PATH

# stead_suite <run.sh> <tree> <out> <regex>   test names on stdin, one per line
# Runs each test matching <regex> with the dump off, each capped at $STEAD_TEST_TIMEOUT s (the
# harness sets it; stead/recipe.py TEST_TIMEOUT); writes <out>/summary.txt
# ("<exit> <test>" per test) and keeps <out>/<test>/ only for tests that did not pass.
stead_suite() {
  local sh=$1 tree=$2 out=$3 pat=$4 t rc
  mkdir -p "$out"; : > "$out/summary.txt"
  while read -r t; do
    [ -n "$t" ] && echo "$t" | grep -qE "$pat" || continue
    timeout -k 10 "${STEAD_TEST_TIMEOUT:-1200}" "$sh" run "$tree" "$t" "$out/$t" --dump=off; rc=$?
    [ $rc -eq 124 ] && rc=3
    [ $rc -eq 2 ] && exit 2
    [ $rc -eq 0 ] && rm -rf "$out/$t"
    echo "$rc $t" >> "$out/summary.txt"
  done
  exit 0
}
