# TLS private keys in an HSM

Keep the private keys of your TLS certificates in a hardware security module
(HSM), or any other PKCS#11 token, and have Synapse sign handshakes with them.
The key never leaves the device. **Needs Synapse 0.8.9 or later.**
Earlier releases cannot use a `pkcs11:` key.

```yaml
proxy:
  certificates: "/certs"
  default_certificate: "www.example.com"
  hsm:
    modules:
      - /usr/lib/softhsm/libsofthsm2.so
    pin_file: /hsm/pin
    retry_interval_secs: 30
    on_failure: fail
```

```yaml
hosts:
  www.example.com:
    tls:
      terminate:
        cert: www.example.com
```

The certificates stay on disk. Beside `www.example.com.crt` sits
`www.example.com.key`, and its one line says where the key is:

```
pkcs11:token=synapse;object=www;type=private
```

## Things to know

- A `.key` file whose first line is a `pkcs11:` URI is an HSM key. A PEM key in
  a `.key` file is a software key, as before. Both kinds can sit in one
  directory, as in the demo (`static.example.com`).
- `cert:` in `upstreams.yaml` is the certificate's **name**, the file stem in
  `proxy.certificates`, never a path. There is no `key:` under `terminate`: the
  key is found beside the certificate.
- The URI MUST NOT carry the PIN. `pin-value` and `pin-source` are rejected.
  The PIN is in `proxy.hsm.pin_file`: a regular, non-empty file, owned by the
  service user or root, mode `0600`. Synapse refuses the file otherwise, and
  its errors name the path, never the content. With systemd, hand the file over
  with `LoadCredential=` and point `pin_file` at
  `/run/credentials/<unit>/<name>`. `PROXY_HSM_PIN_FILE` overrides the key.
- `modules` is tried in order, and the first that loads and yields the key
  wins. List a second module for failover.
- Synapse reaches the token through the OpenSSL `pkcs11` provider. `provider_dir`
  is the directory of its `pkcs11.so`; unset, the usual distribution
  directories are probed. On Debian and Ubuntu it is the `pkcs11-provider`
  package, which the deb and rpm packages suggest. A container image that ships
  it needs nothing more than the vendor's PKCS#11 module.
- A key in the HSM is never read from a file: there is no software fallback.
- `retry_interval_secs` is how often, in seconds, every HSM key signs a test
  message. When one cannot, Synapse reloads the certificates through `modules`,
  so a recovered HSM is picked up within one interval. `0` turns the probe off.
- `on_failure` is what a host gets when its HSM key cannot be loaded. `fail`
  (the default) refuses the TLS handshake for its names. `fallback` serves the
  default certificate and logs a warning. During an outage a reload keeps the
  last working context until its certificate expires, in both modes.
- The `hsm` block is read at start-up. Changing `modules`, `pin_file` or
  `retry_interval_secs` needs a restart. A replaced PIN file is picked up at
  the next certificate load.
- The built-in ACME client makes software keys. For a certificate on an HSM
  key, make the CSR on the device and have certbot issue from it with
  `certbot certonly --csr`. This set does not build that.

## Run

The demo uses SoftHSM, a software PKCS#11 token, so no hardware is needed.
Docker and Compose v2 are needed.

```sh
cd use-cases/hsm-tls-keys
docker compose up -d --build
docker compose run --rm client
```

Or all of it, with the log check, in one go: `./demo.sh`.

What runs:

- `token` (from `Dockerfile`, target `token`) runs `make-token.sh` once: it
  initialises a SoftHSM token named `synapse` with a random PIN, puts an RSA
  key (`www`) and an EC P-256 key (`api`) on it, and writes a certificate and a
  `.key` file with the URI for each. It also writes a plain software key and
  certificate (`static`), and the PIN file with mode `0600`.
- `synapse` is the Synapse image plus SoftHSM's module, built from
  `Dockerfile`, target `synapse`. The Synapse image has no shell and no
  package manager, so `libsofthsm2.so` is copied in from a Debian stage. With a
  real HSM you install your vendor's module instead.
- `client` connects to each host with `openssl s_client`, over TLS 1.2 and
  TLS 1.3, and sees only the certificates, not the token or the PIN.

`docker-compose.yml` builds on `SYNAPSE_IMAGE`; set it to use a build of your
own. The host maps ports 8085 (HTTP) and 8443 (HTTPS).

### What it prints

```
== www.example.com: key line in www.example.com.key
pkcs11:token=synapse;object=www;type=private
   tls1_2: TLSv1.2, rsaEncryption, signature RSA-PSS, verification OK
   tls1_3: TLSv1.3, rsaEncryption, signature RSA-PSS, verification OK
   request: Host: www.example.com
== api.example.com: key line in api.example.com.key
pkcs11:token=synapse;object=api;type=private
   tls1_2: TLSv1.2, id-ecPublicKey, signature ECDSA, verification OK
   tls1_3: TLSv1.3, id-ecPublicKey, signature ECDSA, verification OK
   request: Host: api.example.com
== static.example.com: key line in static.example.com.key
-----BEGIN PRIVATE KEY-----
   tls1_2: TLSv1.2, id-ecPublicKey, signature ECDSA, verification OK
   tls1_3: TLSv1.3, id-ecPublicKey, signature ECDSA, verification OK
   request: Host: static.example.com
== no SNI: the default certificate
subject=CN=www.example.com
```

The two HSM hosts have no private key on disk, only the URI, so every
handshake for them was signed by the token. `./demo.sh` then looks for the PIN
in the logs of all services and finds none.

To start over, remove the volumes:

```sh
docker compose down -v
```

### What goes wrong

- A `pkcs11:` key with no `proxy.hsm` block is an error at load.
- A PIN file that is group or world readable, empty, or not a regular file is
  refused, and the error names the rule that failed.
- With the token unreachable, `on_failure: fail` refuses the handshake with
  `unrecognized_name` for the names of that certificate. The software host is
  unaffected.

## For production

- **The demo imports its keys.** `make-token.sh` makes each key in software and
  imports it with `softhsm2-util --import`, so for a moment a copy of the
  private key is on disk. That is a shortcut for the demo. A real HSM makes the
  key on the device, non-extractable, and signs the certificate request there
  (`pkcs11-tool --keypairgen`, or the vendor's tool). Only the certificate
  comes out.
- Replace SoftHSM with your vendor's module in `proxy.hsm.modules`, and use a
  certificate from your CA.
- Keep the PIN file out of the configuration directory and out of version
  control, mode `0600`, and hand it to the service with `LoadCredential=`.
- **The demo passes the PINs on the command line.** `make-token.sh` gives
  `softhsm2-util` and `pkcs11-tool` the PIN and SO PIN as arguments, which
  other processes on the host can read. Set up a real token with the vendor's
  tool, typing the PINs at its prompt.
- Use your own host names for the `hosts:` keys, for `cert:` and for the
  certificate file names.
- Set `provider_dir` if the `pkcs11.so` of the provider is not in a
  distribution directory.

## Not checked here

The set was run against SoftHSM only, with RSA and EC keys over TLS 1.2 and
TLS 1.3, using a build of Synapse that has HSM keys. It was not run against a
hardware HSM, nor against a published image.

## Files

- `config.yaml`, `upstreams.yaml`: the Synapse set.
- `softhsm2.conf`: where SoftHSM keeps its token. Not needed with a real HSM.
- `docker-compose.yml`, `Dockerfile`: the token provisioner, Synapse with the
  SoftHSM module, a test back-end and the client.
- `make-token.sh`: makes the token, keys, certificates and PIN file.
- `client.sh`: what the `client` service prints.
- `demo.sh`: the demo end to end, with the check that the PIN is in no log.
