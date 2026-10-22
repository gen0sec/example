# Reference

Short, annotated snippets, one per feature. Each snippet is a config set that
`synapse --check-config` accepts on its own, so you can copy a section out and
know the key names are right. For a complete, runnable setup, see
`use-cases/` (being added).

| Directory | What it covers | Status |
|---|---|---|
| [`config/`](./config/) | One snippet per top-level section of the main config file | Available |
| [`upstreams/`](./upstreams/) | The upstreams file: routes, load balancing, health checks, passthrough | Available |
| [`security-rules/`](./security-rules/) | The security rules file: access, WAF, firewall and amygdala rules | Available |

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

`--check-config` arrives in the next Synapse release; no release has it yet, so
use a build that does. CI does not run this check yet.

`make test` runs `synapse --check-config` on every config set and fails on an
error, on a warning (an unknown key is a warning) and on a missing binary. A
config set is a directory with a `config.yaml`, plus an `upstreams.yaml` and a
`security_rules.yaml` beside it when present. See
[`scripts/check.sh`](../scripts/check.sh).

A build without the `classifier` feature cannot check the `ml:` keys. It warns
that they are not supported, and `make test` then prints `skip <set> (ML keys
need a classifier build)` for a set with no other warning, and counts it in the
summary. Any other warning in that set still fails it. Set
`SYNAPSE_REQUIRE_ML=1` to make a skip a failure, as for a classifier build. A
default build checks none of the ML keys (`ml:` and the deprecated top-level
`classifier`, `penalty`, `traffic_classifier`, `flow_classifier`,
`jepa_embedder` and `jepa`): a typo or a wrong value type in them shows only on
a classifier build.
