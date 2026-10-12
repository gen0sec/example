# Gen0Sec Synapse examples

Configuration examples, use cases and integrations for
Synapse, the Gen0Sec reverse proxy, WAF and host agent. Product documentation
is at [docs.gen0sec.com](https://docs.gen0sec.com).

## Layout

| Path | What it holds |
|---|---|
| [`integrations/`](./integrations/) | Ready-to-use integrations of third-party tools with the Gen0Sec API |
| `use-cases/` | Complete, runnable Synapse configurations (being added) |
| [`reference/`](./reference/) | Short annotated snippets, one per feature: config sections now, upstreams and security rules coming |

### Available now

- [Fail2Ban](./integrations/fail2ban/): a Fail2Ban action that reports banned
  IP addresses to the Gen0Sec API, with an Ansible playbook to roll it out.

### Being updated

- [Datadog](./integrations/datadog/): a Datadog workflow that responds to
  security signals. It is being updated: its block step points at a retired
  endpoint, so do not use it yet.

Synapse configuration examples are being added. `reference/config/` is
available; `use-cases/`, `reference/upstreams/` and `reference/security-rules/`
will appear here when they are ready.

Every config set is checked with `synapse --check-config`: run
`SYNAPSE_BIN=/path/to/synapse make test`. `make help` lists the other targets.

## Standalone vs with a Gen0Sec API key

- **Standalone:** Synapse runs from local configuration files only. It needs
  no API key. Installing Synapse still needs a repository credential from the
  Gen0Sec dashboard, which is separate from the platform API key.
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
