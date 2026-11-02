#!/bin/sh
# Runs in the client container: what the signed cookie does.
U=${URL:-http://172.30.7.10:8080/}
hit() { curl -s -H 'Host: app.example.com' "$@" "$U" | grep Hostname; }
jar=/tmp/jar

echo "== no cookie: round robin"
for i in 1 2 3; do hit; done

echo "== the first response sets a signed cookie, <id>.<mac>"
curl -si -H 'Host: app.example.com' -c "$jar" "$U" | grep -i '^set-cookie'

echo "== with that cookie: one server, six times"
for i in 1 2 3 4 5 6; do hit -b "$jar"; done

value=$(awk '/backend_id/ {print $7}' "$jar")
last=${value#"${value%?}"}
[ "$last" = 0 ] && flip=1 || flip=0

echo "== the last digit of the mac changed: ignored, the next server, a fresh cookie"
curl -si -H 'Host: app.example.com' -H "Cookie: backend_id=${value%?}$flip" "$U" | grep -iE '^(set-cookie|hostname)'

echo "== the id without a mac: ignored the same way"
curl -si -H 'Host: app.example.com' -H "Cookie: backend_id=${value%%.*}" "$U" | grep -iE '^(set-cookie|hostname)'
