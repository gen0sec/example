#!/usr/bin/env bash
# Check the header rules against the running example. Exit 1 if any check fails.
#   docker compose up -d && ./test.sh
set -u
base=${BASE:-http://localhost:8087}
fail=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }

req=$(curl -s -H 'Host: app.example.com' -H 'X-Debug: 1' -H 'X-Internal-Token: s3cret' \
  -H 'X-Edge: client-value' -H 'X-Trace: client' "$base/req/api/x")
resp=$(curl -s -D- -o /dev/null -H 'Host: app.example.com' "$base/resp")

has()  { grep -qi "^$2: *$3" <<<"$1"; }
absent() { ! grep -qi "^$2:" <<<"$1"; }

# --- request headers, as the back-end received them
absent "$req" X-Debug                 && ok "request: remove exact name (X-Debug)"        || bad "request: X-Debug reached the back-end"
absent "$req" X-Internal-Token        && ok "request: remove by prefix (X-Internal-*)"    || bad "request: X-Internal-Token reached the back-end"
has "$req" X-Edge synapse             && ok "request: global headers entry replaces the client's value" || bad "request: X-Edge is not 'synapse'"
has "$req" X-Api-Version v2           && ok "request: set with a when condition"          || bad "request: X-Api-Version missing"
has "$req" X-Client-Ip '[0-9]'        && ok "request: set_expr (to_string(ip.src))"       || bad "request: X-Client-Ip missing"
grep -qi '^X-Trace: .*client' <<<"$req" && grep -qi '^X-Trace: .*from-synapse' <<<"$req" \
                                      && ok "request: add keeps the client's value and appends" || bad "request: X-Trace not appended"
has "$req" X-Route req                && ok "request: route-level headers entry"          || bad "request: X-Route missing"
# the when condition must not fire off its path
other=$(curl -s -H 'Host: app.example.com' "$base/req/other")
absent "$other" X-Api-Version         && ok "request: when condition does not fire on another path" || bad "request: X-Api-Version set on /req/other"

# --- response headers, as the client receives them
absent "$resp" X-Powered-By           && ok "response: remove exact name (X-Powered-By)"  || bad "response: X-Powered-By leaked"
absent "$resp" Server                 && ok "response: remove Server"                      || bad "response: Server leaked"
absent "$resp" X-Internal-Trace       && ok "response: remove by prefix (X-Internal-*)"   || bad "response: X-Internal-Trace leaked"
has "$resp" X-Content-Type-Options nosniff && ok "response: global headers entry replaces the origin's value" || bad "response: X-Content-Type-Options not nosniff"
has "$resp" X-Frame-Options DENY      && ok "response: host-level headers entry"          || bad "response: X-Frame-Options missing"
has "$resp" Cache-Control no-store    && ok "response: set when status == 200"            || bad "response: Cache-Control not no-store"
n=$(grep -ci '^Set-Cookie:' <<<"$resp")
[ "$n" = 3 ] && grep -qi 'origin=1' <<<"$resp" && grep -qi 'edge=1' <<<"$resp" && grep -qi 'region=eu' <<<"$resp" \
                                      && ok "response: add appends two cookies to the origin's" || bad "response: expected 3 Set-Cookie, got $n"

exit $fail
