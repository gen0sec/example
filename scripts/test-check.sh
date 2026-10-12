#!/usr/bin/env bash
# Controls for scripts/check.sh: prove it can fail before trusting it to pass.
#   valid set          -> must pass
#   misspelled key     -> must fail (a warning counts as a failure)
#   bad value          -> must fail
#   zero config sets   -> must fail
#   missing binary     -> must fail, with a message
# Needs the same SYNAPSE_BIN as check.sh.
set -u

here=$(cd "$(dirname "$0")" && pwd)
check="$here/check.sh"
fx="$here/fixtures"
fails=0

# expect <pass|fail> <label> <pattern-or-empty> <command...>
expect() {
  local want=$1 label=$2 pattern=$3
  shift 3
  local out rc
  out=$("$@" 2>&1)
  rc=$?
  if [ "$want" = pass ] && [ "$rc" -ne 0 ]; then
    echo "FAIL: $label: expected exit 0, got $rc"; echo "$out" | sed 's/^/    /'; fails=$((fails + 1)); return
  fi
  if [ "$want" = fail ] && [ "$rc" -eq 0 ]; then
    echo "FAIL: $label: expected non-zero exit, got 0"; echo "$out" | sed 's/^/    /'; fails=$((fails + 1)); return
  fi
  if [ -n "$pattern" ] && ! printf '%s\n' "$out" | /usr/bin/grep -q -- "$pattern"; then
    echo "FAIL: $label: output lacks '$pattern'"; echo "$out" | sed 's/^/    /'; fails=$((fails + 1)); return
  fi
  echo "ok:   $label (exit $rc)"
}

expect pass "valid set passes"            ""                 "$check" "$fx/valid"
expect fail "misspelled key fails"        "network.ifce"     "$check" "$fx/typo"
expect fail "bad value fails"             "mode"             "$check" "$fx/bad-value"
expect fail "zero config sets fails"      "no config sets"   "$check" "$fx/empty-root"
expect fail "missing binary fails"        "not found"        env SYNAPSE_BIN=/nonexistent/synapse "$check" "$fx/valid"

if [ "$fails" -ne 0 ]; then
  echo "$fails control(s) failed"
  exit 1
fi
echo "all controls passed"
