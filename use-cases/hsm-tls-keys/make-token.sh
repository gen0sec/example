#!/bin/sh
# Runs in the `token` container. Makes a SoftHSM token, puts an RSA key and an
# EC key in it, makes a certificate for each, and writes what Synapse reads:
#
#   /certs/<name>.crt   certificate
#   /certs/<name>.key   a pkcs11: URI (HSM keys) or a PEM key (the software key)
#   /hsm/pin            the token PIN, mode 0600
#   /hsm/tokens         the token itself
#
# DEMO SHORTCUT: the keys are made in software and then imported into the token
# with `softhsm2-util --import`. That puts a copy of each private key on disk
# for the moment it takes to import it; it is deleted at the end. A real HSM
# makes the key on the device (`pkcs11-tool --keypairgen`, or the vendor's tool)
# and never lets it out. Issue the certificate from a CSR signed on the device.
set -eu

[ -f /hsm/pin ] && { echo "token already provisioned"; exit 0; }
# The PIN file is written last, so a token without it is a run that stopped
# half way. Starting again would add a second token.
if [ -n "$(ls -A /hsm/tokens 2>/dev/null)" ]; then
  echo "a previous run stopped half way; start again with: docker compose down -v" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p /hsm/tokens /certs
module=/usr/lib/softhsm/libsofthsm2.so
pin=$(openssl rand -hex 6)
sopin=$(openssl rand -hex 6)

softhsm2-util --init-token --free --label synapse --pin "$pin" --so-pin "$sopin" >/dev/null

cert() { # name keyfile
  openssl req -x509 -new -key "$2" -days 30 -subj "/CN=$1" \
    -addext "subjectAltName=DNS:$1" -out "/certs/$1.crt"
}

# www: RSA key, in the HSM.
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/www.pem" 2>/dev/null
cert www.example.com "$work/www.pem"
softhsm2-util --import "$work/www.pem" --token synapse --label www --id 01 --pin "$pin" >/dev/null
echo 'pkcs11:token=synapse;object=www;type=private' > /certs/www.example.com.key

# api: EC P-256 key, in the HSM.
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$work/api.pem" 2>/dev/null
cert api.example.com "$work/api.pem"
softhsm2-util --import "$work/api.pem" --token synapse --label api --id 02 --pin "$pin" >/dev/null
echo 'pkcs11:token=synapse;object=api;type=private' > /certs/api.example.com.key

# static: a software key, to show both kinds side by side.
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out /certs/static.example.com.key 2>/dev/null
cert static.example.com /certs/static.example.com.key
chmod 600 /certs/static.example.com.key

# The PIN file: regular, non-empty, mode 0600, owned by root (Synapse runs as
# root in the image; otherwise the service user).
umask 077
printf '%s\n' "$pin" > /hsm/pin
chmod 600 /hsm/pin

echo "objects on the token:"
pkcs11-tool --module "$module" --token-label synapse --login --pin "$pin" --list-objects 2>/dev/null \
  | grep -E '^(Private Key Object|Public Key Object|Certificate Object)|label:' | head -20
