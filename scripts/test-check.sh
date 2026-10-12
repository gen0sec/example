#!/usr/bin/env bash
# Controls for scripts/check.sh: prove it can fail before trusting it to pass.
#   valid set          -> must pass
#   misspelled key     -> must fail (a warning counts as a failure)
#   bad value          -> must fail
#   zero config sets   -> must fail
#   missing binary     -> must fail, with a message
#   binary without --check-config -> must fail (exit 2)
#   typo in upstreams.yaml / security_rules.yaml -> must fail
#   orphan upstreams.yaml (no config.yaml beside it) -> must fail
#   relative SYNAPSE_BIN -> must still work
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
  if [ -n "$pattern" ] && ! printf '%s\n' "$out" | grep -q -- "$pattern"; then
    echo "FAIL: $label: output lacks '$pattern'"; echo "$out" | sed 's/^/    /'; fails=$((fails + 1)); return
  fi
  echo "ok:   $label (exit $rc)"
}

expect pass "valid set passes"            ""                 "$check" "$fx/valid"
expect fail "misspelled key fails"        "network.ifce"     "$check" "$fx/typo"
expect fail "bad value fails"             "mode"             "$check" "$fx/bad-value"
expect fail "zero config sets fails"      "no config sets"   "$check" "$fx/empty-root"
expect fail "missing binary fails"        "not found"        env SYNAPSE_BIN=/nonexistent/synapse "$check" "$fx/valid"
expect fail "binary without --check-config fails" "does not support" env SYNAPSE_BIN=/bin/true "$check" "$fx/valid"
expect pass "valid set with upstreams and rules passes" "" "$check" "$fx/valid-set"
expect fail "typo in upstreams.yaml fails" "upstreamz" "$check" "$fx/typo-upstreams"
expect fail "typo in security_rules.yaml fails" "ips" "$check" "$fx/typo-rules"
expect fail "orphan upstreams.yaml fails" "lonely" "$check" "$fx/orphan-root"

# A relative SYNAPSE_BIN must work: the check runs from each set's directory.
abs_bin=$(command -v "${SYNAPSE_BIN:-synapse}" 2>/dev/null || true)
if [ -n "$abs_bin" ]; then
  expect pass "relative SYNAPSE_BIN works" "" \
    bash -c 'cd "$(dirname "$1")" && SYNAPSE_BIN=./$(basename "$1") "$2" "$3"' _ "$abs_bin" "$check" "$fx/valid"
else
  echo "FAIL: relative SYNAPSE_BIN: no binary to test with"; fails=$((fails + 1))
fi

if [ "$fails" -ne 0 ]; then
  echo "$fails control(s) failed"
  exit 1
fi
echo "all controls passed"
