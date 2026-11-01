# Forwarded headers, HSTS, Via and a request ID

What Synapse adds to, or takes from, a request on its way to the back-end, and
the HSTS header it adds to the response. **Needs Synapse 0.8.9 or later.** The
`proxy:` keys are read at start: a change takes effect on restart, not on SIGHUP.

| Setting | Where | What it does |
|---|---|---|
| `xff_mode` | `config.yaml` `proxy:` | `replace` (default): the client address alone. `append`: `<client's value>, <address>`. `accept`: keep the client's value, add the address only if none was sent |
| `xff_exempt_networks` | `config.yaml` `proxy:` | a request whose TCP peer is in the list gets no `X-Forwarded-For` handling |
| `forwarded_proto` | `config.yaml` `proxy:` | `X-Forwarded-Proto`: `https` on a TLS listener, `http` on a plain one. On by default |
| `via`, `via_pseudonym` | `config.yaml` `proxy:` | `append` adds this hop to `Via`, request and response. Off by default |
| `request_id_header` | `config.yaml` `proxy:` | sends a request ID upstream under this name |
| `hsts` | `upstreams.yaml` | `Strict-Transport-Security` for TLS clients; top level or host; `"off"` on a host drops it |

Things to know:

- `append` and `accept` let a direct client forge `X-Forwarded-For`. Use them
  only behind a hop you control, and exempt only hops that set the header themselves.
- The exemption looks at the TCP peer, not at a PROXY-protocol source.
- A client-sent request ID is kept only when the peer is listed in an explicit
  `proxy.trusted_proxies` entry; otherwise it is replaced.
- `hsts` is added to TLS responses only, never to plain HTTP, redirects or block pages.
  `preload: true` needs `max_age` of at least 31536000 and `include_subdomains: true`.
- Name reserved headers (`Host`, `Authorization`, `X-Forwarded-For` ...) in
  `request_id_header` and the file is refused at start.

## Run

```sh
./make-certs.sh
docker compose --profile demo up -d
H='Host: app.example.com'
# client-a is an ordinary client; client-b (172.30.6.22) is in xff_exempt_networks.
docker compose exec client-a curl -s -H "$H" -H 'X-Forwarded-For: 1.2.3.4' -H 'X-Request-Id: mine' http://172.30.6.10:8080/ | grep -iE '^(x-forwarded|via|x-request)'
# X-Forwarded-For: 1.2.3.4, 172.30.6.21     <- append
# X-Forwarded-Proto: http
# X-Request-Id: req_...                      <- replaced
# Via: 1.1 synapse
docker compose exec client-b curl -s -H "$H" -H 'X-Forwarded-For: 1.2.3.4' http://172.30.6.10:8080/ | grep -i '^x-forwarded-for'
# X-Forwarded-For: 1.2.3.4                   <- exempt peer, untouched
docker compose exec client-a curl -skD- -o /dev/null --resolve app.example.com:8443:172.30.6.10 https://app.example.com:8443/ | grep -i strict
# strict-transport-security: max-age=31536000; includeSubDomains
docker compose --profile demo down
```

Set `xff_mode` to `replace` or `accept` in `config.yaml`, restart with
`docker compose restart synapse`, and send the same request to compare. Set
`SYNAPSE_IMAGE` to use your own image.
