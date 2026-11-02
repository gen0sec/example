#!/bin/sh
# Make the certificate Pebble, the test ACME server, serves on its own API port,
# in ./pebble-tls, again once it has under a day left. Certbot trusts exactly
# this file. Test material only: with a real ACME server there is nothing to make.
set -eu
cd "$(dirname "$0")"
mkdir -p pebble-tls
# Make it again when it is missing or has under a day left.
openssl x509 -checkend 86400 -noout -in pebble-tls/cert.pem >/dev/null 2>&1 || openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -subj "/CN=pebble" -addext "subjectAltName=DNS:pebble" \
  -keyout pebble-tls/key.pem -out pebble-tls/cert.pem
chmod 644 pebble-tls/key.pem
