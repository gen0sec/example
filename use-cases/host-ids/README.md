# host-ids

Synapse as a host intrusion detection agent: it reads packets from a network
interface, matches them against local Suricata-format rules, and writes alerts
to an EVE JSON file. It only alerts; it does not block anything.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with AF_PACKET (any current kernel).
- Privileges to open a raw packet socket: run as root, or give the process
  `CAP_NET_RAW`. Run as a container, the image also needs the capabilities its
  installation guide lists (`SYS_ADMIN`, `BPF`, `NET_ADMIN`), which the compose
  file adds.
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, AF_PACKET capture on `lo`, IDS on, EVE log to `/var/log/synapse/eve.json` |
| [`rules/host-ids.rules`](./rules/host-ids.rules) | One test rule: alert on an ICMP echo request whose payload contains `gen0sec-test` |
| [`docker-compose.yml`](./docker-compose.yml) | Runs the image with host networking and the capabilities above |

The interface is `lo` so you can trigger the rule from the same host. To watch
real traffic, set `capture.interface` to your uplink (for example `eth0`).

## Run as a package

```bash
sudo mkdir -p /etc/synapse/rules
sudo cp config.yaml /etc/synapse/config.yaml
sudo cp rules/host-ids.rules /etc/synapse/rules/
sudo synapse -c /etc/synapse/config.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

## Run with Docker Compose

Log in to the registry first (see the installation guide), then:

```bash
docker compose up -d
```

The compose file uses `network_mode: host`, so the container sees the host's
interfaces, and mounts `./logs` for the EVE file. The image tag is a release
version; change it to the one you use. Image tags have no `v` prefix.

## See it working

Start the agent, wait for the line `AF_PACKET IDS started on 'lo'` in its
output, then send a ping that carries the test payload (`67656e307365632d74657374`
is `gen0sec-test` in hex):

```bash
ping -c 1 -p 67656e307365632d74657374 127.0.0.1
```

Look in the EVE file (`/var/log/synapse/eve.json`, or `./logs/eve.json` with
Compose) for an alert:

```bash
grep '"event_type":"alert"' /var/log/synapse/eve.json
```

A line like this appears (one ping can produce more than one):

```json
{"timestamp":"1970-01-01T00:00:13.131110+0000","flow_id":704,"event_type":"alert","proto":"ICMP","alert":{"action":"allowed","gid":1,"signature_id":1000001,"rev":0,"signature":"GEN0SEC example: ICMP echo with test payload","category":"misc-activity","severity":2}}
```

Look for `"event_type":"alert"`, `"signature_id":1000001` and the signature text.
`"action":"allowed"` means the rule only alerts. The agent also logs
`ALERT sid=1000001 ...` to its console. A `stats` record is written every few
seconds, so the file is not empty before the first alert.

Seen on a test run: the timestamp of an alert was `1970-01-01...` (an offset
since the capture started, not the wall clock), and alerts on loopback traffic
carry no `src_ip` or `dest_ip`; on a real interface they do. Use the `stats`
records' timestamps for time. `stats` records need Synapse 0.8.8 or later,
which is the version the compose file pins.

The startup WARN that mentions `ids.capture_mode=xdp` is expected with this
config: it comes from the XDP IDS worker not starting, and the AF_PACKET IDS runs.

## With a Gen0Sec API key

Everything above runs without a key. With a key, the platform can deliver
managed IDS rule bundles, but only the XDP IDS loads them. It needs
`ids.capture_mode: xdp`, a `firewall.mode` other than `none`, and an interface
that supports XDP. With `firewall.mode: none` the agent loads no BPF or XDP, and
`capture_mode: xdp` falls back to the AF_PACKET IDS without managed rules. This AF_PACKET example builds its
ruleset from `rule_paths` alone and cannot use managed rules. Setting
`managed_rules_path: ""` turns off pulling them. See the
[documentation](https://docs.gen0sec.com) for setting the key.

## Limits

- Alert only: `enforce_block` is `false`. Do not turn it on before the rules
  are tuned, because behind NAT one source address can be many users.
- The IDS reads the one interface in `capture.interface`. `capture.enabled:
  false` keeps the agent from also attaching its fingerprinting probes (a TC
  SSH-fingerprint collector on the host uplink, SSL uprobes on libssl). With
  `capture.interface` unset the IDS binds to all interfaces.
- The `capture_mode: afpacketrecv` IDS is the portable path. The default,
  `xdp`, is faster and needs XDP support on the interface; it falls back to
  AF_PACKET when XDP is unavailable.
- The test rule is a demo. Add real rules to `rules/` (files ending in
  `.rules` are picked up). They are loaded at start; restart the agent after
  changing them.
- Kubernetes (the agent DaemonSet from the synapse-stack chart) is covered by
  the kubernetes use case, which is coming.
