# Security

HubNEX holds API keys, access to your mail and control of the house, including locks and the
alarm. A vulnerability must be handled privately.

## How to report a problem

**Do not open a public issue.** Use GitHub's private reporting:
[Security → Report a vulnerability](https://github.com/P1pp89/HubNEX/security/advisories/new).

Include the HubNEX version, what can be done by exploiting the problem and how to reproduce it.
You will get an answer within a week; the fix ships in a new version and the report is made
public only afterwards, with your name if you wish.

## Supported versions

Only the latest published version receives security fixes: keep the add-on updated.

## What counts as a security problem

- access to the dashboard or the API without authorization, or a non-admin user reaching
  beyond the Home view;
- an action on locks, alarm, mail or connectors carried out without the required confirmation;
- keys, tokens or personal data exposed (logs, backups, API responses);
- a way to make agents or automations carry out actions the owner did not ask for.

## What HubNEX already does

- Keys live only in the add-on options and in `agents.yaml`, inside your Home Assistant.
  The HubNEX backup does not contain the add-on options; it does contain `agents.yaml`, and so
  any connector tokens: keep it as safe as a password.
- From the sidebar, Home Assistant's login applies; from outside, the HQ token is required.
- Locks, alarm and blocked services always ask for confirmation; writes to work programs (MCP)
  and emails go out only after your ✅.
