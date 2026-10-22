# smart-firewall

Synapse as an XDP firewall with the amygdala smart firewall on top. Amygdala
watches the TLS and TCP fingerprints that packet capture produces and blocks
by fingerprint or by source address, from rules in a local file. The IDS runs
too, and bans the source of a flow that matches a blocking rule.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel and a network driver that support XDP, and
  `/sys/kernel/btf/vmlinux` present.
- Privileges to load eBPF and attach XDP: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. Without them the XDP backend cannot load.
- A Synapse build with the smart firewall (`amygdala-reactor`) in it. It is
  off by default and needs `firewall.amygdala.enabled: true`, which this set
  sets.
- No Gen0Sec API key.

`firewall.mode: xdp` forces the XDP backend and has no fallback. If XDP cannot
be loaded, Synapse logs `XDP mode forced but BPF not available` and no kernel
firewall is installed. To fall back to nftables, then iptables, set
`firewall.mode: auto` instead.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, forced XDP firewall, amygdala on with backend `auto`, capture on, IDS with blocking, file logging to `/var/log/synapse` |
| [`security_rules.yaml`](./security_rules.yaml) | `smart_firewall_rules`: a JA4T block with a timeout, and expression rules that block and allow by source address |
| [`rules/host-ids.rules`](./rules/host-ids.rules) | One test IDS rule, a copy of the [host-ids](../host-ids/) one |

All addresses in the rules files are documentation ranges. Replace them with
your own, and set `capture.interface` and `ids.address_vars.HOME_NET` to match
your host.

## What blocks what

Two mechanisms ban sources in this set, on top of the XDP firewall. They are
independent.

| Mechanism | Decides on | Enforced by |
|---|---|---|
| Amygdala | The fingerprints and source addresses in `smart_firewall_rules` | The amygdala backend. With `backend: auto` Synapse tries `xdp`, then `nftables`, then `iptables`, and uses the first that starts. |
| IDS `enforce_block: true` | A matching IDS rule whose action is `drop`, `reject` or `block` | The firewall backend. The source address is banned for 300 seconds. |

Things that follow from the code:

- Amygdala needs capture. It reads the fingerprints capture produces, so
  `capture.enabled: false` leaves it with nothing to decide on.
- The test rule in `rules/` is an `alert` rule. With `enforce_block: true` it
  still only alerts. To ban a source, write a `drop`, `reject` or `block` rule.
- `ids.ban_base_secs` is the floor of the adaptive smart-firewall ban. Repeat
  offenders get longer bans, and a value under 60 is raised to 60.
- Sources in `ids.address_vars.HOME_NET`, and the host's own interface
  addresses, are never banned. If `HOME_NET` is unset while XDP enforcement is
  on, Synapse logs a warning.
- `backend: auto` is used, not `afxdp`. The AF_XDP backend needs a dedicated
  interface and conflicts with the main XDP firewall.
- Amygdala rules are enforced only while amygdala runs. If it cannot start,
  nothing enforces them.

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
then confirm the program is attached to your interface:

```bash
ip link show eth0 | grep xdp
```

Blocks are written to the security-event log, `/var/log/synapse/events.log`,
as JSON lines.

## Limits

- The check above proves the files parse. It does not prove that XDP attaches
  or that a rule blocks.
- Fingerprint rules need traffic that produces the fingerprint. The JA4T value
  in the file is an example: replace it with one you have seen.
- Fleet-wide and platform-managed rules need an API key and are not part of
  this set.
