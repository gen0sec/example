# Gen0Sec Synapse examples

Configuration examples, use cases and integrations for
Synapse, the Gen0Sec reverse proxy, WAF and host agent. Product documentation
is at [docs.gen0sec.com](https://docs.gen0sec.com).

## Layout

| Path | What it holds |
|---|---|
| [`integrations/`](./integrations/) | Ready-to-use integrations of third-party tools with Synapse and the Gen0Sec API |
| [`use-cases/`](./use-cases/) | Complete, runnable Synapse configurations, one directory each |
| [`reference/`](./reference/) | Short annotated snippets, one per feature: config sections, upstreams and security rules |

### Available now

- [Fail2Ban](./integrations/fail2ban/): a Fail2Ban action that reports banned
  IP addresses to the Gen0Sec API. The Ansible role that rolls it out lives in
  [gen0sec/ansible-playbook](https://github.com/gen0sec/ansible-playbook).
- [Splunk](./integrations/splunk/): a Splunk add-on that parses Synapse
  access logs, whether they arrive by syslog, a file or HEC, and maps them to
  the CIM Web data model.
- [Host IDS](./use-cases/host-ids/): agent mode with AF_PACKET capture, local
  Suricata-format rules and EVE alerts written to a file.
- [Reverse proxy with a WAF](./use-cases/reverse-proxy-waf/): Synapse as a
  TLS-terminating proxy with WAF and access rules, run as a package or with
  docker compose, with no API key.
- [XDP firewall](./use-cases/xdp-firewall/): agent mode with a forced XDP
  firewall that enforces access rules and 5-tuple rules from a local file, with
  no API key.
- [Passive monitoring](./use-cases/passive-monitoring/): agent mode with
  packet capture and no firewall; fingerprints are written to a log and nothing
  is blocked.

### Being updated

- [Datadog](./integrations/datadog/): a Datadog workflow that responds to
  security signals. It is being updated: its block step points at a retired
  endpoint, so do not use it yet.

Synapse configuration examples are being added: `reference/` is complete, and
more use cases are on the way. [`use-cases/`](./use-cases/) has a table of the
sets.

Config sets are checked with `synapse --check-config`, which arrives in the
next Synapse release (no release has it yet). With a build that has it, run
`SYNAPSE_BIN=/path/to/synapse make test`. CI does not run this check yet. `make help` lists the other targets.

## Standalone vs with a Gen0Sec API key

- **Standalone:** Synapse runs from local configuration files only. It needs
  no API key. Installing Synapse still needs a repository credential from the
  Gen0Sec dashboard, which is separate from the platform API key.
- **With a Gen0Sec API key:** Synapse also connects to the Gen0Sec platform,
  which adds the features that depend on platform data. The Fail2Ban and
  Datadog integrations use the Gen0Sec API and need an API key.

The Fail2Ban and Datadog integrations are not Synapse configurations. They
call the Gen0Sec API directly. The Splunk add-on needs no API key: it reads
the logs Synapse writes.

## Install Synapse

Installation (packages, containers and Kubernetes) is covered in the
[installation guide](https://docs.gen0sec.com/docs/client/installation).
The rest of the documentation is at [docs.gen0sec.com](https://docs.gen0sec.com).

## Licence

Synapse is commercial software from Gen0Sec. Its licensing is set by your
agreement with Gen0Sec. For licensing questions, contact
[support@gen0sec.com](mailto:support@gen0sec.com).

The examples in this repository are licensed MIT-0 (see [LICENSE](./LICENSE)):
copy and adapt them freely. That licence covers the files in this repository
only, not Synapse.

## Support

- Documentation: [docs.gen0sec.com](https://docs.gen0sec.com)
- Community chat: [Discord](https://discord.gg/jzsW5Q6s9q)
- Email: [support@gen0sec.com](mailto:support@gen0sec.com)
- Issues with an example: open an issue in this repository.
