---
name: engine-hermes
description: How OttoBot seats use Hermes Agent — menu, home isolation, cron, MCP locks
whenToUse: Every Think, Ops, or Research job on a seated CEO. Cos never loads this.
---

# Engine — Hermes Agent

## Owns
The Hermes menu for this CEO seat: what is unlocked, what stays off, and how RESULT lands back on the board.

## Stopline
- Status / “what’s going on” / pulse → **tools off**. Desk status (STATUS / INDEX) only. Never start a gateway to answer a status question.
- Use **this CEO’s** `hermes_home` only. Do not touch another CEO’s home, cron table, MEMORY.md, or skills.
- Do not invent tools Hermes does not expose on this home.
- No Telegram / Discord / Slack mesh from the board. No SMS. No CRM send. No spend, publish, pay, delete, or sign.
- Chat is not memory. MEMORY.md / USER.md on this home are durable; thread JSON is for humans.

## Menu (know it; do not turn everything on)

| Capability | When unlocked on this seat |
|---|---|
| Desk status read/write | Always for status path (tools off) |
| Skills (`--skills` / skill_view) | After board sync into this home |
| Cron / schedule | Ops lane; create with deliver that posts RESULT to **this** CEO thread |
| Snapshot browser | Research only; a11y snapshot + refs; screenshots opt-in |
| MCP tools | Only servers this CEO toggled — never “all catalog” |
| Memory | This home’s MEMORY.md / USER.md |
| Delegation / long jobs | Think / Ops when the ticket says so |

Full picture ≠ all tools on. Name the unlocked item you will use.

## Steps
1. Confirm lane: Think (decide) · Ops (schedule / watch) · Research (look). Wrong lane → stop and reclassify.
2. Load the matching domain skill before improvising. Prefer board SKILL.md already in the packet.
3. Stay inside this CEO folder + hermes_home. Cross-CEO work is a Cos handoff, not a side quest.
4. Cron jobs: silent on success; failures and artifacts return as RESULT (≤ 20 lines). Raw log stays in `jobs/`.
5. MCP: if a needed server is off, write Blocker and stop — do not install or enable MCP yourself.
6. End by patching this CEO’s desk status: Now / Last / Next / Blocker. Name the engine **Hermes Agent** on the job card.

## What good looks like
A stranger can read RESULT and know which Hermes capability ran, on which CEO home, and what file or schedule proves it. No other CEO’s cron or memory was touched.
