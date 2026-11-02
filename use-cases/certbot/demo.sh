#!/bin/sh
# Runs in the client container: what Synapse serves for app.example.com now.
# Pebble makes a new root on every start, so fetch the one in use, over its
# own API port, which the test certificate in /pebble-tls secures.
get() { printf 'GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' "$2" "$1"; }
get pebble /roots/0 | openssl s_client -quiet -CAfile /pebble-tls/cert.pem \
  -connect pebble:15000 2>/dev/null | sed -n '/BEGIN CERT/,/END CERT/p' > /tmp/root.pem

echo "== the certificate on app.example.com:443"
out=$(openssl s_client -connect app.example.com:443 -servername app.example.com \
  -CAfile /tmp/root.pem </dev/null 2>&1)
cert=$(echo "$out" | openssl x509 2>/dev/null)
if [ -z "$cert" ]; then
  echo "$out" | grep -E 'alert|error' | head -3
else
  echo "$cert" | openssl x509 -noout -serial -issuer -dates -ext subjectAltName
  echo "$out" | grep '^Verification'
fi

echo "== a request on https"
get app.example.com / | openssl s_client -quiet -CAfile /tmp/root.pem \
  -connect app.example.com:443 -servername app.example.com 2>&1 | grep -E '^(Hostname|Host):|error'

echo "== the challenge path on http, with no file behind it"
wget -S -O /dev/null http://app.example.com/.well-known/acme-challenge/none 2>&1 | grep -E '^  HTTP/'
