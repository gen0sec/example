# Main config reference

One directory per top-level section of Synapse's main config file. Each holds
a `config.yaml` that sets `mode` and that one section, with every key
explained and its default stated. Copy the section into your own file.

| Section | Directory | What it sets |
|---|---|---|
| `network` | [`network/`](./network/config.yaml) | Interfaces Synapse attaches to |
| `capture` | [`capture/`](./capture/config.yaml) | Packet-capture backend for fingerprinting |
| `firewall` | [`firewall/`](./firewall/config.yaml) | Kernel enforcement backend and block capacity |
| `ids` | [`ids/`](./ids/config.yaml) | Inline intrusion detection with Suricata-format rules |
| `platform` | [`platform/`](./platform/config.yaml) | Gen0Sec platform connection and data feeds, GeoIP |
| `logging` | [`logging/`](./logging/config.yaml) | Log files, security events, EVE output, syslog |
| `telemetry` | [`telemetry/`](./telemetry/config.yaml) | OpenTelemetry export to your own collector |
| `proxy` | [`proxy/`](./proxy/config.yaml) | Listeners, TLS, ACME, limits, captcha, content scanning |

Notes:

- `mode` is `agent` (access rules and monitoring, no proxy) or `proxy` (the
  reverse proxy and WAF). Its default is `agent`.
- The snippets show a key's default when they state "Default". A commented-out
  key is optional; one marked "With a Gen0Sec API key" does nothing without
  one.
- Not covered here: `daemon`, `ml`, `bpf_capacity`, `graceful_restart` and the
  `logging.cef` output.
