#!/usr/bin/env bash
# Validate every Synapse config set in this repository with `--check-config`.
#
# Usage: scripts/check.sh [DIR...]
#   DIR...  roots to search; default: use-cases/ and reference/ (those that exist)
#
# Environment:
#   SYNAPSE_BIN  the synapse binary (default: `synapse` on PATH). It must
#                support --check-config.
#   SYNAPSE_REQUIRE_ML  set to 1 to fail a set that a build without the
#                classifier feature had to skip (see below). Use it with a
#                classifier build, where no set should be skipped.
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
#   - an upstreams.yaml or security_rules.yaml in a directory with no
#     config.yaml (an orphan would otherwise go unchecked);
#   - the binary missing or unable to run. There is no silent pass.
# One warning is ignored: "security rules file not found", which the binary
# prints for a set that has no security_rules.yaml, because the binary looks
# for that file whether or not a set has one.
# One more is a skip, not a failure: a build without the classifier feature
# prints "Config options not supported by this build: ml ..." for the `ml:`
# keys. A set whose only warning is that line prints `skip` and is counted as
# skipped; any other warning in the same set still fails it. The build cannot
# check inside `ml:` then, so a typo there shows only on a classifier build.
set -u

bin=${SYNAPSE_BIN:-synapse}
resolved=$(command -v "$bin" 2>/dev/null) || resolved=
if [ -z "$resolved" ] || [ ! -x "$resolved" ]; then
  echo "error: synapse binary '$bin' not found. Set SYNAPSE_BIN to a binary that supports --check-config." >&2
  exit 2
fi
# Absolute path, because each set is checked from its own directory.
case $resolved in
  /*) bin=$resolved ;;
  *) bin=$(cd "$(dirname "$resolved")" && pwd)/$(basename "$resolved") ;;
esac
help_text=$("$bin" --help 2>&1) || true
case $help_text in
  *--check-config*) ;;
  *)
    echo "error: '$bin' does not support --check-config." >&2
    exit 2
    ;;
esac

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

# Orphans: a rules or upstreams file whose directory has no config.yaml.
orphans=0
if [ "${#roots[@]}" -gt 0 ]; then
  while IFS= read -r f; do
    if [ ! -f "$(dirname "$f")/config.yaml" ]; then
      echo "error: $f has no config.yaml beside it, so it is not part of any config set" >&2
      orphans=$((orphans + 1))
    fi
  done < <(find "${roots[@]}" -type f \( -name upstreams.yaml -o -name security_rules.yaml \) | sort)
fi

if [ "${#sets[@]}" -eq 0 ]; then
  echo "error: no config sets found (a config set is a directory holding config.yaml) under: ${roots[*]:-use-cases reference}" >&2
  exit 1
fi

failed=$orphans
skipped=0
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
  warnings=$(printf '%s\n' "$out" | awk -v has_rules="$has_rules" '
    /^warning:/ { if (!has_rules && /security rules file not found/) next; print }')
  # Of those, the classifier-only line is a skip when nothing else is left.
  other=$(printf '%s\n' "$warnings" | grep -v 'Config options not supported by this build:' || true)
  ml_skip=0
  if [ -n "$warnings" ] && [ -z "$other" ]; then ml_skip=1; fi

  rel=${dir#"$root"/}
  if [ "$rc" -eq 0 ] && [ "$ml_skip" -eq 1 ] && [ "${SYNAPSE_REQUIRE_ML:-}" != 1 ]; then
    echo "skip $rel (ML keys need a classifier build)"
    skipped=$((skipped + 1))
  elif [ "$rc" -ne 0 ] || [ -n "$warnings" ]; then
    echo "FAIL $rel"
    printf '%s\n' "$out" | sed 's/^/    /'
    failed=$((failed + 1))
  else
    echo "ok   $rel"
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "$failed problem(s): $orphans orphan file(s), $((failed - orphans)) of ${#sets[@]} config set(s) failed" >&2
  exit 1
fi
echo "${#sets[@]} config set(s) passed, $skipped skipped"
