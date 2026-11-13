# HubNEX

*English only*

> [!NOTE]
> **This is a fork.** HubNEX was created by **[P1pp89](https://github.com/P1pp89)**; the original
> project lives at **[github.com/P1pp89/HubNEX](https://github.com/P1pp89/HubNEX)**. This fork
> keeps the interface and documentation in English and adds its own changes on top. All credit
> for the project goes to the original developer. If you want to support HubNEX, see
> [Support the original developer](#support-the-original-developer) below.

**The AI headquarters for home and work**, as a Home Assistant add-on.

[![Checks](https://github.com/emile-bodin/HubNEX/actions/workflows/ci.yaml/badge.svg)](https://github.com/emile-bodin/HubNEX/actions/workflows/ci.yaml)

**[See the presentation →](https://p1pp89.github.io/HubNEX/en/)**

![HubNEX's Home view](docs/img/en/casa.jpg)

An assistant (called Jarvis out of the box) coordinates a team of AI agents (Claude), each with
its own role: mail, administration, technical research, home, security… You talk to it from the
3D dashboard in Home Assistant's sidebar, from a Telegram group or by voice through Assist.

- **3D dashboard**: the headquarters with the agents at work, the neural map of what the team
  knows, the animated core that listens, thinks and speaks.
- **Home view**: Home Assistant's dashboard on the holographic floor plan of your house, with
  rooms, lights, climate, blinds, live cameras, alarm and an energy panel. Direct commands, in
  real time, with no AI cost.
- **Configurable team** in `agents.yaml`: companies, departments, agents, instructions, routines.
- **MCP connectors**: connect the programs of your work (management software, calendars, CRM…).
  Agents read freely; every change runs only after your ✅.
- **The past of the house**: every agent can read Home Assistant's history, logbook and
  statistics (read-only, up to 14 days of detail) to answer "when" and "how long" and spot
  routines. Needs the recorder integration; any user's token will do, no admin needed.
- **Mail**: sorting of your emails and reply drafts you approve.
- **Telegram**: a group with a bot for the assistant and one for the mail, voice notes, photos and documents included.
- **Voice**: Home Assistant's Assist (also local with Piper), ElevenLabs or Home Assistant's
  text-to-speech in the dashboard.
- **No initiative without your order**: routines off by default, no action in the house without
  your request, permanent rules that apply to the whole team.
- **English or Dutch**: the dashboard, assistant, agents and add-on messages in English (default) or Dutch.

## Installation

[![Add the repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Femile-bodin%2FHubNEX)

1. Home Assistant → Settings → Add-ons → **Add-on store** → ⋮ → **Repositories** → add
   `https://github.com/emile-bodin/HubNEX` (or press the button above).
2. Install **HubNEX**, open **Configuration**, enter the Anthropic API key (or choose the
   personal Claude Code subscription mode described in the documentation), **Start** and turn
   on **Show in sidebar**.

The full guide (team, connectors, voice, Telegram, mail, Home view) is in
[`hubnex/DOCS.md`](hubnex/DOCS.md), also available in the add-on's **Documentation** tab.

API-key mode needs an Anthropic Console account with credit. A private single-user setup can
instead sign in to the included Claude Code CLI with its own Claude subscription; see the add-on
documentation. HubNEX uses Claude Sonnet for the assistant and the
agents and Claude Haiku for mail and quick commands. The Home view's commands and, with Assist,
Home Assistant's simple commands use no credit.

**Other AI providers.** Every agent can also run on **OpenAI** or on a **local model** through
Ollama or LM Studio (free, no cloud), or on any OpenAI-compatible service (OpenRouter, Gemini,
Mistral…): write the model as `openai:gpt-5-mini` or `ollama:qwen3:14b`. Claude stays the
recommended choice: web search and Jarvis' visible thoughts are Claude-only. See the docs.

## Without Home Assistant (Docker)

```bash
cd hubnex
cp .env.example .env        # fill in the keys
docker compose up -d --build
# dashboard: http://<machine-ip>:8765/?token=<HQ_TOKEN>
```

## API

All of them need `Authorization: Bearer <HQ_TOKEN>` (or `?token=`).

| Method | Path | |
|---|---|---|
| GET | `/api/state` | Full state (team, activity, deadlines, statistics) |
| POST | `/api/chat` | `{"text": "...", "attachments": []}` → the assistant's answer |
| POST | `/api/attachments?name=` | A photo, PDF or text file (raw body) → `{"id"}` for `attachments` |
| POST | `/api/agents/{id}/task` | `{"task": "...", "wait": false}` assigns a task |
| POST | `/api/deadlines` | `{"title", "due", "notes"}` |
| POST | `/api/tts` | `{"text"}` → audio in the configured voice |
| POST | `/api/ha/event` | Event from a Home Assistant automation |
| GET | `/api/casa` | Home view: floor plan, areas, entities and states |
| GET | `/api/backup` | Backup of everything HubNEX knows (zip) |
| WS | `/ws?token=` | Live stream for the dashboard |

Send `X-HubNEX-Lang: nl` to get errors in Dutch (default: English).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md): a demo with a pretend house and Claude
(`python hubnex/dev/demo.py 8765`), the server tests (`pytest`) and the browser tests of the
dashboard. The tests use a fake Claude client: no real calls and no cost.

Structure: `hubnex/hq.py` (the team, the state, delegation), `hubnex/llm.py` (Claude agent
loop), `hubnex/connectors.py` and `hubnex/integrations/mcp.py` (MCP connectors),
`hubnex/actions.py` (actions to confirm), `hubnex/casa.py` and `hubnex/energy.py` (Home view),
`hubnex/maildesk.py` (mail), `hubnex/i18n.py` (languages), `hubnex/tools/` (the agents' tools),
`hubnex/integrations/` (Home Assistant, Telegram, IMAP/SMTP, ElevenLabs), `web/` (dashboard:
Three.js and hls.js included, it works without internet too).

## Support the original developer

> [!IMPORTANT]
> ☕ **The donation link below goes to [P1pp89](https://github.com/P1pp89), the original author
> of HubNEX — not to the maintainer of this fork.** Buying them a coffee supports the person who
> built the project.

HubNEX is free and open source, and it will stay that way. If it gives you back a few minutes
every day, help keep the reactor running: **[buy the original developer a coffee on PayPal](https://www.paypal.com/donate/?hosted_button_id=HTZJULXKFP8M4)**.
Every contribution turns into new features, more tests and faster fixes.

A star on the [original repository](https://github.com/P1pp89/HubNEX) helps too: it brings
HubNEX to the people who need it.

## Licence

[MIT](LICENSE). Includes [Three.js](https://threejs.org) (MIT) and
[hls.js](https://github.com/video-dev/hls.js) (Apache 2.0): see [NOTICE](NOTICE).

HubNEX is not affiliated with Anthropic, Home Assistant, ElevenLabs or Marvel: "Jarvis" is just
the assistant's default name and can be changed in `agents.yaml`.
