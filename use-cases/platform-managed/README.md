# platform-managed

Synapse as an agent that the Gen0Sec platform manages. With a Gen0Sec API key
the platform delivers the rules and data, and the agent enforces and reports.
There is no local rules file.

## What you need

- Synapse installed as a package or pulled as a container image. Installation
  is covered in the
  [installation guide](https://docs.gen0sec.com/docs/client/installation); this
  example does not repeat it.
- Linux with XDP support on the interface. The config uses the XDP IDS and
  `firewall.mode: auto`, which picks XDP, then nftables, then iptables. The
  config leaves `network.iface` unset, so XDP attaches to every physical
  interface that is up; a commented example shows how to pick one.
  `capture.interface` is set to the example uplink `eth0`. It does not choose
  the XDP interface: it is read only by the AF_PACKET capture and IDS fallback,
  and when unset those bind to every interface, including `lo`, bridges and
  veth. Set both `network.iface` and `capture.interface` to your uplink.
- Privileges to load and attach XDP programs: run as root, or give the process
  `CAP_BPF` and `CAP_NET_ADMIN`. Packet capture needs `CAP_NET_RAW` as well.
  Run as a container, the image needs the capabilities its installation guide
  lists.
- A Gen0Sec API key. You get it from your Gen0Sec dashboard. The key also
  needs the `fleet_bans:write` and `fleet_bans:read` permissions for the ban
  features below. The repository credential that installs Synapse is a
  separate thing from the platform key.
- Outbound HTTPS to the platform and its download hosts.

## Files

| File | What it does |
|---|---|
| [`config.yaml`](./config.yaml) | Agent mode with the platform on: threat database, GeoIP, ban ledger and fleet bans (advisory), XDP IDS with managed rules, `firewall.mode: auto`, capture on, file logging and an EVE log |

The set has no `security_rules.yaml` and no `rules/` directory on purpose.

## Run as a package

Put your key in the config, or leave `api_key` empty and set `API_KEY` in the
environment. Replace `YOUR_API_KEY` in the copy, never in this repository.

```bash
sudo mkdir -p /etc/synapse
sudo cp config.yaml /etc/synapse/config.yaml
sudo synapse -c /etc/synapse/config.yaml
```

The log directory `/var/log/synapse` is created on start. To run it as a
service, see the installation guide.

## What the key turns on

- **Access rules and the rest of the rule config.** The agent pulls them from
  the platform and applies them, and a config worker keeps them current. A
  copy of the last config is cached as `cached_config.json` in
  `daemon.working_directory`, which `config.yaml` sets to `/var/lib/synapse`.
  The code default is `/`, so without that line the cache lands at
  `/cached_config.json`.
- **Threat database** (`platform.threat`). An MMDB of threat intelligence,
  checked for a new version every `refresh_secs` seconds (default 300).
- **GeoIP** (`platform.geoip`). A combined country and ASN database, checked
  every 8 hours by default. GeoIP is the one platform feature that also runs
  without a key; it is listed here because the config sets its source.
- **Managed IDS rules** (`ids.managed_rules_path`). The agent writes the rule
  bundles the platform selects for your account to this file, and the IDS
  reloads when the file changes. If your account has no managed IDS rules
  selected, the file stays empty and the IDS has no rules.
- **Ban ledger and fleet bans** (`platform.ban_ledger`, `platform.fleet_bans`).
  The agent uploads the bans it decided. The platform corroborates them across
  your agents and publishes the result, which the agent downloads. In this set
  the downloaded set is advisory: matches are counted and nothing is
  blocked. `enforce: true` installs them in the kernel filter; turn it on
  only after advisory mode has shown how many false positives you get.

Two paths use two different directories. `daemon.working_directory` holds the
config cache. The process working directory is where relative paths such as the
default `managed_rules_path`, the fleet ban cache and models resolve; that is
why `config.yaml` gives absolute paths.

## Local rules are not read

With a key, the agent takes its access rules from the platform. It does not
read `security_rules.yaml`, and a local file is ignored. Without a key it reads
the local file instead (the standalone path). So a set that uses a key ships no
local rules file.

The IDS has no `rule_paths` here either. The XDP IDS supports a deployment that
has only managed rules: it creates `managed_rules_path` empty if it is missing,
starts with no rules and loads the bundle after the first sync. This was
checked in the code and not on a running agent. If you also want local rules,
add `ids.rule_paths`, as in the [host-ids](../host-ids/) set.

## What happens at startup

The agent checks the key against the platform before it goes on:

- **The platform refuses the key** (HTTP 401 or 403, or an answer that says
  the key is not valid): startup stops with `API key validation failed`.
  Fix the key and start again.
- **The platform cannot be reached** (no network, DNS failure, a timeout, a
  5xx or any other status): the agent logs a warning, `Could not validate the
  API key`, and carries on. The key has not been refused, only not checked.
  The config worker retries, and the agent uses the cached config if one
  exists. The agent starts either way; the platform rules arrive once the
  platform answers.

## Telemetry

`telemetry_sending_enabled` defaults to `true`, and the config shows it. As far
as the code shows, it sends access logs, fingerprint events and WAF events to
the platform, and OpenTelemetry data to the platform's telemetry endpoint. Set
it to `false` to stop both. With a key set, the agent also sends a status
heartbeat to the platform whatever this key says. It is sent every 30 seconds
(change it with `AGENT_HEARTBEAT_SECS`) and holds:

- the agent name, hostname, version, mode, process id and uptime;
- the names of the network interfaces;
- the OS and architecture, `platform_base_url` and whether XDP is loaded;
- the capabilities that are on, and per-feature metadata;
- the tags in `AGENT_TAGS` and the addresses in `AGENT_IP_ADDRESSES`, if set.

## Limits

- The IDS is detect-only: `enforce_block` is `false`.
- Without XDP this set runs no IDS. The XDP IDS is skipped, and the AF_PACKET
  fallback refuses an empty `rule_paths` with `thalamus_ids(afpacket): no IDS
  rule paths configured, not starting`. The startup summary still reports
  `"thalamus_ids": true`, so look for that warning, not the flag. To run the
  fallback, add `ids.rule_paths`; it cannot load managed rules.
- `ban_ledger` and `fleet_bans` work only with a key that has the permissions
  above.
- This set was checked with `synapse --check-config`. It was not run against
  the platform, so the platform side (what rules your account gets) is not
  shown here.

## See it working

Look for these lines in the console or in the log file:

- `API key validation failed` means the platform refused the key and Synapse
  did not start. `Could not validate the API key` means it could not ask; it
  keeps going.
- `[agent_status] capabilities (N) at boot: [...]` lists what this agent
  reports to the platform. It appears once the key is set.
- `[thalamus_ids] Started (source=xdp, rules=N, ...` shows the XDP IDS is up.
  After the platform writes a new rule bundle, `[thalamus_ids] Config reload:
  hot-swapped IDS engine (rules=N, ...` gives the new rule count.
  `ids.enabled=true and ids.capture_mode=xdp but no active XDP skeletons are
  attached; XDP IDS worker not started` means XDP did not attach.
- `[fleet-bans] loaded N bans version=...` shows the fleet set was downloaded.
  In advisory mode there is no per-match line; matches are only counted.
