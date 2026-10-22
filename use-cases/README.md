# Use cases

Complete, runnable Synapse configurations, one directory each. Pick the one
closest to what you want and copy it. Every set uses placeholder values
(`example.com`, documentation IP ranges) that you replace with your own.

| Set | Mode | API key | Privileges | What it shows |
|---|---|---|---|---|
| [`host-ids`](./host-ids/) | agent | no | `CAP_NET_RAW` (AF_PACKET) | Local Suricata-format rules over AF_PACKET capture, alerts in an EVE JSON file; alert only |
| [`reverse-proxy-waf`](./reverse-proxy-waf/) | proxy | no | none: the demo listens on ports 8080 and 8443 | TLS-terminating reverse proxy with WAF and access rules from local files |
| [`xdp-firewall`](./xdp-firewall/) | agent | no | `CAP_BPF` and `CAP_NET_ADMIN` (XDP) | XDP firewall enforcing access rules and 5-tuple rules from a local file; if XDP fails, only the 5-tuple rules fall back to netfilter |
| [`passive-monitoring`](./passive-monitoring/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Fingerprints (TCP, TLS, certificate) written to a log; nothing is blocked |
| [`capture-ids`](./capture-ids/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Production shape of host-ids: capture on, XDP IDS with local rules, alert only, EVE alerts and stats |
| [`ids-siem`](./ids-siem/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Detect-only IDS whose alerts and block events go out as CEF to a file and a syslog collector |
| [`platform-managed`](./platform-managed/) | agent | yes | `CAP_BPF` and `CAP_NET_ADMIN` (XDP); `CAP_NET_RAW` and `CAP_SYS_ADMIN` or `CAP_PERFMON` for capture | Platform-managed agent: dynamic rules, threat and GeoIP databases, managed IDS rules and fleet bans (advisory) from the platform; no local rules file |
| [`smart-firewall`](./smart-firewall/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | XDP firewall that blocks by TCP fingerprint and source address from a local file, with the amygdala bridge for other JA4 kinds, and IDS bans from blocking rules |
| [`capture-ids-ml`](./capture-ids-ml/) | agent | yes | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Detect-only XDP IDS with capture and four ML models that download with the API key; needs the `-ml` package |
| [`agent-full-ml`](./agent-full-ml/) | agent | yes | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | XDP firewall, smart firewall, blocking IDS with managed rules, capture and four ML models; needs the `-ml` package and an API key |

"Privileges" lists what the set's own config needs; the installation guide
lists what the container image needs on top. Installation is covered in the
[installation guide](https://docs.gen0sec.com/docs/client/installation).
