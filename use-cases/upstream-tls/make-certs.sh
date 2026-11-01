#!/bin/sh
# Make a test CA, a back-end certificate for backend.internal, and a client
# certificate, in ./certs. Test material only.
set -eu
cd "$(dirname "$0")"
mkdir -p certs && cd certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=Example test CA" \
  -keyout ca.key -out ca.crt
for n in backend client; do
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$n" -keyout $n.key -out $n.csr
done
printf 'subjectAltName=DNS:backend.internal\n' > backend.ext
printf 'extendedKeyUsage=clientAuth\n' > client.ext
openssl x509 -req -in backend.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 30 -extfile backend.ext -out backend.crt
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 30 -extfile client.ext -out client.crt
rm -f *.csr *.ext *.srl
chmod 600 *.key
