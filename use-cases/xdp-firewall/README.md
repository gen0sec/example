# xdp-firewall

Synapse as a kernel firewall driven by a local rules file. The agent attaches
an XDP program to the physical network interfaces and enforces an allow and block list
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

`firewall.mode: xdp` prefers the XDP backend. If XDP cannot be loaded, Synapse
logs `XDP mode forced but BPF not available`, and then:

- the `firewall_rules` (5-tuple rules) fall through to nftables or iptables,
  whichever accepts them, but only while `network.interfaces` is unset;
- the `access_rules` allow and block lists are not enforced, because no
  netfilter backend is set up for them in this mode.

With `network.interfaces` set, Synapse enforces through XDP only, because
nftables and iptables are host-wide and would touch interfaces the map leaves
out. If XDP cannot load, no kernel firewall is installed, for the 5-tuple rules
too.

With `firewall.mode: auto` and `network.interfaces` unset, Synapse falls back
to nftables, then iptables, for both. With `network.interfaces` set, `auto`
installs no kernel firewall when XDP cannot load.

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
then confirm the program is attached to your uplink (`eth0` here is an example):

```bash
ip link show eth0 | grep xdp
```

The security-event log is `/var/log/synapse/events.log`, written as JSON
lines.

## Limits

- XDP attaches to the interfaces Synapse selects. Automatic selection skips
  virtual interfaces and bridge masters (a bridge's member ports are used).
  `firewall.attach_veth` matters only for a `veth` you list in
  `network.iface` or `network.ifaces`. To choose the interfaces yourself, set
  those, or `network.interfaces` for a per-interface map (which also removes
  the netfilter fallback above); unset, every
  physical interface that is up gets the program. Run `ip link` to see which
  carry it.
- `max_ip_filter_entries_v4` and `_v6` are the capacity of the kernel IP
  filter. When one fills, new blocks are decided but never reach the kernel.
  A larger value takes effect only after `synapse --force-stop` or a reboot,
  because the maps stay pinned.
- Capture and the eventbridge (fingerprint) log are off, because this is a
  firewall-only set. Fingerprints are the
  [passive-monitoring](../passive-monitoring/) set.
- `waf_rules` is empty: the WAF belongs to proxy mode (see
  [reverse-proxy-waf](../reverse-proxy-waf/)).
