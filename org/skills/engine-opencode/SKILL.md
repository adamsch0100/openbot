---
name: engine-opencode
description: How OttoBot seats use OpenCode — folder, diff card, Accept gate, MCP locks
whenToUse: Every Builder / Code job on a seated CEO. Cos never loads this.
---

# Engine — OpenCode

## Owns
Local code change in the aimed CEO’s work folder via OpenCode. Diff card waits for the human. Push/merge/deploy stay operator.

## Stopline
- Path is `opencode run` → **diff card** → Accept / Reject. Never silent-apply to production.
- No git push, merge, force-push, or production deploy from this seat.
- No secrets in the repo, brains, or RESULT. Keys stay in vault / env, never in diffs.
- Do not reimplement Hermes cron, gateway, or browser inside OpenCode.
- Cos never sees GitHub / git MCP schemas. MCP only when this CEO toggled it onto Code.
- No “while I’m here” refactors. Ticket scope only.

## Menu (know it; do not turn everything on)

| Capability | When unlocked on this seat |
|---|---|
| Edit files in CEO work folder | Builder / Code jobs |
| LSP / diagnostics | Via OpenCode in that folder |
| GitHub / git MCP | Only if this CEO authorized MCP for Code |
| Diff card + Accept/Reject | Always — human gate |
| Push / merge / publish | Operator only, never auto |

## Steps
1. Read the ticket / HANDOFF. Confirm the aimed CEO folder (not another CEO’s tree).
2. Change glue, board, docs, presets, or that CEO’s product code — wire `hermes` / `opencode` binaries; do not vendor those engines.
3. Produce a local diff. Name the engine **OpenCode** on the job card.
4. RESULT ≤ 20 lines + VERIFY (what to check). Raw log stays in `jobs/`.
5. Patch this CEO’s desk status: Now / Last / Next / Blocker. Diff parks on Needs-you until Accept.
6. Reject restores. Accept is human-only for merge/push when policy says so.

## What good looks like
Folder → change → diff card → desk status. A stranger can Accept or Reject without reading chat. Scope matches the ticket; no engine reimplementation, no secrets in the tree.
