#!/bin/sh
# Make the certificate Pebble, the test ACME server, serves on its own API port,
# in ./pebble-tls. Certbot trusts exactly this file. Test material only: with a
# real ACME server there is nothing to make.
set -eu
cd "$(dirname "$0")"
mkdir -p pebble-tls
[ -s pebble-tls/cert.pem ] || openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -subj "/CN=pebble" -addext "subjectAltName=DNS:pebble" \
  -keyout pebble-tls/key.pem -out pebble-tls/cert.pem
chmod 644 pebble-tls/key.pem
