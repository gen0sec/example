# Reference

Short, annotated snippets, one per feature. Each snippet is a config set that
`synapse --check-config` accepts on its own, so you can copy a section out and
know the key names are right. For a complete, runnable setup, see
`use-cases/` (being added).

| Directory | What it covers | Status |
|---|---|---|
| [`config/`](./config/) | One snippet per top-level section of the main config file | Available |
| `upstreams/` | The upstreams file: routes, load balancing, health checks, passthrough | Coming |
| `security-rules/` | The security rules file: access, WAF and firewall rules | Coming |

## How the snippets are written

- Defaults come from the Synapse code, not from the sample config shipped with
  the packages. Where the two differ, the snippet states the code default.
- Every snippet runs standalone, with no Gen0Sec API key. Keys that need a key
  are commented out and marked "With a Gen0Sec API key".
- Addresses use `example.com` and the documentation ranges, and keys are
  placeholders.

## Check them

```sh
SYNAPSE_BIN=/path/to/synapse make test
```

`make test` runs `synapse --check-config` on every config set and fails on an
error, on a warning (an unknown key is a warning) and on a missing binary. A
config set is a directory with a `config.yaml`, plus an `upstreams.yaml` and a
`security_rules.yaml` beside it when present. See
[`scripts/check.sh`](../scripts/check.sh).
