# agent-full-ml

Synapse agent with everything on: an XDP firewall, the smart firewall (amygdala), packet capture and fingerprinting, an XDP IDS that bans, managed IDS rules, and four ML models that download themselves.

## What you need

- The Synapse `-ml` package (the classifier build, glibc 2.38+). The standard
  package does not support the `ml:` section: it logs one "Config options not
  supported by this build: ml" warning and runs without models. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with a kernel that can load XDP programs.
- Privileges: run as root, or give the process `CAP_NET_RAW`, `CAP_BPF`,
  `CAP_NET_ADMIN`, and `CAP_SYS_ADMIN` or `CAP_PERFMON`. The packaged
  service unit grants `CAP_NET_ADMIN`, `CAP_NET_RAW`, `CAP_SYS_ADMIN`,
  `CAP_BPF` and `CAP_NET_BIND_SERVICE`.
- A Gen0Sec API key, in `platform.api_key` or the `API_KEY` environment
  variable.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode with an API key, firewall `auto` with amygdala, capture on, XDP IDS with `enforce_block: true` and managed rules, and the `ml:` section |
| [`rules/host-ids.rules`](./rules/host-ids.rules) | The demo IDS rule: it alerts on an ICMP echo containing `gen0sec-test`. It only alerts |

Set `capture.interface` and `network.iface` to your uplink. They are
separate keys. XDP and the XDP IDS follow `network.iface` (unset: every
physical interface that is up). The eBPF collectors attach to one interface,
the first physical one. `capture.interface` is read only by the AF_PACKET
fallbacks (unset: every interface). Uncomment `network.iface` and set both.

`daemon.working_directory` is `/var/lib/synapse`, so the config cache is
`/var/lib/synapse/cached_config.json`. The code default is `/`, which is shared
across the host.

## Run as a package

```bash
sudo mkdir -p /etc/synapse/rules
sudo cp config.yaml /etc/synapse/config.yaml
sudo cp rules/host-ids.rules /etc/synapse/rules/
sudo synapse -c /etc/synapse/config.yaml --check-config
sudo synapse -c /etc/synapse/config.yaml
```

Replace `YOUR_API_KEY` first. The log directory `/var/log/synapse` is created
on start. To run it as a service, see the installation guide.

## Models

Each model with `enabled: true` downloads itself from the platform and is
refreshed every 3600 s (`refresh_secs`), when `platform.api_key` is set. The
files are saved at their `model_path`. `fingerprint_classifier` is commented
out: it has no download and needs a local `.onnx` file that you supply. This
set makes no claim about what any model detects.

On first start the penalty and traffic models log `Failed to initialize ...
model file not found` until the startup sync installs them. If the platform is
unreachable then, `startup sync failed` is logged and the next try waits
`refresh_secs` (3600 s), unless a push from the platform arrives first.

## What it shows

On a test replay (a pcap file, no root) with the platform turned off, the
config parsed, the process started, loaded the demo rule and replayed the
packets, and the replay wrote the JA4T, JA4TS, JA4, JA4S and JA4X fingerprints.
With the placeholder key left in place the process stops at start: the
platform rejects the key (401). That is expected until you set a real key.

The replay did not download a model, attach XDP, or enforce anything. It only
shows that the file is valid for the `-ml` build and the process starts.

## Limits

- Detection, bans and models were not exercised. They need a real key, root and
  live traffic.
- A `security_rules.yaml` next to `config.yaml` is not read: with an API key
  the access and firewall rules come from the platform.
- The IDS bans only for `block`, `drop` and `reject` rules. The demo rule
  is an alert rule.
- The amygdala bridge runs only while `logging.eventbridge_log.enabled` is on, so turning that log off silently stops it.
- Bans last 300 s. Behind NAT one source is many users: tune your rules before relying on them.
- The managed IDS rules are written to `/var/lib/synapse/managed.rules` when the platform selects them for your account. The local rule path stays, because the AF_PACKET fallback refuses an empty list.
- For a detect-only variant, see [capture-ids-ml](../capture-ids-ml/).
