# passive-monitoring

Synapse as a passive network observer. The agent captures packets on the
interface in `capture.interface` and writes the fingerprints it computes to a
log. It blocks nothing: there is no kernel firewall, no IDS and no rules file.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux. With `firewall.mode: none` the capture backend `auto` resolves to
  AF_PACKET, so any current kernel works.
- Privileges: run as root, or give the process `CAP_NET_RAW` (the AF_PACKET
  socket), `CAP_BPF` and `CAP_NET_ADMIN` (the eBPF collectors that
  `capture.enabled: true` attaches to the interface, whatever `firewall.mode`
  is), and `CAP_SYS_ADMIN` or `CAP_PERFMON` (the SSL uprobes). The packaged
  service unit grants `CAP_NET_ADMIN`, `CAP_NET_RAW`, `CAP_SYS_ADMIN`,
  `CAP_BPF` and `CAP_NET_BIND_SERVICE`.
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, no firewall, capture with `mode: auto` on `capture.interface`, file logging to `/var/log/synapse` with the eventbridge and events logs |

With `firewall.mode: none` no BPF program loads, so capture is AF_PACKET and
`capture.interface` chooses the interface. Unset, or `auto`, it listens on
every interface, including `lo` and virtual ones. The eBPF collectors (JA4TS,
JA4L, JA4S, JA4SSH) attach to one interface from `network.iface`, `ifaces` or
`interfaces`; unset, the first physical one. Set `capture.interface` and
`network.iface` to your uplink. The config ships `capture.interface: eth0` and
a commented `network.iface` example.

## Run as a package

```bash
sudo mkdir -p /etc/synapse
sudo cp config.yaml /etc/synapse/config.yaml
sudo synapse -c /etc/synapse/config.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

## What it shows

In agent mode Synapse fingerprints the TCP and latency layer of each
connection it sees. On the test replay the log held JA4T (TCP SYN), JA4TS
(TCP SYN-ACK), JA4 (TLS ClientHello), JA4S (TLS ServerHello), JA4X
(certificate) and the SNI. JA4H (HTTP headers) was not seen. The Synapse
mode comparison table lists the application-level fingerprints as proxy-only;
it is out of date for agent mode.

One JSON line per fingerprint event is written to
`/var/log/synapse/eventbridge.log`:

```bash
tail -f /var/log/synapse/eventbridge.log
```

## Limits

- Nothing is blocked. `firewall.mode: none` installs no kernel firewall, and
  there is no IDS, no access rules and no WAF.
- `/var/log/synapse/events.log` is the security-event log (blocks). This set
  blocks nothing, so expect little or nothing in it.
- `capture.mode: auto` picks XDP when BPF programs are loaded, and otherwise
  AF_PACKET with `recvfrom()`. With `firewall.mode: none` no XDP program is
  loaded for the firewall, so it takes the AF_PACKET path.
- To enforce blocks as well as observe, use the
  [xdp-firewall](../xdp-firewall/) set.
