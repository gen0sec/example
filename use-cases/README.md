# Use cases

Complete, runnable Synapse configurations, one directory each. Pick the one
closest to what you want and copy it. Every set uses placeholder values
(`example.com`, documentation IP ranges) that you replace with your own.

| Set | Mode | API key | Privileges | What it shows |
|---|---|---|---|---|
| [`host-ids`](./host-ids/) | agent | no | `CAP_NET_RAW` (AF_PACKET) | Local Suricata-format rules over AF_PACKET capture, alerts in an EVE JSON file; alert only |
| [`reverse-proxy-waf`](./reverse-proxy-waf/) | proxy | no | none: the demo listens on ports 8080 and 8443 | TLS-terminating reverse proxy with WAF and access rules from local files |
| [`xdp-firewall`](./xdp-firewall/) | agent | no | `CAP_BPF` and `CAP_NET_ADMIN` (XDP) | XDP firewall enforcing access rules and 5-tuple rules from a local file; if XDP fails, only the 5-tuple rules fall back to netfilter (and none do when `network.interfaces` is set) |
| [`passive-monitoring`](./passive-monitoring/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Fingerprints (TCP, TLS, certificate) written to a log; nothing is blocked |
| [`capture-ids`](./capture-ids/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Production shape of host-ids: capture on, XDP IDS with local rules, alert only, EVE alerts and stats |
| [`ids-siem`](./ids-siem/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Detect-only IDS whose alerts and block events go out as CEF to a file and a syslog collector |
| [`platform-managed`](./platform-managed/) | agent | yes | `CAP_BPF` and `CAP_NET_ADMIN` (XDP); `CAP_NET_RAW` and `CAP_SYS_ADMIN` or `CAP_PERFMON` for capture | Platform-managed agent: dynamic rules, threat and GeoIP databases, managed IDS rules and fleet bans (advisory) from the platform; no local rules file |
| [`smart-firewall`](./smart-firewall/) | agent | no | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | XDP firewall that blocks by TCP fingerprint and source address from a local file, with the amygdala bridge for other JA4 kinds, and IDS bans from blocking rules |
| [`capture-ids-ml`](./capture-ids-ml/) | agent | yes | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | Detect-only XDP IDS with capture and four ML models that download with the API key; needs the `-ml` package |
| [`agent-full-ml`](./agent-full-ml/) | agent | yes | `CAP_NET_RAW`, `CAP_BPF`, `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON` | XDP firewall, smart firewall, blocking IDS with managed rules, capture and four ML models; needs the `-ml` package and an API key |
| [`lb-methods`](./lb-methods/) | proxy | no | none: the demo listens on port 8080 | One route per `lb.method` over the same three servers; `maglev`, `ring_hash` and `least_request` need Synapse 0.8.9 or later |
| [`certbot`](./certbot/) | proxy | no | none: the demo listens on ports 8089 and 8443 | Serve and renew certificates that certbot writes, with the webroot challenge routed through Synapse; needs Synapse 0.8.9 or later |
| [`lb-passthrough`](./lb-passthrough/) | proxy | no | none: the demo listens on port 8080 | One passthrough host per `lb.method`, without terminating TLS; `maglev` and `ring_hash` on a passthrough host need Synapse 0.8.9 or later |
| [`lb-source-ip-persistence`](./lb-source-ip-persistence/) | proxy | no | none: the demo listens on port 8080 | Pin a client address to the server it first got, whatever `lb.method` says; needs Synapse 0.8.9 or later |
| [`sticky-sessions`](./sticky-sessions/) | proxy | no | none: the demo listens on port 8088 | Keep a client on the server it first got with a signed cookie, and what happens to a cookie that does not verify; needs Synapse 0.8.9 or later |
| [`upstream-source`](./upstream-source/) | proxy | no | none: the demo listens on port 8080 | Bind the connections to a back-end to a local address, interface and port range; needs Synapse 0.8.9 or later |
| [`upstream-tls`](./upstream-tls/) | proxy | no | none: the demo listens on port 8080 | Certificate chain and name checks for a TLS back-end, at the top level, per host or per path; needs Synapse 0.8.9 or later |
| [`tcp-mss`](./tcp-mss/) | proxy | no | none: the demo listens on port 8080 | Cap the MSS of the connections a listener accepts; needs Synapse 0.8.9 or later |
| [`edge-headers`](./edge-headers/) | proxy | no | none: the demo listens on ports 8080 and 8443 | `X-Forwarded-For`, `X-Forwarded-Proto`, `Via`, a request ID and HSTS; needs Synapse 0.8.9 or later |
| [`header-rules`](./header-rules/) | proxy | no | none: the demo listens on port 8080 | Add and remove request and response headers, with a script that checks every rule |
| [`hsm-tls-keys`](./hsm-tls-keys/) | proxy | no | none: the demo listens on ports 8085 and 8443 | TLS private keys in an HSM over PKCS#11 (RSA and EC), served beside a software key, with the PIN in a file; the demo uses SoftHSM in docker; needs Synapse 0.8.9 or later |
| [`kubernetes-cert-manager`](./kubernetes-cert-manager/) | proxy | no | a privileged proxy pod, Kubernetes cluster | A `SynapseProxy` of the Synapse operator serving an Ingress with a certificate from cert-manager, and the proxy picking up a renewed certificate without a restart; needs Synapse operator 0.2.0 (not released yet) and Synapse 0.8.8 or later |

"Privileges" lists what the set's own config needs; the installation guide
lists what the container image needs on top. Installation is covered in the
[installation guide](https://docs.gen0sec.com/docs/client/installation).
