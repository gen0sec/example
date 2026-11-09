#!/bin/sh
# The whole demo, from the host: start, check each host, and check that the
# PIN reached no log. Needs Docker with Compose v2. Leaves the stack running.
set -eu
cd "$(dirname "$0")"

docker compose up -d --build
docker compose run --rm client

pin=$(docker compose run --rm --no-deps -T --entrypoint cat token /hsm/pin)
[ -n "$pin" ] || { echo "no PIN read"; exit 1; }
if docker compose logs --no-color 2>&1 | grep -qF "$pin"; then
  echo "FAIL: the PIN appears in a log"
  exit 1
fi
echo "== the PIN appears in no log"
