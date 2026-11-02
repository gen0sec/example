#!/bin/sh
# Make the sticky-session signing key, ./sticky.key. Test material only: make a
# real key once per cluster and copy the same file to every node.
set -eu
cd "$(dirname "$0")"
[ -s sticky.key ] || (umask 077; head -c 32 /dev/urandom > sticky.key)
