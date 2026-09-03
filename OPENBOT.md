# OPENBOT — Cursor project brief

Save this as `OPENBOT.md` at the root of the OpenBot repo (e.g. `adamsch0100/openbot`).
Keep `ARCHITECTURE.md` and `BRAND.md` next to it.
Also copy the section **Cursor / coding-agent law** into `AGENTS.md`.
This is the spec. Do not invent a third agent runtime.

Grok-in-X chats do not persist project files to your machine. This file *is* the handoff: paste it into Cursor and tell Cursor “follow OPENBOT.md.”

## One sentence

OpenBot is a control plane: one board that routes work to Hermes Agent
(ops, memory, schedules) and OpenCode (repos, LSP, MCP).
We do not fork or rewrite those engines.

## What we are doing

- OpenBot: first-run, board UI, INDEX, tickets, allowlists, job log, spend cap, snapshot browser policy
- Hermes Agent: long jobs, skills, cron, persistent memory when we opt in
- OpenCode: code edits, diffs, MCP, `opencode web` / `opencode run`

The user sees one product. Power users can still open raw Hermes and OpenCode.

## What we are not doing

- Do not vendor or merge the Hermes or OpenCode source trees into this repo
- Do not clone Grok Bot cloud desktop or eternal chat
- Do not put CoS / occupancy / CRD in Telegram
- Do not store or type passwords, TOTP, or API keys in chat, brains, or git
- Do not enable every MCP on every agent
- Do not treat conversation history as the database

## Distribution

Phase 1: your instance only. Web board at a URL (`http://127.0.0.1:8787`, then a host you control). Chat, jobs, INDEX all live there.
Phase 2: other people clone the repo and spin **their own** instance. No multi-tenant OpenBot cloud in v1.

## Legal + credit (keep this in README, footer, About)

Both engines are MIT. Wrapping is allowed if copyright and license notices stay.
Trademarks are **not** in the MIT grant. OpenBot is not “a Hermes/OpenCode product.”
It is a board that **uses** those products.

- Hermes Agent, Nous Research: https://github.com/NousResearch/hermes-agent
- OpenCode, Anomaly: https://github.com/anomalyco/opencode

Do not name the product Hermes, OpenCode, or Grok Bot. Do not use their logos.
Do not put engine names inside the OPENBOT mark. Credit lives in text under/ beside it.

Required three lines (README, NOTICE, board footer, first-run):

> OpenBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly).
> Not affiliated with, sponsored by, or endorsed by those projects.

Ship `NOTICE` or `THIRD-PARTY.md` with both MIT texts.
Nous Portal and model APIs have separate terms.

Every job card names the engine that ran. See `BRAND.md`.

## Product promise

Chat dies. Files stay. Engines are upstream.

- Status questions read `brains/INDEX.md` only (no tools)
- Doing work: Hermes and/or `opencode run`, then RESULT back to INDEX
- Agents do not DM. Four-line tickets go to `inbox/<agent>.md`
- Browser default: accessibility snapshot + refs, not a pixel stream
- Screenshots are opt-in. Login walls stop for a human on the real screen

## UX

One composer. Always. Simple surface, rich underneath.

Beginner sees: Home prompt, Cos/Builder/Research, INDEX card, Work in this folder, paste URL, schedule in plain language.
Advanced opens: job log, tokens, engine used, MCP toggles, raw brains, OpenCode session, Hermes cron, `opencode.json`.

First run:

1. One install command
2. Detect Hermes + OpenCode; use official installers if missing
3. Ask where work lives (folder)
4. Use existing engine auth; never commit keys
5. Create INDEX + Cos
6. Open http://127.0.0.1:8787
7. First prompt: What is this project and what is blocked?

Judge on time-to-first-useful-diff, not tool count.

## Routing

- Status / what is going on → Hermes short session, tools OFF, INDEX only
- Change code → `opencode run` in that folder; MCP only on Builder
- Multi-step ops / cron → Hermes skill + schedule
- Click a site → OpenBot snapshot worker
- Raw IDE → `opencode web` in the corner

Presets:

- Cos: files only, no MCP, no bash, no browser. Cos has no Hermes home and no OpenCode session. Status reads a staff briefing (instance INDEX four-liners plus each CEO). Work (Code / Think / Research / Ops) rides the aimed CEO, or the primary CEO.
- CEO: owns a work folder (OpenCode) and a `hermes-homes/{id}` (Hermes). Workers share that CEO’s engines and keep their own BRAIN + Hermes session name.
- Builder: OpenCode + git MCP
- Research: snapshot browser + fetch
- Ops: Hermes cron + notify

Add GitHub = toggle MCP onto Builder only.

## Repo layout

```
openbot/
  OPENBOT.md
  AGENTS.md
  README.md
  NOTICE
  bin/openbot
  openbot/          thin glue only
  web/              board UI
  brains/
  inbox/
  agents/
  .opencode/agents/
```

Do not copy `nousresearch/hermes-agent` or `anomalyco/opencode` into this tree.
Call them as binaries.

## Cursor / coding-agent law

1. Read `OPENBOT.md` and `brains/INDEX.md` first
2. Change only glue, board, docs, and presets
3. If Hermes or OpenCode already has it, wire it, do not reimplement it
4. End jobs by updating INDEX or the agent brain: Now / Last / Next / Blocker
5. No secrets in files
6. New tools default OFF for Cos
7. If you stall, one-line blocker

## Build order

- Week 1: board on 127.0.0.1, detect engines, status path, code path, job log, README + NOTICE
- Week 2: Builder happy path (folder → change → diff card → INDEX). If this is not delightful, stop adding features.
- Week 3: Research + snapshot browser. Password fields blocked.
- Week 4: MCP toggles per agent, Hermes schedule UI, model picker, spend/tool cap.

Not this month: Telegram mesh, cloud computer, merging upstream source, unsupervised tools that can pay money.

## Why cheaper than a hosted cloud bot

Hosted bots resend a giant thread, keep a desktop warm, and browse with screenshots.
OpenBot uses one-shot jobs, INDEX instead of transcript memory, tools only on the agent that needs them, and snapshot text instead of pixels.

## Done looks like

A new user installs OpenBot, points at a repo, asks for a change, sees a diff and an INDEX update,
and never had to choose Hermes vs OpenCode. Advanced users can still open both engines.
Credits in the README. No stolen marks.

## How to use this in Cursor

1. Unzip this folder. In Cursor: File → Open Folder on `openbot`.
2. Paste `CURSOR_PROMPT.md` into chat.
3. Run `python3 bin/openbot` and open http://127.0.0.1:8787
4. Finish Week 1 only (`WEEK1.md`). Do not start Research until Builder diffs are delightful.
