# capture-ids

Synapse as a detect-only intrusion detection agent on a real interface. Packet
capture and the XDP IDS run together, local Suricata-format rules are matched,
and alerts and periodic stats are written to an EVE JSON file. It only alerts;
it does not block anything.

## How it differs from host-ids

[`host-ids`](../host-ids/) is the portable demo: capture off, an AF_PACKET IDS
on loopback, so you can trigger its rule from the same host. This set is the
production shape: capture on, `ids.capture_mode: xdp` (the default), and
`firewall.mode: auto`, on the interface you set. If no XDP program is attached,
the IDS falls back to the AF_PACKET IDS. Both sets are local-only
(`managed_rules_path: ""`) and alert only (`enforce_block: false`).

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel and a network driver that support XDP, and
  `/sys/kernel/btf/vmlinux` present. Without XDP the IDS runs over AF_PACKET.
- Privileges to load eBPF and attach XDP: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. The AF_PACKET fallback needs `CAP_NET_RAW`.
- No Gen0Sec API key.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode, capture on `eth0`, XDP IDS in detect-only mode, EVE log (`alert` and `stats`) to `/var/log/synapse/eve.json` |
| [`rules/capture-ids.rules`](./rules/capture-ids.rules) | One test rule, a copy of the one in host-ids: alert on an ICMP echo request whose payload contains `gen0sec-test` |

Set `capture.interface` to your uplink if it is not `eth0`.

## Run as a package

```bash
sudo mkdir -p /etc/synapse/rules
sudo cp config.yaml /etc/synapse/config.yaml
sudo cp rules/capture-ids.rules /etc/synapse/rules/
sudo synapse -c /etc/synapse/config.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

## Reading the alerts

```bash
grep '"event_type":"alert"' /var/log/synapse/eve.json
```

`"action":"allowed"` means the rule only alerts. A `stats` record is written
every few seconds, so the file is not empty before the first alert. The record
format is the one shown in [host-ids](../host-ids/#see-it-working).

## Limits

- Alert only: `enforce_block` is `false`. Do not turn it on before the rules
  are tuned, because behind NAT one source address can be many users.
- `managed_rules_path: ""` turns off pulling managed rules, so the ruleset is
  exactly the files in `rule_paths`. Managed rules need a Gen0Sec API key.
- The test rule is a demo. Add real rules to `/etc/synapse/rules/` (files ending
  in `.rules` are picked up). They are loaded at start; restart the agent after
  changing them.
- `firewall.mode: auto` picks the first available firewall backend (XDP, then
  nftables, then iptables). This set loads no access rules, so it blocks
  nothing.
- To send the alerts to a SIEM, see [ids-siem](../ids-siem/).
