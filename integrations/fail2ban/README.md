# Example Integrations

This directory contains example integrations and configurations for Gen0Sec.

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
- Gen0Sec API token (available from your Gen0Sec dashboard)

### Configuration Options

- `g0stoken`: Your Gen0Sec API Bearer token
- `expiration`: Block expiration time in seconds (default: 600 = 10 minutes)

When an IP is banned, it will be automatically reported to Gen0Sec and blocked via the API. Unban actions will also be sent to remove the block.

### Ansible Playbook

An Ansible playbook is provided to automate the setup process across multiple servers.

#### Prerequisites

- Ansible 2.9 or later
- SSH access to target servers with sudo privileges

#### Quick Start

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
