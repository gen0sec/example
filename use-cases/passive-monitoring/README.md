# passive-monitoring

Synapse as a passive network observer. The agent captures packets on one
interface and writes the TCP-level fingerprints it computes to a log. It blocks
nothing: there is no kernel firewall, no IDS and no rules file.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux. With `firewall.mode: none` the capture backend `auto` resolves to
  AF_PACKET, so any current kernel works.
- Privileges to open a raw packet socket: run as root, or give the process
  `CAP_NET_RAW`. Capturing with XDP instead needs `CAP_BPF` (and
  `CAP_NET_ADMIN` to attach it).
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, no firewall, capture on `eth0` with `mode: auto`, file logging to `/var/log/synapse` with the eventbridge and events logs |

Set `capture.interface` to your uplink if it is not `eth0`.

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
connection it sees: JA4T (TCP SYN), JA4TS (TCP SYN-ACK), JA4L and JA4LS
(latency). The application-level fingerprints (JA4, JA4H, JA4S, JA4X) need TLS
termination, which only proxy mode does, so they are not produced here. The
mode comparison is in the [documentation](https://docs.gen0sec.com).

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
