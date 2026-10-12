# reverse-proxy-waf

Synapse as a TLS-terminating reverse proxy with a WAF and access rules, in
front of one backend. It runs from local files and needs no Gen0Sec API key.

## Goal

Receive HTTP and HTTPS requests for `app.example.com`, block the ones that
match a WAF or access rule, and proxy the rest to a backend. After this you
have a working proxy you can point at your own backend by changing one line.

## What you need

- Synapse, installed as the proxy or as a container. Installation needs a
  repository credential from the Gen0Sec dashboard; follow the
  [installation guide](https://docs.gen0sec.com/docs/client/installation).
- `openssl` and `curl`.
- For docker compose: Docker with Compose v2, logged in to
  `registry.gen0sec.com` with that credential.

## Files

| File | What it does |
|---|---|
| `config.yaml` | Proxy mode, listeners on 8080 (HTTP) and 8443 (HTTPS), certificate directory, logging of block decisions to stdout |
| `upstreams.yaml` | Schema v2 routes: `app.example.com` terminates TLS with your certificate and proxies `/` to `whoami:80` |
| `security_rules.yaml` | An access rule (blocks two example address ranges) and three WAF rules (`/admin`, SQL injection, script injection in the query string) |
| `docker-compose.yml` | Synapse plus a demo backend, `traefik/whoami`, which echoes the request it receives |

## Make a certificate

Both ways of running need a certificate pair named after the host. This makes a
self-signed one for the demo; use your own for real traffic.

```sh
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -subj "/CN=app.example.com" -addext "subjectAltName=DNS:app.example.com" \
  -keyout certs/app.example.com.key -out certs/app.example.com.crt
```

## Run as a package

Copy the files and the `certs/` directory to `/etc/synapse/`, point the
`upstream:` line in `upstreams.yaml` at your backend (`host:port`), then run:

```sh
synapse -c /etc/synapse/config.yaml \
  --security-rules-config /etc/synapse/security_rules.yaml
```

For a service, put the same arguments in the unit that the package installs.
The ports in `config.yaml` are above 1024, so no root is needed. The demo
backend `whoami` only exists in docker compose; outside it, change `upstream:`
first.

## Run with docker compose

```sh
docker login registry.gen0sec.com
# make the certificate as above, then:
docker compose up
```

The image tag in `docker-compose.yml` is pinned.

## Certificates from Let's Encrypt

Synapse has an embedded ACME http-01 client (`proxy.acme`), but it is
deprecated and will be removed in a future release, so this example leaves it
off. Get the certificate with an external ACME client such as certbot instead,
and have it write `app.example.com.crt` and `.key` into the `certs/` directory
(the configured `proxy.certificates` path), renewing there. Certificate files
are what `tls.terminate.cert` selects, so nothing else changes.

## See it working

In another terminal. `Host:` selects the route; no DNS is needed.

A proxied request returns 200 and the backend's answer:

```sh
curl -i -H 'Host: app.example.com' http://127.0.0.1:8080/
```

The same over HTTPS (`-k` because the certificate is self-signed):

```sh
curl -ik --resolve app.example.com:8443:127.0.0.1 https://app.example.com:8443/
```

A request the WAF blocks returns 403:

```sh
curl -i -H 'Host: app.example.com' http://127.0.0.1:8080/admin
curl -i -H 'Host: app.example.com' 'http://127.0.0.1:8080/?q=1%27%20union%20select%20password'
```

Each block is one line on Synapse's standard output:

```
{"ts":"...","layer":"waf","action":"block","source":"waf","rule_id":"waf-block-admin","rule_msg":"Block /admin (response=403)","src_ip":"127.0.0.1",...}
```

A host that no route names returns 404. To see the access rule fire, add
`127.0.0.2` to `block.ips` in `security_rules.yaml` and run
`curl --interface 127.0.0.2 -H 'Host: app.example.com' http://127.0.0.1:8080/`;
it returns 403 and logs a line with `"layer":"access_rules"` and
`"rule_msg":"access_rules block ip:127.0.0.2"`. Rule files are reloaded while
Synapse runs, so no restart is needed.

## With a Gen0Sec API key

Set `platform.api_key` in `config.yaml` (a placeholder is not a key: use the one
from the dashboard's API keys page). Synapse then also uses rules and threat
data from the platform, and `security_rules.yaml` is only the fallback used
when no key is set. This example was run and checked without a key; nothing
here was verified with one.

## Limits

- The demo listens on 8080 and 8443 so it runs unprivileged. In production use
  80 and 443, and set `https_redirect_port` to match.
- The certificate for a host is chosen by file name in the `certificates`
  directory (`tls.terminate.cert: app.example.com` means `app.example.com.crt`).
  A full path in `cert:` is not looked up and the default certificate is served
  instead. A client whose SNI matches no certificate also gets the default one.
- The embedded ACME client is deprecated and not used here; see above.
- The rules are a starting point, not a complete defence. The SQL and script
  injection rules look only at the query string, not at bodies or headers.
- The rules here do not rate limit; a rate-limit action needs more than a rule
  file in this setup and is not covered.
- The firewall and packet capture are off. This is the proxy only.
