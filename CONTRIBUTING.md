# Contributing to HubNEX

Thanks for your interest! Reports, ideas and fixes are welcome. For security issues, read
[SECURITY.md](SECURITY.md) first.

## How it's put together

```
hubnex/                 the add-on
  hubnex/               the server (Python, FastAPI): assistant, agents, Home, energy, voice
  web/                  the dashboard (JavaScript without a build step: ES modules, three.js)
  integration/hubnex/   the Assist integration the add-on installs in Home Assistant
  config/agents.yaml    the example team
  dev/demo.py           HubNEX with a fake house and a fake Claude
  tests/                server tests (pytest) and dashboard tests (tests/ui, in the browser)
docs/                   the presentation (GitHub Pages)
```

## Trying the dashboard without Home Assistant

```bash
cd hubnex
pip install -r requirements-dev.txt
python dev/demo.py 8765
```

Open <http://127.0.0.1:8765>: an example house with rooms, lights, climate, energy, cameras and
a fake Claude that always answers with the same sentence. No API key, nothing leaves your computer.
The "turn on …" and "turn off …" commands in the chat are carried out by the fake house.

## Tests

```bash
cd hubnex
python -m pytest -q                         # server
npm install --prefix tests/ui               # once: Playwright
npx --prefix tests/ui playwright install chromium
node --test tests/ui/*.test.cjs             # dashboard in the browser, against dev/demo.py
```

The same checks run on GitHub for every change (**Actions** tab): a change is merged only when
everything is green.

## Style

- **Python**: simple and readable, short functions, docstrings that explain the *why*. Tests
  accompany every new behaviour.
- **Dashboard**: no framework and no build step; user-facing texts are in English, plain,
  with no emoji in the interface.
- **No initiative**: HubNEX never acts without an order from its owner. Locks, alarm, mail and
  writes to work programs always ask for confirmation. A change that bypasses this rule will
  not be accepted.
- **No personal data** in the repository: examples, tests and screenshots use the example house.

## Proposing a change

1. Open an issue or an idea first, so we can discuss it.
2. Fork, create a clearly named branch, make the change together with its tests.
3. Update `hubnex/CHANGELOG.md` and, if the behaviour changes, `hubnex/DOCS.md`.
4. Open the pull request: describe what changes for people who use HubNEX.

The version in `hubnex/config.yaml` is bumped by whoever publishes: every new version builds the
add-on images.
