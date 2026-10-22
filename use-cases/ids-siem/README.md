# ids-siem

Synapse as a detect-only IDS that sends its alerts to a SIEM. IDS alerts and
block events are rendered as ArcSight Common Event Format (CEF), written to a
rotating file and sent to a syslog collector. It only alerts; it does not block
anything.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel and a network driver that support XDP, and
  `/sys/kernel/btf/vmlinux` present. Without XDP the IDS runs over AF_PACKET.
- Privileges to load eBPF and attach XDP: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. The AF_PACKET fallback needs `CAP_NET_RAW`.
- A syslog collector that accepts CEF over UDP on port 514. Replace
  `siem.example.com` with its address.
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, XDP IDS in detect-only mode, EVE log (`alert`), CEF to `/var/log/synapse/cef.log` and to syslog `siem.example.com:514` over UDP in RFC 5424 |
| [`rules/ids-siem.rules`](./rules/ids-siem.rules) | One test rule, a copy of the one in host-ids: alert on an ICMP echo request whose payload contains `gen0sec-test` |

Set `capture.interface` to your uplink if it is not `eth0`.

## Run as a package

```bash
sudo mkdir -p /etc/synapse/rules
sudo cp config.yaml /etc/synapse/config.yaml
sudo cp rules/ids-siem.rules /etc/synapse/rules/
sudo synapse -c /etc/synapse/config.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

## How the CEF output works

- `logging.cef.streams.ids_alerts: true` renders IDS alerts, including
  alert-only rules, as CEF. `block_events: true` renders security decisions
  from every layer. The access-log and fingerprint streams stay off.
- The CEF syslog sink is Synapse's own direct sender: it opens its own socket
  to the collector. It is separate from the local syslog daemon and from the
  `logging.syslog` section, so it needs no local syslog setup.
- CEF output starts only when `logging.file_logging_enabled` is `true`, which
  this set sets.
- The syslog host is resolved once at start. If it does not resolve, or the CEF
  file cannot be opened, Synapse prints `synapse_cef::init failed` and CEF
  output is off for that run. The agent keeps running.
- `transport: udp` cannot slow the agent but loses records if the collector or
  the network drops them. `transport: tcp` is reliable, but the sink drops
  records while the connection is down. `rfc: rfc3164` is for collectors that
  only speak BSD syslog.
- `device_host` is sent as `dvchost` in every record; left empty, the system
  hostname is used.

## Sending the data on

- [`integrations/splunk`](../../integrations/splunk/): a Splunk add-on that
  parses Synapse logs.
- [`integrations/syslog-ng`](../../integrations/syslog-ng/): forwards
  Synapse's syslog to a remote host through syslog-ng.

## Limits

- Alert only: `enforce_block` is `false`. Do not turn it on before the rules
  are tuned, because behind NAT one source address can be many users.
- `managed_rules_path: ""` turns off pulling managed rules, so the ruleset is
  exactly the files in `rule_paths`.
- The test rule is a demo. Add real rules to `/etc/synapse/rules/`; they are
  loaded at start.
- `siem.example.com` is a placeholder and does not resolve. Replace it before
  you run this set, or CEF is off for the run.
- The EVE file is written next to the CEF output; the EVE log is not sent to
  the SIEM.
