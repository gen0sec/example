#!/usr/bin/env bash
# Validate every Synapse config set in this repository with `--check-config`.
#
# Usage: scripts/check.sh [DIR...]
#   DIR...  roots to search; default: use-cases/ and reference/ (those that exist)
#
# Environment:
#   SYNAPSE_BIN  the synapse binary (default: `synapse` on PATH). It must
#                support --check-config.
#
# What a config set is: a directory that holds a `config.yaml`. Beside it,
# an `upstreams.yaml` and a `security_rules.yaml` are part of the same set when
# present, and are passed as --upstream-conf and --security-rules-config. A set
# is checked from its own directory, so paths in the command are relative.
#
# What fails the run:
#   - a non-zero exit from the binary (an invalid file or value);
#   - any `warning:` line, because an unknown (misspelled) key is only a warning;
#   - no config sets found under the roots;
#   - the binary missing or unable to run. There is no silent pass.
# One warning is ignored: "security rules file not found", which the binary
# prints for a set that has no security_rules.yaml, because the binary looks
# for that file whether or not a set has one.
set -u

bin=${SYNAPSE_BIN:-synapse}
if ! command -v "$bin" >/dev/null 2>&1; then
  echo "error: synapse binary '$bin' not found. Set SYNAPSE_BIN to a binary that supports --check-config." >&2
  exit 2
fi
if ! "$bin" --help 2>&1 | /usr/bin/grep -q -- '--check-config'; then
  echo "error: '$bin' does not support --check-config." >&2
  exit 2
fi

root=$(cd "$(dirname "$0")/.." && pwd)
if [ "$#" -gt 0 ]; then
  roots=("$@")
else
  roots=()
  for d in use-cases reference; do
    [ -d "$root/$d" ] && roots+=("$root/$d")
  done
fi

sets=()
if [ "${#roots[@]}" -gt 0 ]; then
  while IFS= read -r f; do
    sets+=("$(dirname "$f")")
  done < <(find "${roots[@]}" -type f -name config.yaml | sort)
fi

if [ "${#sets[@]}" -eq 0 ]; then
  echo "error: no config sets found (a config set is a directory holding config.yaml) under: ${roots[*]:-use-cases reference}" >&2
  exit 1
fi

failed=0
for dir in "${sets[@]}"; do
  args=(--check-config --config config.yaml)
  [ -f "$dir/upstreams.yaml" ] && args+=(--upstream-conf upstreams.yaml)
  has_rules=0
  if [ -f "$dir/security_rules.yaml" ]; then
    has_rules=1
    args+=(--security-rules-config security_rules.yaml)
  fi

  out=$(cd "$dir" && "$bin" "${args[@]}" 2>&1)
  rc=$?

  # Warnings that fail the check (all but the absent-rules-file notice).
  warnings=$(printf '%s\n' "$out" | /usr/bin/grep '^warning:' || true)
  if [ "$has_rules" -eq 0 ]; then
    warnings=$(printf '%s\n' "$warnings" | /usr/bin/grep -v 'security rules file not found' || true)
  fi

  rel=${dir#"$root"/}
  if [ "$rc" -ne 0 ] || [ -n "$warnings" ]; then
    echo "FAIL $rel"
    printf '%s\n' "$out" | sed 's/^/    /'
    failed=$((failed + 1))
  else
    echo "ok   $rel"
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "$failed of ${#sets[@]} config set(s) failed" >&2
  exit 1
fi
echo "${#sets[@]} config set(s) passed"
