# OpenBot brand + credit lockup

OpenBot is **your board**. Hermes Agent and OpenCode are **upstream engines**.
We wrap them. We do not become them.

## Positioning (say this out loud)

Wrong: “OpenBot is a Hermes / OpenCode product.”
Right: “OpenBot is a local control plane that runs Hermes Agent and OpenCode.”

MIT lets you wrap the code. MIT does **not** give you their names as your product name, their logos, or an affiliation claim.

## Who it is for, in order

1. You first. One instance at a local or private URL (`http://127.0.0.1:8787`, later your own host).
2. When that instance is better than the hosted-bot habit (cheap jobs, INDEX memory, tools on demand), publish the repo so **other people spin up their own instance**.
3. Not a multi-tenant SaaS in v1. Every user owns the process, the brains folder, and their API keys.

“LOCAL ORG.” on the mark is honest for phase 1. Keep it. Do not replace it with “Hermes × OpenCode” as if this were an official joint product.

## What the logo is allowed to say

The mark you have is fine:

- Faceted hex / cube in bronze + one mint facet
- Wordmark: **OPENBOT**
- Line under: **LOCAL ORG.**

Do not put Nous, Anomaly, Hermes, or OpenCode *inside* the logo.
Do not use their animal/wordmarks, hex colors copied from their sites, or “Official” / “Powered by” stamps that look like a partnership badge.

## Required credit (every surface)

Same three lines, same order, everywhere people look:

```
OpenBot uses Hermes Agent (MIT, Nous Research)
and OpenCode (MIT, Anomaly).
Not affiliated with, sponsored by, or endorsed by those projects.
```

Places this must appear:

- README.md (top third, not a footer afterthought)
- NOTICE / THIRD-PARTY.md (full MIT texts + links)
- Board footer, always visible on the web UI
- About / first-run screen
- Advanced drawer: live links to each engine + “open raw Hermes” / “open OpenCode”

Footer lockup (small, not a logo mashup):

```
OPENBOT  ·  LOCAL ORG.
Engines: Hermes Agent  ·  OpenCode
```

Each engine name is a text link, not a borrowed mark.

## In-product honesty

The user sees one composer. They must still be able to see **which engine ran** on every job card:

- Cos — board only
- Builder — OpenCode
- Research / Ops — Hermes Agent

Never hide the engine to look like a single original agent. Capability can feel unified. Attribution cannot.

## Names we will not use

- Hermes, Hermes Agent, Nous, OpenCode, Anomaly, Grok Bot, Grok — as the product title
- “OpenBot by Hermes”, “OpenCode Bot”, “Grok-like Bot”
- Their logos next to ours in a lockup that reads as co-branding

Allowed descriptive sentences in docs and About:

- “Routes coding jobs to OpenCode.”
- “Schedules and memory go through Hermes Agent.”
- “Inspired by the *shape* of a persistent bot chat, not a clone of any hosted desktop.”

## Distribution copy (README)

```
OpenBot is a self-hosted board. Install it, point it at a folder,
and it talks to Hermes Agent and OpenCode you already have (or
the official installers).

This is not a hosted cloud computer and not an official
Nous or Anomaly product. You run the instance. You hold the keys.
```

When others spin it up: same repo, same NOTICE, their URL, their keys, their brains/.
No shared “OpenBot cloud” that mixes tenants in v1.

## First-run screen (credit is part of setup)

1. Detect `hermes` and `opencode` binaries
2. If missing, link **official** installers only
3. Show the three-line attribution before the board opens
4. Ask where work lives
5. Open the URL

If an engine is missing, the board still loads in Cos-only mode and the footer says which engine is absent. Do not silently pretend OpenBot *is* the missing engine.
