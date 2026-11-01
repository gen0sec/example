# Source address for back-end connections

`upstream_source` binds the connections Synapse opens to a back-end to a local
address, interface and port range, so the back-end, or a firewall in front of
it, sees a known source. **Needs Synapse 0.8.9 or later.**

```yaml
upstream_source:
  address: 172.30.4.10
  interface: eth1            # optional; a VRF works
  port_range: [40000, 40099] # optional; needs Linux 6.3 or later
```

Things to know:

- It is allowed at the top level, on a host and on a path. Fields layer one by
  one, and `null` clears an inherited field.
- Synapse opens a test socket when the file loads. A bad address, a missing
  interface or capability, or an old kernel fails the load and names the level.
  The check does not prove the back-end is reachable from that source.
- A bind that fails later answers 502 and logs a warning once a minute.
- The health probes of the route leave from `address` and `interface`, not from
  `port_range`.
- The back-end and the address must be the same IP family.

## Run

```sh
docker compose up -d
curl -s -H 'Host: app.example.com' localhost:8083/ | grep RemoteAddr
# RemoteAddr: 172.30.4.10:40005    <- the address and a port from the range
docker compose down
```

Set `SYNAPSE_IMAGE` to use your own image.
