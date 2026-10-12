# Fail2Ban

A Fail2Ban action that reports banned IP addresses to the Gen0Sec Signal API (`POST /v2/signal`).
The request format is described in the [Signal API v2 reference](https://docs.gen0sec.com/docs/api/signal-api#signal-api-v2).

## Flow diagram
![Gen0Sec architecture](./fail2ban.svg)

## Fail2Ban Integration

The `integrations/fail2ban/` directory contains a Fail2Ban action file that integrates with the Gen0Sec API to automatically block malicious IP addresses.

### Setup

1. Copy the action file to your Fail2Ban actions directory:

   ```bash
   curl -fSL https://raw.githubusercontent.com/gen0sec/example/refs/heads/main/integrations/fail2ban/gen0sec.conf -o /etc/fail2ban/action.d/gen0sec.conf
   ```

2. Set appropriate permissions (the file contains your API token):
   ```bash
   sudo chmod 640 /etc/fail2ban/action.d/gen0sec.conf
   ```

3. Edit the configuration file and add your Gen0Sec API token:
   ```bash
   sudo nano /etc/fail2ban/action.d/gen0sec.conf
   ```
   Set the `g0stoken` value in the `[Init]` section.

4. Configure your jail to use the Gen0Sec action by editing your jail configuration:
   ```bash
   sudo nano /etc/fail2ban/jail.conf
   ```

   Add or modify the action parameter:
   ```
      banaction = gen0sec
      banaction_allports = gen0sec
   ```

   **Debian** related system. E.g: Ubuntu, Debian. `/etc/fail2ban/jail.d/defaults-debian.conf`
   ```
   [DEFAULT]
   banaction = gen0sec
   banaction_allports = gen0sec
   backend = systemd

   [sshd]
   enabled = true
   ```

### Requirements

- `curl` (required)
- `jq` (optional, for JSON parsing)
- Gen0Sec API token with the `signal:write` permission (available from your Gen0Sec dashboard)

**Upgrading from the earlier action:** it used the v1 Signal API, which needed no particular permission. Check that your key has the `signal:write` permission before you replace the file; without it every ban is refused, and Fail2Ban logs `Error banning`.

### Configuration Options

- `g0stoken`: Your Gen0Sec API Bearer token
- `expiration`: Block expiration time in seconds (default: the jail's `bantime`)

A ban, unban or prolong that the API does not accept with HTTP 200 fails, and Fail2Ban logs it as an error. That covers a key without the permission, an entry the API rejects, and an unreachable API.

When an IP is banned, the action creates a Gen0Sec access rule that blocks it, with the reference `fail2ban-<jail>-<ip>`. When Fail2Ban unbans the IP, the action deletes that rule.

Expiration is handled by the API as follows:

- The rule expires after `expiration` seconds, so Gen0Sec lifts the block on its own even if the unban never reaches the API.
- A value below 60 is raised to 60, and 0 means one day.
- A negative value is rejected, so a jail with a permanent ban (`bantime = -1`) needs `expiration` set to a positive number.

### Testing the action

`test/test_action.py` renders the action with Fail2Ban's own code and runs it against a local mock of the Signal API. It checks that a ban, unban or prolong succeeds only when the API answers 200. It needs the Fail2Ban Python package and sends nothing to Gen0Sec:

```bash
python3 test/test_action.py
```

### Ansible Playbook

An Ansible playbook is provided to automate the setup process across multiple servers.

#### Prerequisites

- Ansible 2.9 or later
- SSH access to target servers with sudo privileges

#### Quick Start

Run these steps from `integrations/fail2ban/`.

1. **Set up inventory file:**
   ```bash
   cp hosts.example hosts
   # Edit hosts and add your server details
   ```

2. **Configure variables:**
   ```bash
   mkdir -p group_vars
   cp group_vars/all.example.yml group_vars/all.yml
   # Edit group_vars/all.yml and set your Gen0Sec API token
   ```

3. **Run the playbook:**
   ```bash
   ansible-playbook playbook.yml
   ```

   Or pass the API token directly:
   ```bash
   ansible-playbook playbook.yml -e gen0sec_api_token=your_token_here
   ```

#### Playbook Features

- Installs fail2ban and required dependencies (curl, jq)
- Copies and configures the Gen0Sec action file
- Sets appropriate file permissions (640 for config file)
- Configures jail.local with Gen0Sec integration
- Supports both Debian/Ubuntu and RedHat/CentOS systems
- Enables and starts the fail2ban service

#### Variables

- `gen0sec_api_token`: Your Gen0Sec API Bearer token (required)
- `gen0sec_expiration`: Block expiration time in seconds (default: 600)
- `fail2ban_jail_enabled`: Enable fail2ban jails (default: true)
- `fail2ban_backend`: Fail2Ban backend (default: systemd)
