# Use cases

Complete, runnable Synapse configurations, one directory each. Pick the one
closest to what you want and copy it. Every set uses placeholder values
(`example.com`, documentation IP ranges) that you replace with your own.

| Set | Mode | API key | Privileges | What it shows |
|---|---|---|---|---|
| [`host-ids`](./host-ids/) | agent | no | `CAP_NET_RAW` (AF_PACKET) | Local Suricata-format rules over AF_PACKET capture, alerts in an EVE JSON file; alert only |
| [`reverse-proxy-waf`](./reverse-proxy-waf/) | proxy | no | none: the demo listens on ports 8080 and 8443 | TLS-terminating reverse proxy with WAF and access rules from local files |
| [`xdp-firewall`](./xdp-firewall/) | agent | no | `CAP_BPF` and `CAP_NET_ADMIN` (XDP) | XDP firewall enforcing access rules and 5-tuple rules from a local file; no fallback if XDP fails |
| [`passive-monitoring`](./passive-monitoring/) | agent | no | `CAP_NET_RAW` (AF_PACKET); `CAP_BPF` for XDP | TCP-level fingerprints written to a log; nothing is blocked |

"Privileges" lists what the set's own config needs; the installation guide
lists what the container image needs on top. Installation is covered in the
[installation guide](https://docs.gen0sec.com/docs/client/installation).
