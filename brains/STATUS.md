# Desk status


## Engine changelog (Steward propose)
- 2026-09-14: Mobile feel pass — 5-tab scroll row (no 4-col crush), hide Engines/pulse in bar, thumb composer dock, safe-area (board CSS).
- 2026-09-14: Micro-motion + fewer hard borders (transitions.dev cues) on mobile/desktop board CSS.
- 2026-09-14: Mobile calm UI — type scale, track dividers, layered card/button shadows (board CSS; brand fonts kept).
- 2026-09-10: Chat-as-home polish (empty stream, Ready fluff kill) + align Engines Wire auth when site/repo/railway URLs exist.
- 2026-09-10: Treat Ready…/Idle INDEX copy as fluff so org-now shows failed/due (#96 soft note).
- 2026-09-10: Hotfix loadCeoDigest → renderBotMeta so indexSummary picks up honest failed counts.
- 2026-09-10: Follow-up #94 — left-rail org-now + indexSummary use honestWorkLine (per-CEO workCounts).
- 2026-09-10: P0 serve /otto.png before OpenCode catch-all; P1 rail/Next honesty for failed + Cos Results jobIsFailed (status often None).
- 2026-09-10: Hotfix gateway/start UnboundLocalError project_tools (CEO Restart 502) — resolve hermes_home only, no shadowed import.
- 2026-09-10: Gateway Restart force-clears stale state/sock (no SSH) + resolve CEO hermes_home; Restart never returns naked 502.
- 2026-09-10: CEO Settings → Engines health chip (Hermes/OpenCode versions, dash home match, gateway, wire). Steward pins Accept-only — never silent upgrade.
- 2026-09-10: Engines health next-steps — honest red + Next: line + Restart gateway when dash/gateway wrong (no fake green, no chat spam).
- 2026-09-10: Propose pin Dockerfile Hermes→v2026.9.7 (v0.21.1) + OpenCode→1.18.30. Accept-gated deploy only — never silent upgrade.
Source of truth for this OttoBot instance. Status questions read this file only.

Now: Work is one chip. Chat stays the conversation. Engine: board.
Last: Keys are APIs OttoBot uses. Auto picks models per Chat, Think, Code, Research, Ops.
Next: Ship Work collapse to live when you want it.
Blocker: Do not mass-retry. Do not remake SAA crons. Do not Accept parked restore. Do not redeploy ListLogic replica.

## Vault

- Keys live in `secrets.local.json` on this machine (gitignored). Same idea as `.env`. Not markdown. Not chat.
- Site logins live in that same vault. You → Keys → Site logins, or approve them on a login card when a job hits a wall.
- Unlock PIN in You → Settings gates the board. Do not paste keys or passwords into chat.
- OpenCode Go wallets (same catalog): OpenCode Go first, then SAA Go, then ListLogic Go. OpenRouter PAYG last.
- Seats are Auto unless you pin: Auto stays on OpenCode Go (flash). Muse Spark on an OpenRouter id is not Auto. OpenRouter PAYG is last after the Go wallets. Empty Chat can still be the board (desk status) with no key.
- CEO pins: OttoBot + Support → OpenCode Go. SAA Homes → SAA Go. Nadia + ListLogic eligible again (not in RETIRED_CEO_IDS); seat via Add CEO after unlock — do not auto-wire here.
- Hermes native: Nous Portal subscription. Subscribe at portal.nousresearch.com/r/adam-schwartz. Connect with `hermes portal` or paste `NOUS_API_KEY`. Not in this vault yet, so Auto is Go then OpenRouter.
- PAYG: OpenRouter after the three Go wallets are empty, plus OpenCode Zen after Go quota
- Not imported as the operator surface: Telegram, SMTP, GitHub, Meta. OttoBot chat is the inbox. Telegram, if connected later, must be the same thread as this chat.

## Railway Hermes (source)

- ListLogic Hermes
- SAA Homes Hermes
- SAA Conversion Hermes
- Each already had a Go key and the same OpenRouter fallback. Lab keys stay on those Hermes instances if they were already there.

## Instance

- URL: https://openbot-production-9334.up.railway.app
- Phase: operator-only (local org)
- Work dir: this checkout
- Default: Auto on OpenCode Go, then the other Go wallets, OpenRouter last.
- Plan: org/projects/openbot/STATUS.md
- Tickets: org/projects/support/tickets (file via You → Help; Support is a CEO)
- Support files: org/projects/support/STATUS.md

## Engines

- board: this process
- OpenCode: found on PATH (official binary). Pane is a wall if web cannot bind.
- Hermes Agent: found on PATH (official binary). Dash needs Nous Portal login for Think.
