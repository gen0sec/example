#!/usr/bin/env bash
# Refuse an `in` operator without braces in a rules expression.
#
# Usage: scripts/check-expressions.sh [DIR...]
#   DIR...  roots to search; default: use-cases/ and reference/ (those that exist)
#
# `in` takes a set in braces: `ip.src in {10.0.0.0/8}`. `--check-config` does
# not compile smart-firewall expressions, and a rule that does not compile is
# skipped with a warning at start, so a brace-less form goes unnoticed. This
# check needs no synapse binary.
#
# It reads every `expression:` line of every security_rules.yaml under the
# roots (smart_firewall_rules, waf_rules and any other section) and fails on
# `in` followed by a character other than `{` or `$` (a list variable).
#
# Limit: it is a regex, not a parser. A ` in ` inside a quoted string, as in
# `http.request.path contains "log in here"`, is a false positive. Reword the
# string or set it in a variable. A multi-line expression is read only on its
# `expression:` line.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
if [ "$#" -gt 0 ]; then
  roots=("$@")
else
  roots=()
  for d in use-cases reference; do
    [ -d "$root/$d" ] && roots+=("$root/$d")
  done
fi

for d in "${roots[@]}"; do
  if [ ! -d "$d" ]; then
    echo "error: '$d' is not a directory." >&2
    exit 2
  fi
done

files=$(find "${roots[@]}" -name security_rules.yaml | sort)
if [ -z "$files" ]; then
  echo "error: no security_rules.yaml found under: ${roots[*]}" >&2
  exit 2
fi

status=0
while IFS= read -r f; do
  hits=$(grep -nE 'expression:.*[[:space:]]in[[:space:]]+[^{$[:space:]]' "$f") || true
  if [ -n "$hits" ]; then
    while IFS= read -r h; do
      echo "$f:${h%%:*}: 'in' without braces: ${h#*:}" >&2
    done <<< "$hits"
    status=1
  fi
done <<< "$files"
[ "$status" -eq 0 ] && echo "ok: no brace-less 'in' in $(echo "$files" | wc -l) security_rules.yaml file(s)"
exit $status
