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
# It reads the value of every `expression:` key in every security_rules.yaml
# under the roots (smart_firewall_rules, waf_rules and any other section) and
# fails on `in` followed by a character other than `{` or `$` (a list
# variable). The value may be a plain or quoted scalar, a `|` or `>` block
# scalar, or span several lines; lines are joined before the test, so `in` at
# the end of a line is read with the next line.
#
# Not read: a `#` comment line, a trailing comment, and a commented-out
# example. A commented-out `expression:` is not enforced, so it is not flagged.
# `expression:` counts only as a key, at the start of a line (after `- `) or
# after `{` or `,` in flow style, not inside another key's value.
#
# Exit: 0 clean, 1 a brace-less `in` found, 2 usage error or unreadable input.
#
# Limit: it is a regex, not a parser. A ` in ` inside a quoted string, as in
# `http.request.path contains "log in here"`, is a false positive. Reword the
# string or set it in a variable.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
roots=()
if [ "$#" -gt 0 ]; then
  roots=("$@")
else
  for d in use-cases reference; do
    [ -d "$root/$d" ] && roots+=("$root/$d")
  done
fi

# An empty array under `set -u` is an error in bash 3.2.
if [ "${#roots[@]}" -eq 0 ]; then
  echo "error: no directory to search." >&2
  exit 2
fi

for d in "${roots[@]}"; do
  if [ ! -d "$d" ]; then
    echo "error: '$d' is not a directory." >&2
    exit 2
  fi
done

files=$(find "${roots[@]}" -name security_rules.yaml) || {
  echo "error: find failed under: ${roots[*]}" >&2
  exit 2
}
files=$(printf '%s\n' "$files" | sed '/^$/d' | sort)
if [ -z "$files" ]; then
  echo "error: no security_rules.yaml found under: ${roots[*]}" >&2
  exit 2
fi

# Prints "FILE:LINE: 'in' without braces: TEXT" per hit; LINE is the line of
# the `expression:` key.
read -r -d '' prog <<'AWK'
function indent(s) { match(s, /^[[:space:]]*/); return RLENGTH }
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
function check(text) {
  if ((" " text) ~ /[[:space:]]in[[:space:]]+([^{$[:space:]]|$)/)
    { gsub(/[[:space:]]+/, " ", text); print f ":" sline ": 'in' without braces: " trim(text) }
}
# Index of the quote that closes the scalar opened at s[1], or 0.
function closeidx(s, q,    i, c, n) {
  n = length(s)
  for (i = 2; i <= n; i++) {
    c = substr(s, i, 1)
    if (q == "\"" && c == "\\") { i++; continue }
    if (c == q) {
      if (q == "'" && substr(s, i + 1, 1) == "'") { i++; continue }
      return i
    }
  }
  return 0
}
function flush() {
  if (mode == 2) check(substr(buf, 2))
  else if (mode == 1 || mode == 3) check(buf)
  mode = 0
}
function start(val,    c, end) {
  c = substr(val, 1, 1)
  buf = ""
  if (c == "|" || c == ">") { mode = 1; return }
  if (c == "'" || c == "\"") {
    q = c; buf = val; end = closeidx(buf, q)
    if (end) { check(substr(buf, 2, end - 2)); mode = 0 } else mode = 2
    return
  }
  if (match(val, /[[:space:]]#/)) { val = substr(val, 1, RSTART - 1); mode = 0; done = 1 } else done = 0
  if (flow) { sub(/[,}].*$/, "", val); done = 1 }
  buf = trim(val)
  if (done) check(buf); else mode = 3
  if (done) mode = 0
}
{
  line = $0
  if (mode == 1) {
    if (line ~ /^[[:space:]]*$/) next
    if (indent(line) > keycol) { buf = buf " " line; next }
    flush()
  } else if (mode == 2) {
    buf = buf " " line
    end = closeidx(buf, q)
    if (end) { check(substr(buf, 2, end - 2)); mode = 0 }
    next
  } else if (mode == 3) {
    if (line ~ /^[[:space:]]*$/) next
    if (indent(line) > keycol && line !~ /^[[:space:]]*#/) {
      t = line
      if (match(t, /[[:space:]]#/)) { t = substr(t, 1, RSTART - 1); buf = buf " " trim(t); flush() }
      else buf = buf " " trim(t)
      next
    }
    flush()
  } else if (mode == 4) {
    if (line ~ /^[[:space:]]*($|#)/) next
    if (indent(line) > keycol) { start(trim(line)); next }
    mode = 0
  }
  if (line ~ /^[[:space:]]*#/) next
  if (!match(line, /["']?expression["']?:([[:space:]]|$)/)) next
  pre = substr(line, 1, RSTART - 1)
  rest = substr(line, RSTART + RLENGTH)
  if (pre ~ /^[[:space:]]*(-[[:space:]]+)*$/) { flow = 0; keycol = length(pre) }
  else if (pre ~ /[{,][[:space:]]*$/) { flow = 1; keycol = indent(line) }
  else next
  sline = NR
  rest = trim(rest)
  if (rest == "" || substr(rest, 1, 1) == "#") { mode = 4; next }
  start(rest)
}
END { flush() }
AWK

status=0
while IFS= read -r f; do
  if [ ! -r "$f" ]; then
    echo "error: cannot read '$f'." >&2
    exit 2
  fi
  hits=$(LC_ALL=C awk -v f="$f" "$prog" "$f") || {
    echo "error: awk failed on '$f'." >&2
    exit 2
  }
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits" >&2
    status=1
  fi
done <<< "$files"
[ "$status" -eq 0 ] && echo "ok: no brace-less 'in' in $(echo "$files" | wc -l) security_rules.yaml file(s)"
exit $status
