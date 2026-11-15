#!/usr/bin/env bash
# Check the snippet against the running example. Exit 1 if any check fails.
#   docker compose up -d && ./test.sh
# The rate limit counts a minute: run it again after 60 seconds.
set -u
cd "$(dirname "$0")" || exit 2
base=${BASE:-http://localhost:8090}
fail=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
code() { curl -s -o /dev/null -w '%{http_code}' -H 'Host: app.example.com' "$@"; }

[ "$(code "$base/")" = 200 ] && ok "a plain request passes" || bad "a plain request did not pass"

[ "$(code "$base/admin/panel")" = 403 ] && ok "/admin is blocked" || bad "/admin was not blocked"

# A scanner is let through and tagged in the access log.
[ "$(code -A sqlmap/1.7 "$base/tagged")" = 200 ] && ok "a scanner user agent is not blocked" || bad "the scanner request failed"
sleep 1
grep -h '/tagged' logs/access.log 2>/dev/null | grep -q '"axon_tag":"scanner-ua"' \
  && ok "the scanner request carries the tag in access.log" || bad "no scanner-ua tag in logs/access.log"

# More than 30 requests in a minute from one address are blocked.
last=200
for _ in $(seq 1 40); do last=$(code "$base/burst"); done
[ "$last" = 403 ] && ok "the 40th request in a minute is blocked" || bad "the burst was not limited (last status $last)"

exit $fail
