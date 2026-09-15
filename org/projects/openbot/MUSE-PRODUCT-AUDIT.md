# OttoBot — operator product audit (Cursor + browser, 2026-09-15)

**Audited:** local board `http://127.0.0.1:8787/` · cache **v=194** (Muse Phase 1 dock/ribbon)  
**Method:** accessibility snapshots + mobile (~390px) screenshots; desktop snapshot (narrow viewport in tool)  
**Audience for fixes:** Muse Spark + Cursor implementation passes · Adam taste gate before Railway

## What we are building (give Muse this every pass)

OttoBot is the **operator control plane** for multiple **CEOs** (businesses): SAA Homes, ListLogic, Nadia, OttoBot itself, Support, etc. One **Chief of Staff** chat steers; each CEO has desk memory (`STATUS.md`), goals, Hermes (think/schedule/ops) and OpenCode (code). Adam runs businesses **hands-off** toward goals; intervenes in **one composer**; must **trust** what “running” means and **see** engine work without learning “board vs gateway vs pool.”

**Non‑negotiables:** MIT engine credit; name engine on job cards; Accept gates for publish/pay/delete/sign; chat is UI not prompt archive; simplicity **and** transparency.

---

## Executive verdict

**Not release-ready.** Phase 1 polish (fused `#chatDock`, work ribbon) is a thin skin on a product that still behaves like an **internal ops console** dumped into a chat thread. The gap is not “more bronze CSS” — it is **information architecture**, **honest work states**, **CEO-grade language**, and **separating operator surfaces** (chat / work / tools / setup).

---

## P0 — ship blockers (trust + daily use)

| # | Finding | Evidence | World-class target |
|---|---------|----------|-------------------|
| P0.1 | **Chat answers in engineer/registry voice** | “What is going on?” returns `v154`, `BLOCKED`, `PROCESS LAW`, multi-CEO paste blocks, version changelog lines | **Briefing card** (2–3 sentences) + optional “Details” fold; status reads like a human CoS; version strings never in default stream |
| P0.2 | **No morning digest at top of thread** | Desktop snapshot: stream empty above composer; mobile: wall of text after one question | Persistent **Today** card: Needs you (1) · In motion (N) · Quiet CEOs · Next due |
| P0.3 | **Results sheet = changelog graveyard** | Opening Results shows “Resolved · 12” with rows like “v161”, “Neighborhood audit…”, duplicate paragraphs | Results = **named jobs** with state, engine, CEO, time, one-line outcome; group “System notes” separately or hide from default |
| P0.4 | **Running/Due counts vs felt reality** | Operator distrust (citation audit, stuck “Running”) — ribbon does not show Live/Quiet/Stuck | Phase 2 honesty model; ribbon segment opens list **by job name** with state chip; stale jobs → Quiet/Stuck with reason |
| P0.5 | **Settings drawer is a second product** | Snapshot lists 50+ headings (Keys, MCP, Routines, Self-Build, X intake…) exposed in same layer as chat | **Setup** only on first run + gear; advanced behind “Advanced”; per-CEO settings only when CEO selected |
| P0.6 | **Tools tab feels like “leave OttoBot”** | `#tools/opencode` — embed + “Open in tab”; no bridge from chat job → Watch live | **Watch** affordance on every Code/Hermes job; mini live log in sheet; Tools = inspector, not home |

---

## P1 — chat experience (the room)

| # | Finding | Target |
|---|---------|--------|
| P1.1 | Chief of Staff vs aimed CEO unclear when rail shows many CEOs | Header: **who is speaking** + **who work applies to**; switching CEO clears/reframes thread context visibly |
| P1.2 | User bubble OK; agent reply is unstyled prose block | Message types: **Briefing**, **Answer**, **Job card**, **Needs you** — distinct cards, scannable |
| P1.3 | Composer placeholder good; no suggested starters on empty desk | 3 chips: “What’s going on?”, “What needs me?”, “Open SAA Homes” |
| P1.4 | Attach/send row cramped on mobile | Dock already fused — add safe-area, 44px targets, sheet must not cover composer |
| P1.5 | Cron/heartbeat noise in history | Already partially fixed — enforce: cron landings **only** in Work → Schedule/Results, never main narrative |

---

## P1 — Work ribbon + sheet (the glance layer)

| # | Finding | Target |
|---|---------|--------|
| P1.6 | Ribbon exists (Running, Due, Results, Schedule, Goals) — good direction | Keep; add **Failed** as first-class segment when count > 0 (partially in JS) |
| P1.7 | Activity sheet on mobile covers thread awkwardly | Bottom sheet ~65–70%, dimmer, drag handle, **preserve scroll** (spec in DESIGN-BRIEF) |
| P1.8 | Results row “Auto” / “RESOLVED” — meaningless | Row: `CEO · job title · Failed/Healthy · Hermes` + tap → detail |
| P1.9 | Goals not visibly tied to work | Work row subtitle: “For: Weekly GBP goal” when link known |

---

## P1 — Hermes & OpenCode visibility

| # | Finding | Target |
|---|---------|--------|
| P1.10 | Engine attribution buried in text | Every active job: **pill** `Hermes Agent` / `OpenCode` / `Board` |
| P1.11 | No unified “in flight” strip | When any job live: slim **Live now** bar above ribbon (job name, engine, last step, Watch) |
| P1.12 | OpenCode/Hermes tabs duplicate setup copy in DOM | Tools stage: CEO picker + embed only; move Setup wizard out of Tools |
| P1.13 | “Checking engines…” in settings | Engines status on **This CEO** card in rail: green/amber/red one line |

---

## P2 — desktop layout

| # | Finding | Target |
|---|---------|--------|
| P2.1 | Org rail + chat + drawers — density OK for power user, not for “CEO on phone” | Desktop: rail = **desk cards** with lamp; chat = 70% width; sheet side-by-side on wide (CSS started) |
| P2.2 | Chat/Tools top tabs compete with ribbon | Chat/Tools stay; Tools default sub: Code \| Hermes with clear “You’re watching {CEO}” |
| P2.3 | Empty desktop stream | Same briefing card as mobile; never blank |

---

## P2 — mobile layout

| # | Finding | Target |
|---|---------|--------|
| P2.4 | Hamburger rail works but thread feels secondary | After open CEO: collapse rail; focus chat |
| P2.5 | Results sheet + status text collision | Sheet z-index and padding so last message not hidden behind sheet header |
| P2.6 | Long unbroken status paragraphs | Max width, line-height, section collapse |

---

## P3 — polish & brand

- Serif for names/briefing; sans for data (partially there).
- **Needs you** as only interruptive notification style (not every fail).
- Wallets rename + simplify keys UI (per DESIGN-BRIEF).
- Footer credit: fix missing spaces in “Research)and” in DOM (typo).

---

## What Muse Phase 1 did well

- `#chatDock` sticky cluster; ribbon segment styling (`.work-ribbon`, `.on`/`.hot`/`.need`/`.is-fail`).
- Activity sheet pattern (drawer over thread).
- Composer + ribbon visually grouped — right **metaphor**, needs **content** pass.

---

## Recommended program order (after this audit)

1. **Muse Pass A (docs only):** `MUSE-WORLDCLASS-BRIEF.md` — screen-by-screen spec, component list, copy rules, P0–P3 with acceptance tests.  
2. **Cursor Pass B:** `app.js` — stream rendering (briefing card, message types, cron firewall), `workCounts` honesty hooks (read-only if backend not ready).  
3. **Muse Pass C:** CSS/HTML for briefing + sheet + live strip per brief.  
4. **Adam:** live URL hard refresh · throwaway CEO smoke · push `master`.

---

## Acceptance tests (operator, plain language)

- Ask “What’s going on?” → no version numbers in first screenful.  
- With a failed SAA job → see **Failed 1** on ribbon, name visible without scrolling changelog.  
- Start Code job → **Watch** opens Tools with correct CEO folder within one tap.  
- Open Results → at most 5 recent human-meaningful outcomes before “Older”.  
- New user: Setup in <3 steps before chat; Advanced hidden.  
- Mobile 390px: composer always visible; sheet closes without losing scroll position.

---

## Files Muse may read

- `org/projects/openbot/MUSE-DESIGN-BRIEF.md`
- `BRAND.md`, `OPENBOT.md` (UX honesty)
- `web/index.html`, `web/styles.css`, `web/app.js` (structure only for Pass A)
- This file: `MUSE-PRODUCT-AUDIT.md`

**Pass A must not edit `web/`** — output only `org/projects/openbot/MUSE-WORLDCLASS-BRIEF.md`.
