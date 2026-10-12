# Upstreams reference

The upstreams file says which hosts Synapse serves and where each request
goes. These sets use the v2 schema (`version: 2`). Each directory is a config
set that `synapse --check-config` accepts: a `config.yaml` (proxy mode) and an
`upstreams.yaml` with every key explained.

| Directory | What it shows |
|---|---|
| [`hosts/`](./hosts/upstreams.yaml) | `default_host`, static and ACME certificates, wildcard names, binding a host to listeners |
| [`routes/`](./routes/upstreams.yaml) | Path routes, `match_expr` routes, rewrite, redirect, `force_https`, per-route options |
| [`headers-transforms/`](./headers-transforms/upstreams.yaml) | Header lists layered global, host and route; `transforms`; fingerprint headers |
| [`load-balancing/`](./load-balancing/upstreams.yaml) | Weights, `lb.method`, health checks, timeouts, sticky sessions |
| [`passthrough/`](./passthrough/upstreams.yaml) | TLS by SNI, plain HTTP by Host, both wires, PROXY protocol v2, tunnel limits |
| [`limits/`](./limits/upstreams.yaml) | `normalize_path`, URL and header limits, method allow-lists |

## Things to know

- Every terminating host needs `tls.terminate` (a `cert`, or `acme`; `tls.terminate: {}`
  is accepted too). A host cannot set both `upstream`/`upstreams` and `paths`.
- Certificate files named here are not read by `--check-config`, so the
  paths in these sets are placeholders. Neither are listener names checked.
- A key written wrongly is rejected (the v2 parser refuses unknown keys), with
  exceptions: a misspelled key inside `rewrite`, `redirect` or an entry of a
  weighted `upstreams` list is silently ignored.
- The per-set `config.yaml` files are identical on purpose, so each set differs
  only in its `upstreams.yaml`.
- `transforms` expressions are compiled when the proxy starts, not by
  `--check-config`. `match_expr` is compiled by the check.
- Backends use RFC 1918 addresses and `example.com` names. Replace them.
- `config.yaml` here only declares listeners. The full `proxy` section is in
  [`../config/proxy/`](../config/proxy/config.yaml).
