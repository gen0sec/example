#!/bin/sh
# Make a self-signed certificate for app.example.com in ./certs. Test material only.
set -eu
cd "$(dirname "$0")"
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -subj "/CN=app.example.com" -addext "subjectAltName=DNS:app.example.com,DNS:legacy.example.com" \
  -keyout certs/app.example.com.key -out certs/app.example.com.crt
chmod 644 certs/app.example.com.key
