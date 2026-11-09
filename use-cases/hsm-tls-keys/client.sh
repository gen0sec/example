#!/bin/sh
# Runs in the client container: what Synapse serves for each host, over
# TLS 1.2 and TLS 1.3. The certificates are self-signed, so each host's own
# certificate file is the trust anchor.
get() { printf 'GET / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' "$1"; }
fail=0

for host in www.example.com api.example.com static.example.com; do
  echo "== $host: key line in $host.key"
  head -1 "/certs/$host.key" | cut -c1-60
  for v in tls1_2 tls1_3; do
    out=$(openssl s_client -connect "$host:443" -servername "$host" -"$v" \
      -CAfile "/certs/$host.crt" -verify_hostname "$host" </dev/null 2>&1)
    proto=$(echo "$out" | sed -n 's/^New, \(TLSv[0-9.]*\),.*/\1/p' | head -1)
    sig=$(echo "$out" | sed -n 's/^Peer signature type: *//p' | head -1)
    kind=$(echo "$out" | openssl x509 -noout -text 2>/dev/null | sed -n 's/^ *Public Key Algorithm: *//p')
    ver=$(echo "$out" | sed -n 's/^Verification: *//p' | head -1)
    echo "   $v: ${proto:-no handshake}, $kind, signature ${sig:-?}, verification ${ver:-?}"
    [ "$ver" = OK ] && [ -n "$proto" ] || fail=1
  done
  echo "   request: $(get "$host" | openssl s_client -quiet -connect "$host:443" \
    -servername "$host" -CAfile "/certs/$host.crt" 2>/dev/null | grep -m1 '^Host:')"
done

echo "== no SNI: the default certificate"
openssl s_client -connect www.example.com:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -subject
exit $fail
