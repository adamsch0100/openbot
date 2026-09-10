# OttoBot brand + credit lockup

OttoBot is **your board**. Hermes Agent and OpenCode are **upstream engines**.
We wrap them. We do not become them.

Product face: **Otto** — friendly TV-head mark, lowercase **ottobot** wordmark, line **On it.**

## Positioning (say this out loud)

Wrong: “OttoBot is a Hermes / OpenCode product.”
Right: “OttoBot is a control plane that runs Hermes Agent and OpenCode.”

MIT lets you wrap the code. MIT does **not** give you their names as your product name, their logos, or an affiliation claim.

## Who it is for, in order

1. You first. One instance at a local or private URL (`http://127.0.0.1:8787`, later a host you control).
2. When that instance beats the hosted-bot habit (cheap jobs, INDEX memory, tools on demand), grow toward hosted sessions + app.
3. Every user owns their session brains and keys. Do not mix tenants’ files.

“On it.” is the consumer line. Keep engine credit in text — never inside the Otto mark.

## What the logo is allowed to say

- Otto head (gray monitor face, lavender antenna) — `web/otto.svg`, `web/favicon.png`, `web/logo.png`
- Wordmark: **ottobot** / **OTTOBOT** in chrome
- Line under: **On it.**

Do not put Nous, Anomaly, Hermes, or OpenCode *inside* the logo.
Do not use their animal/wordmarks or “Official” / “Powered by” partnership stamps.

## Required credit (every surface)

Same three lines, same order, everywhere people look:

```
OttoBot uses Hermes Agent (MIT, Nous Research)
and OpenCode (MIT, Anomaly).
Not affiliated with, sponsored by, or endorsed by those projects.
```

Places this must appear:

- README.md (top third, not a footer afterthought)
- NOTICE / THIRD-PARTY.md (full MIT texts + links)
- Board About panel (and footer mark)
- First-run mark / setup surface
- Advanced drawer: live links to each engine + “open raw Hermes” / “open OpenCode”

Footer lockup (small, not a logo mashup):

```
OTTOBOT  ·  On it.
Engines: Hermes Agent  ·  OpenCode
```

Each engine name is a text link, not a borrowed mark.

## In-product honesty

The user sees one composer (Grok-simple chat). They must still see **which engine ran** on every job card:

- Cos — board only
- Builder / SupportBuilder — OpenCode
- Research / Ops — Hermes Agent

Never hide the engine to look like a single original agent. Capability can feel unified. Attribution cannot.

## Names we will not use

- Hermes, Hermes Agent, Nous, OpenCode, Anomaly, Grok Bot, Grok — as the product title
- OpenBot (legacy product title — repo/paths may still say openbot)
- “OttoBot by Hermes”, “OpenCode Bot”, “Grok-like Bot”
- Their logos next to ours in a lockup that reads as co-branding

Allowed descriptive sentences in docs and About:

- “Routes coding jobs to OpenCode.”
- “Schedules and memory go through Hermes Agent.”
- “Inspired by the *shape* of a persistent bot chat, not a clone of any hosted desktop.”

## Distribution copy (README)

```
OttoBot is a self-hosted board. Install it, point it at a folder,
and it talks to Hermes Agent and OpenCode you already have (or
the official installers).

This is not a hosted cloud computer and not an official
Nous or Anomaly product. You run the instance. You hold the keys.
```

## First-run screen (credit is part of setup)

1. Detect `hermes` and `opencode` binaries
2. If missing, link **official** installers only
3. Show Otto mark + attribution before the board opens (About/API credit ok)
4. Ask where work lives
5. Open the URL

If an engine is missing, the board still loads in Cos-only mode and the footer says which engine is absent. Do not silently pretend OttoBot *is* the missing engine.
