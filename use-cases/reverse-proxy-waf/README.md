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
  Kubernetes is covered by the coming `kubernetes` use case, not here.
- `openssl` and `curl`.
- For docker compose: Docker with Compose v2, logged in to
  `registry.gen0sec.com` with that credential.

## Files

| File | What it does |
|---|---|
| `config.yaml` | Proxy mode, listeners on 8080 (HTTP) and 8443 (HTTPS), certificate directory, block events written to `events.log` as JSON |
| `upstreams.yaml` | Schema v2 routes: `app.example.com` terminates TLS with your certificate and proxies `/` to `whoami:80` |
| `security_rules.yaml` | An access rule (blocks two example address ranges) and four WAF rules (`/admin`, SQL injection, script injection in the query string, a rate limit on `/login`) |
| `docker-compose.yml` | Synapse plus a demo backend, `traefik/whoami`, which echoes the request it receives. It mounts this directory at `/etc/synapse` and `./logs` at `/var/log/synapse` |

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

Copy `config.yaml`, `upstreams.yaml`, `security_rules.yaml` and the `certs/`
directory to `/etc/synapse/`, and point the `upstream:` line in
`upstreams.yaml` at your backend (`host:port`). The demo backend `whoami` only
exists in docker compose.

The package's service unit runs
`synapse --daemon --config /etc/synapse/config.yaml`. That is enough: a
relative `--security-rules-config` (its default is `security_rules.yaml`) is
looked up next to the config file, so `/etc/synapse/security_rules.yaml` is
found without changing the unit. Restart the service to apply the files:

```sh
sudo systemctl restart synapse-proxy
```

`--daemon` detaches Synapse from the terminal and discards its standard output,
so nothing reaches journald. That is why `config.yaml` turns on
`file_logging_enabled` and writes block events to
`/var/log/synapse/events.log`; look there (see "See it working").

To try it by hand instead, run it in the foreground. The log directory
`/var/log/synapse` must be writable, so use `sudo` or change the two
`/var/log/synapse` paths in `config.yaml`:

```sh
sudo synapse -c /etc/synapse/config.yaml \
  --security-rules-config /etc/synapse/security_rules.yaml
```

The ports in `config.yaml` are above 1024, so a normal user could bind them.

## Run with docker compose

```sh
echo "$GEN0SEC_KEY" | docker login registry.gen0sec.com -u x --password-stdin
# make the certificate as above, then:
docker compose up
```

`$GEN0SEC_KEY` is the repository credential from the Gen0Sec dashboard (see
the installation guide). The compose file mounts this directory as
`/etc/synapse` (a directory, not single files, so edits to the rule files are
picked up while Synapse runs) and `./logs` as `/var/log/synapse`. The image tag
is pinned.

From the host, the proxy sees your requests as coming from the Docker network
gateway, not from `127.0.0.1`. Block events in `logs/events.log` show that
address as `src_ip`.

## Certificates from Let's Encrypt

Synapse has an embedded ACME http-01 client (`proxy.acme`), but it is
deprecated and will be removed in a future release, so this example leaves it
off. Get the certificate with an external ACME client such as certbot instead.

`proxy.certificates` may point straight at certbot's live directory. Synapse
reads `<domain>/fullchain.pem` and `<domain>/privkey.pem` for every
subdirectory and names the certificate after the directory, so
`tls.terminate.cert: app.example.com` selects
`/etc/letsencrypt/live/app.example.com/`:

```yaml
proxy:
  certificates: "/etc/letsencrypt/live"
```

In docker compose, mount `/etc/letsencrypt/live` and `/etc/letsencrypt/archive`
(the live files are links into it) read-only at the same paths. Renewals then
replace the files in place.

## See it working

In another terminal. `Host:` selects the route; no DNS is needed. The commands
use the ports from `config.yaml`; with docker compose they work unchanged from
the host.

A proxied request returns 200 and the backend's answer:

```sh
curl -i -H 'Host: app.example.com' http://127.0.0.1:8080/
```

The same over HTTPS (`-k` because the certificate is self-signed):

```sh
curl -ik --resolve app.example.com:8443:127.0.0.1 https://app.example.com:8443/
```

A request the WAF blocks returns 403. The `/admin` rule lower-cases the path,
so `/ADMIN` is blocked as well:

```sh
curl -i -H 'Host: app.example.com' http://127.0.0.1:8080/admin
curl -i -H 'Host: app.example.com' http://127.0.0.1:8080/ADMIN
curl -i -H 'Host: app.example.com' 'http://127.0.0.1:8080/?q=1%27%20union%20select%20password'
```

Each block is one JSON line in `events.log` (`/var/log/synapse/events.log` for
the package, `logs/events.log` next to the compose file):

```
{"ts":"...","layer":"waf","action":"block","source":"waf","rule_id":"waf-block-admin","rule_msg":"Block /admin (response=403)","src_ip":"127.0.0.1",...}
```

`/login` is rate limited to 3 requests per client per 60 seconds. The fourth
request returns 429, and so does every one after it for the next 60 seconds:

```sh
for i in 1 2 3 4; do
  curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: app.example.com' http://127.0.0.1:8080/login
done
```

This prints `200`, `200`, `200`, `429`. (The demo backend answers 200 on any
path.) Each refused request is logged with `"action":"ratelimit"` and
`"rule_id":"waf-ratelimit-login"`.

A host that no route names returns 404.

### The access rule

Add your address to `block.ips` in `security_rules.yaml` and Synapse reloads
the file within a few seconds, with no restart.

- Package: add `127.0.0.2`, then run
  `curl --interface 127.0.0.2 -H 'Host: app.example.com' http://127.0.0.1:8080/`.
- docker compose: the proxy sees the gateway of the compose network, so add
  that address and run the plain request from the host. Find it with
  `docker network inspect reverse-proxy-waf_default --format '{{(index .IPAM.Config 0).Gateway}}'`.
  This blocks every request from your host, including `/`, until you remove it.

The request returns 403 and `events.log` gets a line with
`"layer":"access_rules"` and a `"rule_msg"` such as
`"access_rules block ip:127.0.0.2"`. Remove the address again to
undo it.

## With a Gen0Sec API key

Set the key with the `API_KEY` environment variable, never in a file you commit
(for the packaged service, put `Environment=API_KEY=...` in a drop-in created
with `systemctl edit synapse-proxy`; with docker compose, run
`API_KEY=... docker compose up`, which the compose file passes through).

With a key, Synapse takes its rules and threat data from the platform and does
not read the local `security_rules.yaml`. The access rule and the four WAF rules
in this directory then no longer apply; define them in the platform instead.
The file is only used when no key is set. This example was run and checked
without a key; nothing here was verified with one.

## Limits

- The demo listens on 8080 and 8443 so it runs unprivileged. In production use
  80 and 443, and set `https_redirect_port` to match.
- The certificate for a host is chosen by file name in the `certificates`
  directory (`tls.terminate.cert: app.example.com` means `app.example.com.crt`,
  or a `app.example.com/` directory holding `fullchain.pem` and `privkey.pem`).
  A full path in `cert:` is not looked up and the default certificate is served
  instead. A client whose SNI matches no certificate also gets the default one.
- The embedded ACME client is deprecated and not used here; see above.
- The rules are a starting point, not a complete defence. The SQL and script
  injection rules look only at the query string, not at bodies or headers.
- The firewall and packet capture are off. This is the proxy only.
