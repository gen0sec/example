# Datadog Security Workflow

A Datadog workflow that automatically responds to security signals by extracting malicious IP addresses and services, creating an investigative notebook, and notifying security responders via Slack. Responders can then choose to either block the IPs directly in Gen0Sec or create a security incident for further investigation.

## Features

- Automatically triggers on Datadog security signals
- Extracts IP addresses and affected services from security signal data
- Creates an investigative notebook for security analysis
- Sends interactive Slack notifications with action options
- Supports direct IP blocking in Gen0Sec or incident creation
- Includes retry logic for API calls to Gen0Sec

![Gen0Sec architecture](./datadog.svg)

## Configuration

Import `datadog.json` into your Datadog Workflows workspace. Configure the workflow inputs:
- **Investigative notebook**: ID of the Datadog notebook template to use
- **IP set name** and **IP set ID**: Optional IP set parameters

Update the Slack notification settings (channel, team ID, mention targets) before publishing.

## Tutorial

1. Go to your Datadog dashboard.
2. On right side click on the Actions -> New workflow.
3. ![Use import button on right corner.](./docs/import.png)
4. [Download datadog json template](./datadog.json)
5. ![Import downloaded workflow](./docs/import_workflow.png)

When you finished the import you can see this.
![Workflow](./docs/workflow.png)

### Create new connection
You have to create a new connection.

1. Choose the step named `Arxignis` (the imported workflow still uses that step name)
2. Right side connection menu.
3. ![Create new connection](./docs/create_new_connection.png)
4. ![New connection](./docs/new_connection.png)
5. ![Connection configuration](./docs/connection.png)
6. Add your Gen0Sec API key to token value.
7. Use this connection in the workflow.

> ❗ Setup your Slack connection on our picture already configured.

# Congrats
Your system is most secure before this workflow.

![Workflow](./docs/workflow.png)
