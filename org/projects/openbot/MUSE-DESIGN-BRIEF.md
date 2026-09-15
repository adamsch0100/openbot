# OttoBot — Muse Spark design pass (world-class CEO desk)

**Engine:** OpenCode · model `opencode/muse-spark-1.3-contributor-free` (Go catalog; use `opencode/muse-spark-1.3` if Contributor ack blocks)  
**Scope:** `web/index.html`, `web/app.js`, `web/styles.css`, `BRAND.md` tokens only. No third runtime. No secrets in git.

## How we run this program (operator + Cursor + Muse)

**Default loop: Cursor acts as the operator (you). Muse implements in the repo. Cursor reviews, steers, fixes glue/tests, ships when Adam says push.**

| Role | Who | Job |
| --- | --- | --- |
| **Adam** | You | Taste, “world-class” bar, live test, push live |
| **Cursor agent** | Me in this chat | Write the pass directive, review Muse diffs, browser snapshots for QA, fix `app.js` hooks/tests, refuse scope creep |
| **Muse Spark** | `opencode/muse-spark-1.3-contributor-free` | **Implement** HTML/CSS (and copy) in `web/` per directive — world-class Phase 1 desk |

Muse is the hands; Cursor is the eyes and judgment on your behalf. Optional critique-only run: `scripts/run_muse_suggestions.ps1`.

**Per pass:** edit `org/projects/openbot/MUSE-DIRECTIVE.md` (one screen of must-do / must-not), then `scripts/run_muse_design.ps1`.

Phases ship one at a time to `master` → Railway.

**Phase 1 (now) — world-class bar before Phase 2:** Executive desk at the bottom of chat: inset pill **work ribbon** fused with **composer dock**; chat head breathes (display type, folder line); work sheet feels like a drawer over the thread (not a second app). Counts still from `workCounts()` only. Muse uses **`opencode/muse-spark-1.3-contributor-free`** only; Cursor merges and tests.  
**Phase 2:** Briefing card + honest job states (Live / Quiet / Stuck / Failed / Scheduled).  
**Phase 3:** CEO desk cards in rail; Wallets UI rename polish.  
**Phase 4:** Motion + mobile bottom sheet polish.

Local Muse: `python scripts/setup_opencode_go.py` (paste Go key at prompt, never in chat) then `scripts/run_muse_design.ps1`.

## Operator north star

Clear. Helpful. Speaks like a human CEO. Simplicity **and** transparency. One composer always. Chat is how I intervene; work must stay glanceable without eating the screen.

I do **not** want to learn: board, engine, Cos, shared pool, gateway scar, failover chains.

## Product shape (decided direction — Kimi + operator)

**Chat is the room (~75%). Work is a thin always-on status ribbon (~25% of attention, not viewport).**

- Ribbon (desktop): one horizontal strip **above the composer**: `Running 2 · Due 3 · Failed 1 · Schedule · Goals 4` — each segment = label + count, color = health.
- Tap segment → **sheet/drawer slides up over chat** (does not navigate away). × or tap again → conversation exactly where it left off.
- Mobile: same ribbon above keyboard; segment → bottom sheet ~70%; chat preserved underneath. No 5-tab header scroll.
- **Counts and expanded list share one live source** (jobs digest). Never show a count that does not match the list.

### Job honesty (fix citation-audit distrust)

Plain states — never a lying “Running” for 12h:

| State | Meaning |
| --- | --- |
| **Live** | Green only with recent real activity |
| **Quiet** | No activity in N minutes — gray/amber |
| **Stuck** | Amber + one-line human reason + what is being tried |
| **Failed** | Red + next step (never buried in a total) |
| **Scheduled** | Neutral, next run time |

Ribbon “Running N” must list those N jobs **by name** when opened.

## Keys / models (Wallets)

Rename mentally to **Wallets**:

- Saved keys first: plain name, position number, drag reorder = usage order, delete.
- Add key: one paste + name + “Key saved ✓”.
- Models: one row — **Auto** with copy: “OttoBot picks the right model for chat, thinking, code, research, and operations. Pin only to lock.”
- No engine families, no “board → Hermes → OpenCode” failover text.

## Goals vs Work vs chat

- **Goals** = why (week / month / horizon cards per CEO).
- **Work** = what (running, due, results, schedule).
- **Chat** = steering wheel.
- Empty goals: CEO asks in chat to accept founding — never auto-invent crons.

Work rows should show **which goal** they serve when known.

## Visual direction (executive suite)

- Ink/charcoal base, parchment/brass accents (existing bronze tokens).
- Serif display for CEO names and briefing; clean sans for data.
- Each CEO = **desk card** with status lamp (not anonymous list row).
- Top of conversation: **briefing card** — 2–3 lines Chief of Staff morning digest.
- Notifications surface only **Needs you** (Accept gates).

## Current code reality (do not throw away)

- Work chip + `work-peek` tabs exist; evolve peek → ribbon + sheet, do not remove glanceability.
- `paintWorkTabs`, `workCounts`, `openWork`, `chatSchedule` activity sheet — extend, don’t duplicate a second work system.
- Chief of Staff label (not Cos). Keys v192 Auto-pick copy shipped.

## Deliverables for this pass

1. **HTML/CSS mock in repo** — ribbon + sheet + briefing card + CEO desk card in chat head (desktop + 390px).
2. **Short `DESIGN.md` addendum** — what changed and why (P0 screens only).
3. **No backend cron/hermes changes** in this pass.
4. Keep footer MIT credit lines untouched.

## Acceptance

- I can see all five work segments without opening a mystery chip.
- Opening work never destroys scroll position in chat.
- Failed/stuck visually distinct from live.
- Every visible label passes “read aloud to a non-engineer” test.
