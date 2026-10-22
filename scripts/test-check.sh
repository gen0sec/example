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
#   ML keys (ml-keys, ml-keys-typo, ml-inner-typo) -> depends on the build,
#     which this script detects: a default build skips ml-keys, fails
#     ml-keys-typo and fails ml-keys under SYNAPSE_REQUIRE_ML=1; a classifier
#     build passes ml-keys and fails ml-inner-typo.
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

# Which build is this? A default build prints the classifier-only warning for ml-keys.
probe=$(cd "$fx/ml-keys" && "${SYNAPSE_BIN:-synapse}" --check-config --config config.yaml 2>&1)
if printf '%s\n' "$probe" | grep -q 'Config options not supported by this build:'; then
  echo "build: default (no classifier feature)"
  expect pass "ML keys are skipped" "skip .*ML keys need a classifier build" "$check" "$fx/ml-keys"
  expect pass "skip is counted in the summary" "1 skipped" "$check" "$fx/ml-keys"
  expect fail "ML keys plus a typo fail" "network.ifce" "$check" "$fx/ml-keys-typo"
  expect fail "ML keys fail under SYNAPSE_REQUIRE_ML=1" "Config options not supported" \
    env SYNAPSE_REQUIRE_ML=1 "$check" "$fx/ml-keys"
  expect pass "typo inside ml: is invisible (documented limit)" "skip " "$check" "$fx/ml-inner-typo"
else
  echo "build: classifier"
  expect pass "ML keys pass" "ok   " "$check" "$fx/ml-keys"
  expect pass "ML keys pass under SYNAPSE_REQUIRE_ML=1" "ok   " env SYNAPSE_REQUIRE_ML=1 "$check" "$fx/ml-keys"
  expect fail "ML keys plus a typo fail" "network.ifce" "$check" "$fx/ml-keys-typo"
  expect fail "typo inside ml: fails" "enabeld" "$check" "$fx/ml-inner-typo"
fi

if [ "$fails" -ne 0 ]; then
  echo "$fails control(s) failed"
  exit 1
fi
echo "all controls passed"
