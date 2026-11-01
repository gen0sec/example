# Load balancing by a request key

Pick the back-end from the request instead of rotating: `maglev` and
`ring_hash` hash a key, so one client, tenant, cookie or path keeps landing on
the same server. `least_request` sends a request to the less loaded server.
**Needs Synapse 0.8.9 or later.**

| Path | Method | Key |
|---|---|---|
| `/by-client` | `maglev` | the client address (the default key) |
| `/by-header` | `maglev` | `header:x-tenant` |
| `/by-cookie` | `ring_hash` | `cookie:session` |
| `/by-path` | `ring_hash` | `path` |
| `/least` | `least_request` | none |

Things to know:

- `lb.key` is `client_ip`, `path`, `header:<name>` or `cookie:<name>`. A request
  that carries no key falls back to the weighted rotation.
- `ring_hash` (also written `consistent`) needs IP literals, not host names, and a
  total weight of 10000 or less. That is why the back-ends here have fixed addresses.
- A route with no `lb.key` takes `proxy.sticky_sessions.key` from the upstreams
  file, then `client_ip`.
- Behind a load balancer or a Docker NAT every client looks like one address:
  set `proxy.trusted_proxies`, or `client_ip` sends all traffic to one server.

## Run

```sh
docker compose up -d
H='Host: app.example.com'
for i in 1 2 3; do curl -s -H "$H" -H 'x-tenant: acme'   localhost:8090/by-header | grep Hostname; done   # same server 3 times
for i in 1 2 3; do curl -s -H "$H" -H 'x-tenant: globex' localhost:8090/by-header | grep Hostname; done   # a different key, often a different server
docker compose down
```

The image is `registry.gen0sec.com/gen0sec/synapse:0.8.9`. To use your own
build, set `SYNAPSE_IMAGE`. Check the files without running them with
`synapse --check-config -c config.yaml --upstream-conf upstreams.yaml`.
