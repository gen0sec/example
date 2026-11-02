# Certificates from certbot

Let certbot get and renew the certificate, and have Synapse serve it, without
a restart. **Needs Synapse 0.8.9 or later.** Earlier releases read the same
directory, but do not pick up a renewal made by certbot's link swap.

```yaml
proxy:
  listeners:
    - { name: http, address: "0.0.0.0:80", mode: http }
    - { name: https, address: "0.0.0.0:443", mode: tls }
  certificates: "/etc/letsencrypt/live"
  acme:
    enabled: false
```

```yaml
hosts:
  app.example.com:
    tls:
      terminate:
        cert: app.example.com
    paths:
      "/":
        upstream: whoami:80
        force_https: true
      "/.well-known/acme-challenge":
        upstream: webroot:80
```

## Things to know

- `proxy.certificates` is certbot's `live` directory: one subdirectory per
  domain, each with `fullchain.pem` and `privkey.pem`. The subdirectory is named
  after the first `-d` name given to certbot. `cert:` on the host names it.
- The directory MUST exist when Synapse starts. It MAY be empty. A missing
  directory is a start-up error (from 0.8.8). While it is empty, a TLS
  handshake fails with alert 40 and the log says that no certificates were found.
- Synapse watches the directory and reads the certificate at each handshake. A
  renewal needs no restart and no `SIGHUP`.
- `proxy.acme.enabled: false` turns the embedded ACME client off. It is
  deprecated.
- With it off, Synapse answers nothing on `/.well-known/acme-challenge` by
  itself. The request goes to the host's routes, so a second path sends it to
  the directory certbot writes the challenge file to (`--webroot`). Write the
  path without a trailing slash: with one, the route does not match and the
  challenge goes to the `/` upstream.
- Certbot needs the plaintext listener on port 80 to reach the host from the
  CA. The challenge cannot be answered on 443.
- `force_https: true` on `/` redirects every other request on port 80 to HTTPS,
  so the app is not served in clear. The challenge route has no `force_https`
  and stays plain HTTP. The redirect goes to the first `tls` listener's port
  (443); set `proxy.https_redirect_port` if clients reach HTTPS on another
  port, as the demo's `8443` mapping does from the host.
- Put the challenge route in before the first issue. Without it the challenge
  falls to `/` and is redirected to HTTPS, where there is no certificate yet.
- `certbot renew` is meant to run from cron or a timer. Run it with
  `--no-random-sleep-on-renew` when you test it by hand, or it waits up to
  several minutes.

## Run

The demo uses [Pebble](https://github.com/letsencrypt/pebble), a test ACME
server, so nothing reaches Let's Encrypt. Docker and Compose are needed.

```sh
cd use-cases/certbot
./make-certs.sh                       # a test certificate for Pebble's API
docker compose up -d
docker compose run --rm client        # before: no certificate yet
docker compose run --rm certbot       # issue
docker compose run --rm client        # after: the issued chain
```

To renew at once, and see that Synapse keeps running:

```sh
docker inspect -f '{{.State.StartedAt}}' $(docker compose ps -q synapse)
docker compose run --rm --entrypoint certbot certbot \
  renew --force-renewal --no-random-sleep-on-renew
docker compose run --rm client
docker inspect -f '{{.State.StartedAt}}' $(docker compose ps -q synapse)
docker compose down -v
```

The image is the 0.8.9 release image. To use a build of your own, set
`SYNAPSE_IMAGE`.

### What it prints

Before issuing, the handshake fails, plain HTTP on `/` is redirected, and the
challenge path reaches the webroot (404, no file yet):

```
== the certificate on app.example.com:443
...SSL alert number 40
== a request on http
HTTP/1.1 301 Moved Permanently
Location: https://app.example.com:443/
== the challenge path on http, with no file behind it
  HTTP/1.1 404 Not Found
```

Certbot issues through port 80:

```
Requesting a certificate for app.example.com
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/app.example.com/fullchain.pem
```

Synapse then serves the chain, and it verifies against Pebble's root:

```
serial=438B3F45B317B805
issuer=CN=Pebble Intermediate CA 7fb12e
DNS:app.example.com
Verification: OK
```

After the forced renewal the serial has changed and the container's start time
is the same as before (`2026-11-02T12:56:46.334774266Z` in both reads):

```
serial=7E3AAB75D18199E5
```

The serials, the issuer name and the dates differ on every run.

Synapse loads the first certificate when certbot creates its directory under
`/etc/letsencrypt/live`, so it is served without waiting for a renewal. Builds
before this fix, 0.8.9-rc.2 and earlier, could miss a first certificate:
certbot makes the directory and its links within a fraction of a millisecond,
and under load Synapse sometimes saw only the directory. The handshake then
failed with alert 40 until the next change in the directory (the forced renewal
loaded it). If the "after" check shows alert 40 on such a build, look for
`Certificate changed` in the log and update.

With the fixed build, the first certificate was served at the first poll in 10
of 10 runs of this demo, and in 10 of 10 runs with Synapse sharing one CPU with
two busy loops. The same starved runs on a build without the fix served it 1
time in 10.

### What goes wrong

Without the challenge path in the routes, the request goes to `/`, which
redirects it to HTTPS, where there is no certificate yet. The CA reports:

```
Type:   connection
Detail: Get "https://app.example.com:443/.well-known/acme-challenge/...":
remote error: tls: handshake failure
```

Without the `live` directory, Synapse does not start:

```
proxy failed to start: listener "https" (0.0.0.0:443, mode=tls): proxy.certificates directory "/etc/letsencrypt/live" does not exist; fix or create it, or remove proxy.certificates
```

That is why `docker-compose.yml` creates it first.

## For production

- Remove the `pebble`, `client` and `init` services, `REQUESTS_CA_BUNDLE` and
  the `--server` flag. Certbot then uses Let's Encrypt.
- Replace `--email admin@example.com` with your own address, or use
  `--register-unsafely-without-email`. Let's Encrypt refuses `example.com`
  contacts. This was not tried against Let's Encrypt.
- Use your own host name for `-d`, for the `hosts:` key and for `cert:`.
- Keep `/etc/letsencrypt` on a volume that Synapse mounts read-only and certbot
  mounts read-write, and run `certbot renew` from a timer.
- Port 80 MUST reach Synapse from the internet: the CA fetches the challenge
  there. Keep `force_https: true` on `/` and leave it off the challenge route.
  That redirects the app to HTTPS and keeps the challenge on plain HTTP.

## Not checked here

The set was run against Pebble only. It was not run against Let's Encrypt, and
the published 0.8.9 image was not pulled: the run used a build of the 0.8.9
branch that includes the first-certificate fix.

## Files

- `config.yaml`, `upstreams.yaml`, `security_rules.yaml`: the Synapse set.
- `docker-compose.yml`: Synapse, a test back-end, the webroot, Pebble, certbot.
- `nginx.conf`: serves the webroot.
- `pebble-config.json`, `make-certs.sh`: the test ACME server.
- `demo.sh`: what the `client` service prints.
