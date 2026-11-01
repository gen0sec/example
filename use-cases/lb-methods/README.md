# Every load-balancing method on a terminated route

One route per `lb.method`, over the same three servers. A route with no `lb:`
block is `round_robin`. `maglev`, `ring_hash` and `least_request` need
**Synapse 0.8.9 or later**.

| Path | Method | Picks the server |
|---|---|---|
| `/round-robin` | `round_robin` | rotates by weight |
| `/weighted` | `weighted_round_robin` | rotates by weight (here 1:2:3) |
| `/random` | `random` | a weighted random draw per request |
| `/by-client` | `maglev` | a hash of the client address (the default key) |
| `/by-header` | `maglev` | a hash of `header:x-tenant` |
| `/by-cookie` | `ring_hash` | a hash of `cookie:session`, on a ketama ring |
| `/by-path` | `ring_hash` | a hash of the request path |
| `/consistent` | `consistent` | another name for `ring_hash` |
| `/least` | `least_request` | the less loaded of two servers drawn by weight |

Things to know:

- `lb.key` is `client_ip`, `path`, `header:<name>` or `cookie:<name>`, and only
  with `maglev` or `ring_hash`. A request with no key is served by the weighted rotation.
- `ring_hash` needs IP literals, not host names, and a total weight of 10000 or
  less. That is why the back-ends here have fixed addresses.
- A route with no `lb.key` takes `proxy.sticky_sessions.key` from the upstreams
  file, then `client_ip`.
- Behind a load balancer or a Docker NAT every client looks like one address:
  set `proxy.trusted_proxies`, or `client_ip` sends all traffic to one server.
- A host-level `lb:` next to `paths:` is the default of every path without its own.

## Run

```sh
docker compose up -d
H='Host: app.example.com'
# 60 requests per method, counted by server:
for p in round-robin weighted random consistent least; do
  echo -n "/$p: "; for i in $(seq 60); do curl -s -H "$H" localhost:8090/$p | grep Hostname; done | sort | uniq -c | tr '\n' ' '; echo
done
# /round-robin: 20 web1, 20 web2, 20 web3     /weighted: 10, 20, 30
# /random: about 10, 20, 30 (it is a draw)    /consistent: all 60 on one server
for i in 1 2 3; do curl -s -H "$H" -H 'x-tenant: acme'   localhost:8090/by-header | grep Hostname; done   # one server, three times
for i in 1 2 3; do curl -s -H "$H" -H 'x-tenant: globex' localhost:8090/by-header | grep Hostname; done   # another key, often another server
docker compose down
```

The image is `registry.gen0sec.com/gen0sec/synapse:0.8.9`. To use your own
build, set `SYNAPSE_IMAGE`. Check the files without running them with
`synapse --check-config -c config.yaml --upstream-conf upstreams.yaml`.
