# Source-IP persistence

Pin a client address to the server it first got, whatever `lb.method` says.
**Needs Synapse 0.8.9 or later.**

```yaml
lb:
  method: round_robin
  persistence:
    kind: source_ip
    timeout_secs: 1800    # 1 to 604800
    capacity: 100000      # 1 to 10000000, about 100 bytes per pin
```

Things to know:

- The order is: the sticky cookie, then the pin, then `lb.method`.
- A restart empties the pins. A configuration reload keeps them.
- A pin lasts `timeout_secs` after the client's last request.
- Behind a load balancer set `proxy.trusted_proxies`, or every client shares one pin.
- A passthrough host takes `persistence` on each wire, with every method except
  `least_request`.

## Run

Two client containers with their own addresses call the pinned route and an
unpinned route over the same three servers:

```sh
docker compose up -d
docker compose run --rm -e URL=http://172.30.2.10:8080/pinned   client-a   # one server, six times
docker compose run --rm -e URL=http://172.30.2.10:8080/pinned   client-b   # its own pin
docker compose run --rm -e URL=http://172.30.2.10:8080/unpinned client-a   # rotates through all three
docker compose --profile demo down
```

A client on the Docker host appears as the bridge gateway address, so it
cannot show a split between clients; use the containers. Set `SYNAPSE_IMAGE` to
use your own image.
