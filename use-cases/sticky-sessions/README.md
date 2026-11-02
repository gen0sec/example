# Sticky sessions

Keep a client on the server it first got, with a signed cookie.
**Needs Synapse 0.8.9 or later.**

```yaml
proxy:
  sticky_sessions:
    enabled: true
    secret_file: sticky.key   # at least 32 bytes; the whole file is the key
```

Things to know:

- `secret_file` is required when `enabled` is true. Synapse 0.8.9 refuses to
  load the file without it, and a failed reload keeps the old configuration.
- The key file holds at least 32 bytes, and the whole file is the key, a
  trailing newline included. A missing file, an empty file and a short file each
  fail the load and name the file: `cannot read`, `is empty`, `holds 31 bytes; at
  least 32 are required`.
- Every response on a sticky route carries
  `backend_id=<id>.<mac>; Path=/; Max-Age=600; HttpOnly; SameSite=Lax`. It has no
  `Secure` and no `Domain`.
- A cookie that does not verify is ignored and the client gets a fresh one: a
  wrong or cut mac, an id without a mac, a cookie signed with another key, the
  old `address:port:ssl` form, and an id the matched route does not list.
- The order is: the cookie, then `lb.persistence`, then `lb.method`.
- Every node of a cluster must hold the same key file, or a client moved to
  another node is placed again.
- A reload (SIGHUP) reads the key again. After a key change every old cookie is
  ignored once and the clients are placed afresh.
- The setting is global, so it covers every route of every host in the file.
  `lb.key` and `proxy.sticky_sessions.key` are separate: that one is the default
  hash key for `maglev` and `ring_hash`.
- A v1 upstreams file with sticky sessions on does not load. Use `version: 2`.
  `synapse --check-config` does not report this yet.
- `secret_file` is read as written. A relative path resolves against the
  working directory of the process, so the compose file sets `working_dir`. In
  production give an absolute path, mode 0600, owned by the user Synapse runs
  as (root for the packages). The packaged unit cannot read a 0600 file that
  another user owns, and the load then fails with `cannot read`.

## Run

`make-certs.sh` writes a test key, `sticky.key`. It is test material: make a real
key once and copy the same file to every node.

```sh
./make-certs.sh
docker compose up -d
docker compose --profile demo run --rm client
docker compose --profile demo down
```

The demo shows a client without its cookie, the cookie, the same client with it,
and two cookies that do not verify:

```text
== no cookie: round robin
Hostname: web1
Hostname: web2
Hostname: web3
== the first response sets a signed cookie, <id>.<mac>
set-cookie: backend_id=2e2c38f482e21ba66add678268fc2ccd9ab89044fadd8bda48.3af418f700984ec7f254e98118633e9e; Path=/; Max-Age=600; HttpOnly; SameSite=Lax
== with that cookie: one server, six times
Hostname: web1
Hostname: web1
Hostname: web1
Hostname: web1
Hostname: web1
Hostname: web1
== the last digit of the mac changed: ignored, the next server, a fresh cookie
set-cookie: backend_id=90e374a7560bd7850266bdb6d07956fc4aa0533b06bec4b979.7a81f48f7df0a71cb9819018a0f161ed; Path=/; Max-Age=600; HttpOnly; SameSite=Lax
Hostname: web2
== the id without a mac: ignored the same way
set-cookie: backend_id=b22780b7c0c5810ac8101782a749cbb95d84ea9b6ae77eccfb.1df3d74d863d432ab912016ba59897c4; Path=/; Max-Age=600; HttpOnly; SameSite=Lax
Hostname: web3
```

Your cookies differ: the key is random. To see a key change, write a new
key beside the old one, move it into place and send SIGHUP:

```sh
(umask 077; head -c 32 /dev/urandom > sticky.key.new) && mv sticky.key.new sticky.key
docker compose kill -s HUP synapse
```

Moving the file keeps a load from reading a half-written key, and gives it the
new file's mode. Rerunning `make-certs.sh` does not rotate: it keeps an existing
key.

A client that sends its old cookie is placed again and gets a fresh one.

The demo listens on port 8088 of the Docker host. Set `SYNAPSE_IMAGE` to use
your own image.
