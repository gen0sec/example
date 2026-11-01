# Re-encrypt to a TLS back-end

From 0.8.9 Synapse checks the certificate chain and name of a TLS back-end on
terminated routes. Before, it accepted any certificate. `upstream_tls` sets how,
at the top level, on a host or on a path, one field at a time. It also holds the
client certificate for back-ends that ask for one (mTLS).
**Needs Synapse 0.8.9 or later.**

| Path | `upstream_tls` | Result |
|---|---|---|
| `/verified` | `ca` | 200: chain and name check out |
| `/mtls` | `ca`, `client_cert`, `client_key` | 200: the back-end accepts the client certificate |
| `/untrusted` | none | 404: the probe marks the server down |
| `/untrusted-no-probe` | none, `health_check: none` | 502: the connect fails the check |
| `/unverified` | `verify: false` | 200: no check at all |

Things to know:

- `ca` is a PEM file that **replaces** the system trust store for the route.
  Without it, the system store is used.
- The name checked is the configured back-end address, here `backend.internal`.
  An IP-literal back-end needs the IP in the certificate's SANs.
- `client_cert` and `client_key` go together. Keep the key at mode 0600. Synapse
  warns about a key anyone can read.
- The health probe uses the same settings and presents the client certificate.
  A back-end whose certificate fails, or that refuses the handshake, is marked
  down and the log says so once per server per minute.
- **Before a rollback, remove `client_cert` and `client_key`:** older versions
  refuse a file that holds them.
- The files are read when the configuration loads, from the directory Synapse
  starts in (`working_dir` in the compose file). After you change one, send SIGHUP.

## Run

```sh
./make-certs.sh                 # a test CA, a back-end certificate and a client certificate, in ./certs
docker compose up -d
for p in verified mtls untrusted untrusted-no-probe unverified; do
  curl -s -o /dev/null -w "/$p %{http_code}\n" -H 'Host: app.example.com' localhost:8084/$p
done
docker compose down
```

Set `SYNAPSE_IMAGE` to use your own image.
