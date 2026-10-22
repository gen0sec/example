# smart-firewall

Synapse as an XDP firewall that blocks by TCP fingerprint and by source
address, from rules in a local file. The amygdala smart firewall is on too and
adds the other JA4 fingerprint kinds. The IDS runs as well, and bans the
source of a flow that matches a blocking rule.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel and a network driver that support XDP, and
  `/sys/kernel/btf/vmlinux` present.
- Privileges to load eBPF and attach XDP: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. Without them the XDP backend cannot load.
- A Synapse build with the smart firewall. `amygdala-reactor` is in the
  default features, so the standard and `-ml` packages have it. It is enabled
  at runtime by `firewall.amygdala.enabled: true`, which this set sets.
- No Gen0Sec API key.

`firewall.mode: xdp` forces the XDP backend and has no fallback. If XDP cannot
be loaded, Synapse logs `XDP mode forced but BPF not available` and no kernel
firewall is installed. To fall back to nftables, then iptables, set
`firewall.mode: auto` instead.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, forced XDP firewall, amygdala on with backend `auto`, capture on, IDS with blocking, file logging to `/var/log/synapse` |
| [`security_rules.yaml`](./security_rules.yaml) | `smart_firewall_rules`: a JA4T block, and expression rules that allow and block by source address |
| [`rules/host-ids.rules`](./rules/host-ids.rules) | One test IDS rule, a copy of the [host-ids](../host-ids/) one |

All addresses in the rules files are documentation ranges. Replace them with
your own, and set `ids.address_vars.HOME_NET` to match your host.

## Interfaces

XDP, the XDP IDS and XDP capture attach to `network.interfaces`, else
`network.ifaces` or `network.iface`. This set leaves them unset, so every
physical interface that is up is used. To pin one, set `network.iface` to your
uplink (a commented example is in `config.yaml`).

`capture.interface` does not move XDP. It chooses the interface of the
AF_PACKET fallback, which binds every interface (lo, bridges, veth) when it is
unset. This set sets it to `eth0`. To use one interface, set both
`network.iface` and `capture.interface` to it.

The amygdala bridge enforces on ONE interface. With `firewall.amygdala.iface`
unset, it is the first physical interface that XDP attached to. On a host with
several NICs XDP covers all of them, but the bridge's TC and reactor
enforcement covers one. Set `firewall.amygdala.iface` to choose it. If
`network.interfaces` marks an interface with the `smart_firewall` role, leave
`amygdala.iface` unset: a different value stops Synapse at start.

## What blocks what

Three mechanisms block sources on top of the XDP firewall, and the IDS can add
a fourth. They are independent, and turning amygdala off does not stop the
first two.

| Rule | Enforced by | Conditions | Expiry |
|---|---|---|---|
| `kind: ja4t` entry in `smart_firewall_rules.block` | The XDP fingerprint stage in the main firewall, always on with XDP | XDP attached | None on v0.8.9: the block lasts until the file changes. `ttl_seconds` does not lift it. |
| `rules:` expression | Evaluated per flow in the capture pump. A drop makes an adaptive IP ban through the firewall backend. | Capture enabled; the source is not a loopback, private, CGNAT, link-local or multicast address | Adaptive, from `ids.ban_base_secs` |
| Other JA4 kinds (`ja4`, `ja4s`, `ja4h` and so on) | The amygdala bridge only, through NFQUEUE or TC, plus a TTL-tracked copy | `firewall.amygdala.enabled`, and `logging.eventbridge_log.enabled` | `ttl_seconds` or `expires_at` if set |
| IDS `enforce_block: true` | The firewall backend | A matching rule whose action is `drop`, `reject` or `block` | 300 seconds |

With `backend: auto` the bridge tries `xdp`, then `nftables`, then `iptables`.

Things that follow from the code:

- Expression rules need capture. They read the flow events capture produces,
  so `capture.enabled: false` leaves them with nothing to decide on. The XDP
  JA4T stage does not need capture.
- The bridge runs only while `logging.eventbridge_log.enabled` is on (the
  default). Turning that log off stops it without a message.
- Expression-rule IP bans skip loopback, RFC 1918, CGNAT, link-local and
  multicast sources. A test from the LAN never bans.
- Expression rules are checked in file order and the first match wins. List
  allow rules before block rules.
- The test rule in `rules/` is an `alert` rule. With `enforce_block: true` it
  still only alerts. To ban a source, write a `drop`, `reject` or `block` rule.
- `ids.ban_base_secs` is the floor of the adaptive smart-firewall ban. Repeat
  offenders get longer bans, and a value under 60 is raised to 60.
- Sources in `ids.address_vars.HOME_NET` are never banned. The host's own
  interface addresses are never banned either, but only while XDP is attached.
  If `HOME_NET` is unset while XDP enforcement is on, Synapse logs a warning.
- `backend: auto` is used, not `afxdp`. The AF_XDP backend needs a dedicated
  interface and conflicts with the main XDP firewall.

## Run as a package

```bash
sudo mkdir -p /etc/synapse/rules
sudo cp config.yaml security_rules.yaml /etc/synapse/
sudo cp rules/host-ids.rules /etc/synapse/rules/
sudo synapse -c /etc/synapse/config.yaml \
  --security-rules-config /etc/synapse/security_rules.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

Check the files without root first: `synapse --check-config -c config.yaml
--security-rules-config security_rules.yaml`.

## See it working

Look for the line `Using XDP/BPF firewall backend (forced)` in the output,
then confirm the program is attached to your interface (the one in
`network.iface`, or any physical interface if it is unset):

```bash
ip link show <interface> | grep xdp
```

Blocks are written to the security-event log, `/var/log/synapse/events.log`,
as JSON lines.

## Limits

- The check above proves the files parse. It does not prove that XDP attaches
  or that a rule blocks.
- Fingerprint rules need traffic that produces the fingerprint. The JA4T value
  in the file is a placeholder that matches no real stack: replace it with one
  from `/var/log/synapse/fingerprint.log`.
- On v0.8.9 a JA4T block lasts until the file changes. There is no timeout.
- Fleet-wide and platform-managed rules need an API key and are not part of
  this set.
