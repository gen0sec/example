# Every load-balancing method on a passthrough host

A passthrough host copies bytes without terminating TLS. One host per
`lb.method`, over the same three servers. `maglev` and `ring_hash` on a
passthrough host need **Synapse 0.8.9 or later**.

| Host | Method | Picks the server |
|---|---|---|
| `pt-round-robin.example.com` | `round_robin` | rotates; **weights are ignored** |
| `pt-weighted.example.com` | `weighted_round_robin` | rotates by weight (here 1:2:3) |
| `pt-random.example.com` | `random` | a uniform draw; weights are ignored |
| `pt-maglev.example.com` | `maglev` | a hash of the client address |
| `pt-ring-hash.example.com` | `ring_hash` (or `consistent`) | a hash of the client address, on a ketama ring |

Things to know:

- `least_request` is refused when the file loads. On a passthrough host `lb.key`
  is `client_ip` or absent, and any other key is refused.
- The client address is the socket peer, or the source in the PROXY protocol
  header when `proxy.protocol.enabled` is on. `proxy.trusted_proxies` does not apply.
- This example passes plain HTTP (`http:`, matched by the Host header) so the
  back-end can answer with its name. A `tls:` wire, matched by SNI, takes the same
  `upstreams` and `lb` keys.
- `ring_hash` needs IP literals and a total weight of 10000 or less.

## Run

Two client containers with their own addresses call each host twelve times:

```sh
docker compose up -d
for h in pt-round-robin pt-weighted pt-random pt-maglev pt-ring-hash; do
  echo "== $h"
  docker compose run --rm -e HOST=$h.example.com client-a | sort | uniq -c
  docker compose run --rm -e HOST=$h.example.com client-b | sort | uniq -c
done
# round-robin: 4 / 4 / 4   weighted: 2 / 4 / 6   random: varies
# maglev, ring_hash: all 12 on one server per client
docker compose --profile demo down
```

Set `SYNAPSE_IMAGE` to use your own image.
