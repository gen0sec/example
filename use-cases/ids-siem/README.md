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
- Privileges: run as root, or give the process `CAP_BPF` and `CAP_NET_ADMIN`
  (XDP and the TC fingerprint collectors that `capture.enabled` attaches),
  `CAP_NET_RAW` (the AF_PACKET fallback), and `CAP_SYS_ADMIN` or
  `CAP_PERFMON` (the SSL uprobes). The packaged systemd unit grants all of
  these except `CAP_PERFMON`, so it relies on `CAP_SYS_ADMIN`.
- A syslog collector that accepts CEF over UDP on port 514. Replace
  `siem.example.com` with its address.
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, XDP IDS in detect-only mode, EVE log (`alert`), CEF to `/var/log/synapse/cef.log` and to syslog `siem.example.com:514` over UDP in RFC 5424 |
| [`rules/ids-siem.rules`](./rules/ids-siem.rules) | One test rule, a copy of the one in host-ids: alert on an ICMP echo request whose payload contains `gen0sec-test` |

Set the interface as described in "Which interface" below.

## Which interface

`network.iface` chooses the interfaces the XDP
program and the XDP IDS run on. Left unset, as here, Synapse auto-detects every
physical interface that is up. Unset, `capture.interface` binds every
interface, so keep it set. It is read only by the
AF_PACKET capture and the AF_PACKET IDS fallback; it does not choose the XDP
interface. To run on one interface, set both to it (the commented lines in
`config.yaml`).

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

- `logging.cef.streams.block_events: true` renders security decisions from
  every layer. A live IDS alert is also a block event (layer `ids`, severity
  notice), so it is already sent through this stream, alert-only rules
  included. `ids_alerts: true` renders the same alert a second time, from the
  EVE path. With both on, each live alert is sent twice. Set one of the two to
  `false` for one record per alert. A pcap replay cannot show this: the
  offline IDS emits no block event. The access-log and fingerprint streams
  stay off.
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
  records while the connection is down. The write runs on the thread that
  emits the record, and while the collector is down each record tries a 500 ms
  connect. With `ids_alerts` on, that thread can be the IDS inspect thread, so
  inspection can stall. TCP frames each record by octet count (RFC 6587), so
  the collector must support that framing. `rfc: rfc3164` is for collectors that
  only speak BSD syslog.
- `device_host` is sent as `dvchost` in every record; left empty, the system
  hostname is used.

## Sending the data on

These integrations do not carry this set's CEF output:

- [`integrations/splunk`](../../integrations/splunk/): a Splunk add-on for
  Synapse's access logs and `events.log`. It does not parse CEF. Use it for
  those logs, or point your SIEM's CEF parser at the collector instead.
- [`integrations/syslog-ng`](../../integrations/syslog-ng/): forwards
  Synapse's own syslog output (`logging.syslog`) to a remote host. This set
  leaves `logging.syslog` off, and the CEF sender does not go through the local
  syslog daemon, so that config does not apply to it. You can still run
  syslog-ng as the collector that receives the CEF datagrams.

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
