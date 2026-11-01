# Passthrough host with maglev

A passthrough host copies bytes without terminating TLS. From 0.8.9 it can pick
its server by client address with `maglev` or `ring_hash`, so one client keeps
landing on the same server. **Needs Synapse 0.8.9 or later.**

Things to know:

- On a passthrough host `lb.key` is `client_ip` or absent. Any other key is
  refused when the file loads, as is `least_request`.
- The client address is the socket peer, or the source in the PROXY protocol
  header when `proxy.protocol.enabled` is on. `proxy.trusted_proxies` does not apply.
- This example passes plain HTTP (`http:`, matched by the Host header) so the
  back-end can answer with its name. A `tls:` wire, matched by SNI, takes the same
  `upstreams` and `lb` keys.
- `ring_hash` needs IP literals and a total weight of 10000 or less.

## Run

```sh
docker compose up -d
docker compose run --rm client-a     # one server, six times
docker compose run --rm client-b     # also one server, picked by its own address
docker compose --profile demo down
```

Set `SYNAPSE_IMAGE` to use your own image.
