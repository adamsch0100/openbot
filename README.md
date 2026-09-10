# OttoBot

Self-hosted board. One composer. Files are memory. Engines stay upstream.

OttoBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly).
Not affiliated with, sponsored by, or endorsed by those projects.

This is not a hosted cloud computer. You run the instance. You hold the keys.

## What it is

OttoBot is a local control plane:

- **Board** — web UI at `http://127.0.0.1:8787`
- **Hermes Agent** — ops, skills, cron, snapshot browser when Research is on
- **OpenCode** — code edits, diffs, MCP when Builder is on

We do not fork those engines. We call the official binaries.

## You first, then others

Phase 1: one instance for the operator.
Phase 2: other people clone this repo and spin up *their* instance.
No multi-tenant OttoBot cloud in v1.

## Quick start

```bash
cd openbot
python bin/openbot
```

Windows: `.\bin\openbot.cmd` or the same `python bin/openbot` line.

Open http://127.0.0.1:8787

Optional engines (install from official docs, not from this repo):

- Hermes Agent: https://github.com/NousResearch/hermes-agent
- OpenCode: https://github.com/anomalyco/opencode

If an engine is missing, the board still loads in Cos-only mode and the footer says so.

OpenCode needs its own provider login (`opencode auth login`). Keys stay with the engine, not in this repo.

## Cursor

Open this folder in Cursor. Paste `CURSOR_PROMPT.md` into chat.

Law files:

- `OPENBOT.md` — product spec (repo filename; product name is OttoBot)
- `AGENTS.md` — coding-agent law
- `ARCHITECTURE.md` — cheap context + routing
- `BRAND.md` — OttoBot credit lockup
- `.cursor/rules/ceo-index-build.mdc` — CEO INDEX build law
- `BROWSER.md` — snapshot browser, not a warm desktop
- `brains/INDEX.md` — live source of truth

## Layout

```
OPENBOT.md          spec
AGENTS.md           agent law
bin/openbot         start the board
openbot/            thin Python glue
web/                board UI (Otto mark)
brains/             INDEX + per-bot brains
inbox/              four-line tickets
jobs/               receipts (not prompts)
```

## Credit

OTTOBOT · On it.
Engines: [Hermes Agent](https://github.com/NousResearch/hermes-agent) · [OpenCode](https://github.com/anomalyco/opencode)

See `NOTICE` and `BRAND.md`.
