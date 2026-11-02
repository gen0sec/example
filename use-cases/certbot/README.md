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

Before issuing, the handshake fails and the challenge path reaches the webroot
(404, no file yet):

```
== the certificate on app.example.com:443
...SSL alert number 40
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
serial=5CDE5864DFDD051B
issuer=CN=Pebble Intermediate CA 6a73b6
DNS:app.example.com
Verification: OK
```

After the forced renewal the serial has changed and the container's start time
is the same as before (`2026-11-02T12:44:47.182364177Z` in both reads):

```
serial=3AA7426B5BC3656B
```

The serials, the issuer name and the dates differ on every run.

### What goes wrong

Without the challenge path in the routes, the request goes to `/`, and the CA
reads another server's answer:

```
Type:   unauthorized
Detail: The key authorization file from the server did not match this challenge
"..." != "Hostname: whoami ..."
```

Without the `live` directory, Synapse does not start:

```
proxy failed to start: listener "https" (0.0.0.0:443, mode=tls): proxy.certificates directory "/etc/letsencrypt/live" does not exist; fix or create it, or remove proxy.certificates
```

That is why `docker-compose.yml` creates it first.

## For production

- Remove the `pebble`, `client` and `init` services, `REQUESTS_CA_BUNDLE` and
  the `--server` flag. Certbot then uses Let's Encrypt.
- Use your own host name for `-d`, for the `hosts:` key and for `cert:`.
- Keep `/etc/letsencrypt` on a volume that Synapse mounts read-only and certbot
  mounts read-write, and run `certbot renew` from a timer.
- The host must be reachable on port 80 from the internet.

## Not checked here

The set was run against Pebble only. It was not run against Let's Encrypt, and
the published 0.8.9 image was not pulled: the run used a 0.8.9 build of the
binary.

## Files

- `config.yaml`, `upstreams.yaml`, `security_rules.yaml`: the Synapse set.
- `docker-compose.yml`: Synapse, a test back-end, the webroot, Pebble, certbot.
- `nginx.conf`: serves the webroot.
- `pebble-config.json`, `make-certs.sh`: the test ACME server.
- `demo.sh`: what the `client` service prints.
