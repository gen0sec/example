# xdp-firewall

Synapse as a kernel firewall driven by a local rules file. The agent attaches
an XDP program to the network interface and enforces an allow and block list
and 5-tuple rules before a packet reaches the socket layer. It has no IDS, no
fingerprint capture and no proxy.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel and a network driver that support XDP (most current
  drivers do), and `/sys/kernel/btf/vmlinux` present.
- Privileges to load eBPF and attach XDP: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. Without them the XDP backend cannot load.
- No Gen0Sec API key.

`firewall.mode: xdp` forces the XDP backend and has no fallback. If XDP cannot
be loaded, Synapse logs `XDP mode forced but BPF not available` and no kernel
firewall is installed. To fall back to nftables, then iptables, set
`firewall.mode: auto` instead.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, forced XDP firewall, the IP-filter capacity, capture off, file logging to `/var/log/synapse` |
| [`security_rules.yaml`](./security_rules.yaml) | `access_rules` allow and block lists, and `firewall_rules` rulesets (a port block and a timed block) |

All addresses in the rules file are documentation ranges (`192.0.2.0/24`,
`198.51.100.0/24`, `203.0.113.0/24` and `2001:db8::/32`). Replace them with
your own before use.

## Run as a package

```bash
sudo mkdir -p /etc/synapse
sudo cp config.yaml security_rules.yaml /etc/synapse/
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

The security-event log is `/var/log/synapse/events.log`, written as JSON
lines.

## Limits

- XDP attaches to the interfaces Synapse selects (physical and bridge devices,
  not `veth*` unless `firewall.attach_veth` is set). Run `ip link` to see
  which one carries the program.
- `max_ip_filter_entries_v4` and `_v6` are the capacity of the kernel IP
  filter. When one fills, new blocks are decided but never reach the kernel.
  A larger value takes effect only after `synapse --force-stop` or a reboot,
  because the maps stay pinned.
- Capture is off, so this set writes no fingerprint events. Fingerprints are
  the [passive-monitoring](../passive-monitoring/) set.
- `waf_rules` is empty: the WAF belongs to proxy mode (see
  [reverse-proxy-waf](../reverse-proxy-waf/)).
