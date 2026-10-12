# Gen0Sec Synapse examples

Configuration examples, use cases and integrations for
[Synapse](https://github.com/gen0sec/synapse), the Gen0Sec reverse proxy, WAF
and host agent.

## Layout

| Path | What it holds |
|---|---|
| [`integrations/`](./integrations/) | Ready-to-use integrations of third-party tools with the Gen0Sec API |
| `use-cases/` | Complete, runnable Synapse configurations (being added) |
| `reference/` | Short annotated snippets, one per feature (being added) |

### Available now

- [Fail2Ban](./integrations/fail2ban/): a Fail2Ban action that reports banned
  IP addresses to the Gen0Sec API, with an Ansible playbook to roll it out.
- [Datadog](./integrations/datadog/): a Datadog workflow that responds to
  security signals and lets a responder block the IP addresses in Gen0Sec.

Synapse configuration examples are being added. `use-cases/` and `reference/`
will appear here when they are ready.

## Standalone vs with a Gen0Sec API key

- **Standalone:** Synapse runs from local configuration files only. It needs
  no API key.
- **With a Gen0Sec API key:** Synapse also connects to the Gen0Sec platform,
  which adds the features that depend on platform data. The integrations in
  this repository use the Gen0Sec API and need an API key.

The Fail2Ban and Datadog integrations are not Synapse configurations. They
call the Gen0Sec API directly.

## Install Synapse

Installation (packages, containers and Kubernetes) is covered in the
[installation guide](https://docs.gen0sec.com/docs/client/installation).
The rest of the documentation is at [docs.gen0sec.com](https://docs.gen0sec.com).

## Licence

Synapse is dual-licensed: the Sustainable Use License applies by default, and
the Synapse Enterprise License applies to some components. Production use of
the Enterprise-licensed components requires a Gen0Sec subscription;
development, testing and evaluation are free. See the
[Synapse repository](https://github.com/gen0sec/synapse#license) for which
components are covered.

The files in this repository are examples for you to copy and adapt.

## Support

- Documentation: [docs.gen0sec.com](https://docs.gen0sec.com)
- Community chat: [Discord](https://discord.gg/jzsW5Q6s9q)
- Issues with an example: open an issue in this repository.
