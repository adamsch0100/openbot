# OttoBot — Muse World-Class Brief (north-star UX spec)

**Status:** Pass A, docs-only. Do not edit `web/`, Python, or backend in this pass.
**Inputs:** `MUSE-DESIGN-BRIEF.md` (direction) + `MUSE-PRODUCT-AUDIT.md` (2026-09-15, v=194) + `BRAND.md` + `OPENBOT.md`
**Engine for implementation passes:** `opencode/muse-spark-1.3-contributor-free` only (fallback `opencode/muse-spark-1.3` if Contributor ack blocks). No third runtime.
**Output of this file:** the single spec Muse (hands) + Cursor (eyes/judgment) + Adam (taste gate) build against until shippable.
**Non-negotiables (from audit + OPENBOT.md):** MIT engine credit on every surface; every job card names its engine; Accept gates for publish/pay/delete/sign; chat is UI not prompt archive; Chief of Staff label (never "Cos" in UI); one composer always; no secrets in git/chat/brains.

---

## 1. Product promise (one paragraph, non-engineer)

OttoBot is your executive desk for running real businesses hands-off. You talk to one Chief of Staff in one chat thread; each business (SAA Homes, ListLogic, Nadia, OttoBot itself, Support) has its own CEO desk with memory, goals, and workers. You glance at a thin work ribbon to know what is moving, what is stuck, and what needs your approval — and you steer everything by chatting. You never learn what a board, engine, pool, gateway, or failover chain is. If it needs you, it asks plainly. If it doesn't, it stays quiet and keeps working.

Read-aloud test: every sentence above must make sense to a non-engineer landlord or agency owner. If a label fails that test, it does not ship.

---

## 2. Core loops (Goals → Work → Chat steering → Engines)

There are exactly four concepts. Never a fifth.

1. **Goals = why.** Week / month / horizon cards per CEO. Written or accepted in chat. Empty state never auto-invents work: the Chief of Staff asks "Want to set your first goal for SAA Homes?" and waits for Accept. Work rows cite their goal ("For: Weekly GBP goal") when the link is known (audit P1.9).
2. **Work = what.** Running, due, failed/stuck, results, schedule. One live jobs digest feeds both counts and lists — a count that does not match its list is a ship-blocking bug (DESIGN-BRIEF § Product shape). Honest states only: **Live / Quiet / Stuck / Failed / Scheduled** (see §4).
3. **Chat = steering wheel.** One composer, always visible, always the same thread position after any sheet closes (scroll preserved). Chat issues steering (approve, redirect, kill, ask); it never becomes a changelog dump. Cron/heartbeat landings go to Work → Schedule/Results only, never the main narrative (audit P1.5).
4. **Engines = how (attributed, not taught).** Hermes Agent does thinking/scheduling/ops/memory. OpenCode does code/diffs. Board does Chief-of-Staff orchestration and status. Every job card carries one engine pill — `Hermes Agent` / `OpenCode` / `Board` — per BRAND.md honesty rule. The user never picks an engine; Auto routes. "Routes coding jobs to OpenCode / Schedules and memory go through Hermes Agent" are the only allowed explanatory sentences.

Loop in one line: **CEO sets Goals → Work moves via Engines → Ribbon shows truth → Chat steers or Accepts → STATUS.md records Now/Last/Next/Blocker.**

Desk-status mirror: UI labels "Working on / Just did / Up next / Stuck" map 1:1 to `brains/STATUS.md` Now / Last / Next / Blocker. Status questions read STATUS.md only.

---

## 3. Screen inventory

Global frame (both form factors): **Org rail (left) | Chat room (center, ~75% attention) | Work sheet (drawer over chat, not a page) | Tools (inspector, not home) | Setup/You (first-run + gear only).** Top tabs stay exactly `Chat | Tools`. No 5-tab header scroll (DESIGN-BRIEF mobile rule).

### 3.1 Chat (the room)

**Desktop (≥1024px):**
- Center column max ~720px, rail left (~280px) as CEO desk cards (§4.6). Stream top always shows **Today briefing card** (§4.1) — never blank (audit P2.3).
- Composer dock: sticky bottom cluster `#chatDock` = work ribbon + Live strip (when active) + composer, fused as one inset pill unit (Phase 1 skin — keep it). Chat/Tools tabs stay top; they do not compete with the ribbon because the ribbon lives with the composer, not the header (audit P2.2).
- Sheet behavior on wide: side-by-side drawer (right ~380px) over dimmed thread, thread scroll frozen + restored on close. Esc / × / re-tap segment closes.

**Mobile (~390px):**
- Rail hidden behind hamburger; once a CEO is opened, rail collapses and chat takes focus (audit P2.4). Header shows: back chevron + **who is speaking** (Chief of Staff) + **aimed CEO** + engine-health dot (§4.6 compact). No ambiguity when many CEOs exist (audit P1.1).
- Ribbon sits directly above keyboard/composer, horizontally scrollable with snap, 44px min targets, `env(safe-area-inset-bottom)` padding (audit P1.4).
- Segment tap → bottom sheet ~65–70% height, drag handle, dimmer, swipe-down to dismiss. Composer stays mounted underneath (never unmounted, never covered by sheet header — fix P2.5 collision with explicit z-index: thread < dimmer < sheet < dock? No: sheet slides *above* thread but *below* dock so composer stays tappable; spec: `thread z1 / dimmer z40 / sheet z50 / dock z60` — sheet top edge stops 8px above dock).
- Empty desk: composer placeholder + 3 starter chips: "What's going on?" / "What needs me?" / "Open SAA Homes" (audit P1.3).

**Both:** switching CEO visibly reframes context — header swap + one-line system divider in thread ("Now with SAA Homes — thread context switched") + briefing card swaps. Never silently mix CEOs (audit P1.1).

### 3.2 Work sheet (the glance layer)

One sheet, five segments, one source. Ribbon segments (desktop order): `Failed (only when >0, red-first) · Running · Due · Results · Schedule · Goals`. Mobile order identical; Failed badges to front when hot. Each segment = label + count. Color = health: red fail, amber stuck/quiet, green live, neutral scheduled/goals.

- Tap segment → sheet opens to that tab. Tap again / × / swipe → closes, chat scroll restored to exact px (store `scrollTop` on open, restore on close; do not re-render thread while sheet is open).
- Counts = `workCounts()` output only. List = same digest filtered. This is the Phase 1 contract: Muse never invents a second counter (DESIGN-BRIEF "Current code reality": extend `paintWorkTabs`, `workCounts`, `openWork`, `chatSchedule` activity sheet — do not duplicate).
- Results tab: max 5 human-meaningful outcomes, then "Older" fold. System notes (version bumps like "v161", duplicate paragraphs) grouped under collapsed "System notes" or hidden from default (audit P0.3). Every row is a **work row** (§4.3).
- Schedule tab: plain-language next-run lines ("Tue 9:00 — GBP review"), never cron expressions in default view. Cron strings live behind tap → detail.
- Goals tab (in sheet, glanceable): goal cards with linked work counts; empty → inline "Ask Chief of Staff to propose goals" button that posts a chat prompt (never auto-creates crons).

### 3.3 Org rail (CEO desks)

**Desktop:** vertical stack of **CEO desk cards** (§4.6) — lamp + name (serif) + one-line status + Failed/Due mini-counts. Selected card raised. "All / Chief of Staff" card on top as home. Bottom: Setup gear only.

**Mobile:** rail is a drawer from hamburger; selecting a CEO closes drawer and focuses chat. No CEO settings inside rail — tap card body switches; tiny "···" opens per-CEO panel only when that CEO is aimed (audit P0.5: per-CEO settings only when selected).

### 3.4 Tools — Code / Hermes (inspector, not home)

Tools is where you **watch**, not where you live (audit P0.6). Structure:

- Sub-tabs: `Code (OpenCode) | Hermes`. Header line always: "You're watching **{CEO}** · {folder}".
- No setup-wizard copy inside Tools (move to Setup per audit P1.12). Contents: CEO picker (mirrors rail selection), live embed/log, Open-in-tab link, and per-job **Watch** deep-link target.
- Entry: every Code/Hermes work row + every Live-strip item has a **Watch** button → opens Tools with correct CEO + job/session focused, one tap (acceptance test). Closing Tools returns to chat exactly where left.

### 3.5 Setup / You (first-run + gear)

- First run = ≤3 steps: 1) Otto mark + 3-line MIT credit (BRAND.md) + Detect `hermes`/`opencode` (official installers only if missing), 2) "Where does work live?" (folder), 3) Open desk + ask "What is this project and what is blocked?" (OPENBOT.md first-run). Missing engine → Cos-only mode + footer names the absent engine (never fake it).
- After first run, Setup lives behind gear only. **Advanced** collapsed by default: job log, tokens, engine used, MCP toggles, raw brains, sessions, crons, `opencode.json`. Settings drawer must not be a 50-heading second product (audit P0.5).
- Keys → **Wallets** rename (DESIGN-BRIEF): saved keys first (plain name, position number, drag = usage order, delete), add = one paste + name + "Key saved ✓", models = one **Auto** row with copy "OttoBot picks the right model for chat, thinking, code, research, and operations. Pin only to lock." No engine families, no failover-chain text.
- Vault/PIN behavior unchanged (STATUS.md Vault): keys in `secrets.local.json`, PIN gates board, never paste keys/passwords in chat.

---

## 4. Component spec

Tokens (BRAND.md + existing bronze system — Muse touches tokens only, never logo/credit): ink/charcoal base, parchment/brass accents; serif display for CEO names + briefing; clean sans for data/counts; status lamp palette: green Live, gray/amber Quiet, amber Stuck, red Failed, neutral Scheduled. Keep footer MIT credit lines byte-identical (fix only the "Research)and" missing-space typo flagged in audit P3).

### 4.1 Briefing card ("Today") — fixes P0.1, P0.2

Persistent top-of-thread card, one per aimed scope (Chief-of-Staff rollup or single CEO). Content: 2–3 sentences, human CoS voice, then a 1-line stat strip, then optional "Details" fold.

```
┌ Today — SAA Homes · Tue Sep 15 ─────────────┐
│ SAA showings are on track. One GBP review   │
│ needs your approval before noon. ListLogic  │
│ is quiet since yesterday evening.           │
│ ● Needs you 1 · ● In motion 2 · ○ Quiet 1   │
│ Next due: GBP review · 12:00  [Details ▾]   │
└─────────────────────────────────────────────┘
```

Rules: no version strings (`v154`), no `BLOCKED`/`PROCESS LAW`/registry words in default view — those live under Details. Empty desk shows briefing + 3 starter chips, never blank. Rendered by stream renderer (Cursor Pass B), styled by Muse (Pass C).

### 4.2 Message types — fixes P1.2

Four agent bubble styles, visually distinct:

| Type | Use | Style |
|---|---|---|
| **Briefing** | Morning digest, "What's going on" answers | Serif, parchment tint, lamp dot, stat strip |
| **Answer** | Normal CoS reply | Default prose, max-width ~62ch, generous line-height, collapsible sections for long text (P2.6) |
| **Job card** | Any work item surfaced in chat (started/finished/blocked) | Mini work row (§4.3) inline: title + state chip + engine pill + Watch/Accept actions |
| **Needs you** | Only interruptive style (§4.5) | Brass border, must be Accept-gated action |

User bubble unchanged (already OK). Cron/heartbeat never render as Answer — firewall to Work (P1.5).

### 4.3 Work row — fixes P0.3, P1.8, P1.9, P1.10

One row pattern everywhere (sheet lists, Results, inline job cards). No second row design.

```
[● state chip]  Job title (human verb + object)        [engine pill]
                CEO · 12m ago · For: Weekly GBP goal    [Watch] [···]
                One-line outcome or next step (never a changelog id)
```

- Title: human ("GBP photo refresh"), never "v161" / "RESOLVED" / "Auto". Failed/Stuck rows show reason + next step inline ("Photo upload rejected — retrying with smaller files" / "Needs you: approve publish").
- State chip: Live (green pulse) / Quiet (gray) / Stuck (amber) / Failed (red) / Scheduled (neutral + next time).
- Engine pill always: `Hermes Agent` / `OpenCode` / `Board`. Cos-authored notes = Board.
- Subtitle line 1: `CEO · relative time · For: {goal}` when link known. Line 2: one-line outcome. Tap row → detail (full log, engine session, goal link, history). Results "Auto"/"RESOLVED" copy is banned (§5).

### 4.4 Live strip ("Live now") — fixes P1.11

Slim bar directly above ribbon, rendered only when ≥1 Live job exists. Content: strongest-signal job (most recent activity): `● Live now — {job name} · {engine} · {last step, ≤60ch} [Watch]`. If >1 live, " +N more" tap opens sheet Running tab. Never shows for Quiet/Stuck/Failed — those live in ribbon counts. Dismissing = sheet open, not job kill (kill lives in row detail with Accept gate when destructive).

### 4.5 Needs-you card (Accept gates) — fixes P0.2, P3-notification rule

The **only** interruptive notification. Used for publish / pay / delete / sign / any irreversible step. Pattern: brass-bordered card in thread + stat-strip bump ("Needs you 1") + Failed-segment-adjacent badge. Content: what, why, cost/scope, expiry, [Approve] [Edit] [Dismiss]. Every other failure is a red Failed row, not a popup. Never notify on every fail.

### 4.6 CEO desk card — fixes P1.1, P1.13, P2.1

Rail unit (desktop) + header source (mobile). Not an anonymous list row.

```
┌ ○ SAA Homes ─────────┐
│ Showings on track    │  ← one-line human status (from STATUS.md Last/Next)
│ Failed 1 · Due 2     │  ← mini counts, same digest
│ Engines ● (one line) │  ← green/amber/red: "Hermes ● · Code ●" (replaces "Checking engines…")
└──────────────────────┘
```

Lamp = worst health across that CEO (red > amber > green > neutral). Serif name. Tap = switch scope (with visible reframe per §3.1). "This CEO" engines line is the only engines-health surface in normal use; full versions/dash-home/gateway detail lives in Advanced.

### 4.7 Sheet chrome (shared)

Drag handle, dimmer, focus trap, Esc closes, scroll-lock thread behind, restore `scrollTop` on close. Bottom-sheet mobile / side-drawer wide via same markup + breakpoint. Last message + composer never hidden behind sheet header (explicit padding + z-index per §3.1). Sheet header shows segment title + count + close ×.

---

## 5. Copy rules

### 5.1 Forbidden in default views (move to Details/Advanced or delete)

- Version/changelog ids as content: `v154`, `v161`, "Resolved · 12" as a row title, bare `RESOLVED`, bare `Auto` as a result.
- Registry/ops voice: `BLOCKED`, `PROCESS LAW`, `INDEX`, `gateway scar`, `shared pool`, `failover chain`, `board → Hermes → OpenCode`, engine family names, cron expressions, `Checking engines…` (replace with one-line lamp, §4.6).
- "board", "Cos" (always "Chief of Staff" in UI), "pool", "scar", "mesh", "CRD".
- Failover exposition ("board → Hermes → OpenCode will retry…") → replace with Stuck row reason + what is being tried (§4.3).
- The typo "Research)and" (fix spacing; credit lines otherwise untouched).

### 5.2 Allowed CEO voice (read-aloud test)

- "On it." (Otto acknowledgment; consumer line, never inside credit block).
- Briefing: "SAA showings are on track. One review needs your approval before noon."
- Work: Live / Quiet / Stuck / Failed / Scheduled + one-line human reason ("No activity in 40 minutes — gray until the next showing sync").
- Schedule: "Tue 9:00 — GBP review" (never `0 9 * * *` outside detail).
- Models: "OttoBot picks the right model for chat, thinking, code, research, and operations. Pin only to lock."
- Wallets: "Key saved ✓".
- Needs-you: "Approve publish to Google profile? This posts 6 photos. [Approve] [Edit] [Dismiss]".

### 5.3 Engine naming on cards (BRAND.md lockup)

- Pills: `Hermes Agent`, `OpenCode`, `Board` (for Cos-authored). Full credit sentences allowed only in About/footer/first-run/Advanced: "OttoBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly). Not affiliated with, sponsored by, or endorsed by those projects." Footer lockup `OTTOBOT · On it. / Engines: Hermes Agent · OpenCode` stays, names as text links.
- Never: product titled Hermes/OpenCode/Grok Bot; engine names inside the Otto mark; "Powered by" partnership stamps; hiding the engine to look like one original agent.

---

## 6. P0 / P1 / P2 backlog (with acceptance criteria each)

### P0 — ship blockers (trust + daily use)

- **P0.1 Engineer voice in chat.** Rework stream renderer: Briefing card + Answer/Job/Needs-you types (§4.1–4.2, 4.5); version strings + registry words behind Details fold. *Accept:* ask "What's going on?" → zero version numbers / BLOCKED / PROCESS LAW in first screenful on desktop + 390px.
- **P0.2 No morning digest.** Persistent Today briefing card (§4.1): Needs-you (n) · In motion (n) · Quiet (n) · Next due. Never blank. *Accept:* cold load with any CEO shows Today card above composer without asking.
- **P0.3 Results = changelog graveyard.** Work-row rewrite (§4.3) + "System notes" fold; ≤5 human outcomes before "Older". *Accept:* open Results → every visible row has job title + state + engine + CEO + time + one-line outcome; no bare "v161"/"Auto"/"RESOLVED".
- **P0.4 Running/Due vs felt reality.** Honesty model Live/Quiet/Stuck/Failed/Scheduled (§4.3); ribbon Running opens the N named jobs; stale → Quiet/Stuck with reason + what-is-tried. Counts ≡ list (single digest). *Accept:* ribbon "Running N" lists exactly N named jobs; a 12h-silent "Running" never renders green.
- **P0.5 Settings is a second product.** Setup ≤3 steps (§3.5); everything else behind gear → Advanced; per-CEO settings only when aimed. *Accept:* new user reaches chat in ≤3 steps; default drawer shows no MCP/Routines/Self-Build/X-intake headings.
- **P0.6 Tools feels like leaving.** Watch affordance on every Code/Hermes row + Live strip (§4.4); Tools header "You're watching {CEO}"; mini live log in sheet detail. *Accept:* Start Code job → one tap on Watch lands in Tools with correct CEO folder focused.

### P1 — chat + glance layer (must-have polish)

- **P1.1 Who is speaking / whose work.** Header + CEO-switch reframe divider (§3.1). *Accept:* with 3+ CEOs, header always names speaker + aimed CEO; switch posts visible divider.
- **P1.2 Message types.** Four bubble styles (§4.2). *Accept:* briefing/answer/job/needs-you visually distinct in snapshot.
- **P1.3 Empty-desk starters.** 3 chips (§3.1). *Accept:* empty desk shows all three, each posts correctly.
- **P1.4 Cramped dock on mobile.** 44px targets, safe-area, sheet-below-dock z-index (§3.1). *Accept:* 390px composer always tappable with sheet open.
- **P1.5 Cron firewall.** Cron/heartbeat → Work only (§4.2). *Accept:* 24h of cron traffic leaves zero main-narrative landings.
- **P1.6 Failed as first-class segment.** Ribbon shows Failed segment whenever count >0 (red-first). *Accept:* failed SAA job → "Failed 1" visible without opening any chip.
- **P1.7 Sheet covers thread awkwardly.** 65–70% bottom sheet + dimmer + handle + scroll preserve (§3.2, §4.7). *Accept:* open/close sheet → chat `scrollTop` identical ±2px.
- **P1.8 Results row meaning.** Work-row pattern everywhere (§4.3). *Accept:* zero rows titled "Auto"/"RESOLVED".
- **P1.9 Goals tied to work.** "For: {goal}" subtitle when known (§4.3). *Accept:* any goal-linked job shows its goal in row + detail.
- **P1.10 Engine pill on every active job.** (§4.3, §5.3). *Accept:* every Running/Live row shows exactly one of Hermes Agent/OpenCode/Board.
- **P1.11 Live-now strip.** Slim bar above ribbon when live work exists (§4.4). *Accept:* live job → strip shows name + engine + last step + Watch.
- **P1.12 Tools dedup.** CEO picker + embed only in Tools; setup copy moved out (§3.4). *Accept:* Tools DOM contains zero setup-wizard headings.
- **P1.13 Engines one-liner.** "This CEO" card lamp line replaces "Checking engines…" (§4.6). *Accept:* every CEO card shows green/amber/red engines line.

### P2 — layout (desktop + mobile)

- **P2.1 Desk-card rail.** Rail = lamp cards (§4.6); chat ~70% width; wide sheet side-by-side. *Accept:* desktop snapshot reads as desks, not anonymous rows.
- **P2.2 Tabs vs ribbon.** Chat/Tools top, ribbon with composer (§3.1). *Accept:* Tools default sub shows Code|Hermes + "You're watching {CEO}".
- **P2.3 Never blank.** Same briefing card desktop + mobile. *Accept:* empty stream impossible — Today card always renders.
- **P2.4 Rail collapse on mobile.** After open CEO, focus chat (§3.1). *Accept:* selecting CEO closes rail drawer.
- **P2.5 Sheet/text collision.** z-index + padding (§3.1, §4.7). *Accept:* last message fully readable with sheet open.
- **P2.6 Long prose.** Max-width, line-height, section collapse (§4.2). *Accept:* 500-word status renders scannable, no wall-of-text.

### P3 — brand polish (batch at end)

Serif names/briefing + sans data; Needs-you as sole interrupt; Wallets rename (§3.5); footer typo fix. *Accept:* read-aloud pass on all labels + credit lines intact.

---

## 7. Phased implementation map (files: `web/index.html`, `web/styles.css`, `web/app.js`)

Rules for all phases: one phase ships to `master` → Railway at a time; Adam taste-gates; Cursor merges/tests; Muse touches `web/` + `BRAND.md` tokens only; counts always from `workCounts()`; footer credit untouched.

- **Phase 1 (shipped skin, v=194 — keep): `styles.css` + `index.html`.** Fused `#chatDock` (ribbon + composer pill cluster), `.work-ribbon` segments with `.on/.hot/.need/.is-fail`, activity-sheet drawer pattern, chat-head breathing (display type + folder line). No logic changes. Done — do not regress.
- **Phase 2 (honesty + briefing — next): `app.js` first (Cursor Pass B), then `styles.css`/`index.html` (Muse Pass C).**
  - `app.js`: stream renderer (briefing card, 4 message types, cron firewall P1.5), `workCounts` honesty hooks (Live/Quiet/Stuck/Failed/Scheduled, read-only until backend ready), Failed-first ribbon segment (P1.6), scroll preserve in `openWork`, "For: goal" subtitle plumbing, `Watch` deep-link → Tools with CEO+session, Today-card data join (STATUS.md Now/Last/Next/Blocker → Working on/Just did/Up next/Stuck).
  - `index.html`: briefing-card + live-strip + needs-you + desk-card + work-row markup (no new work system — extend `paintWorkTabs`/`openWork`/`chatSchedule` sheet).
  - `styles.css`: briefing serif, state chips, engine pills, live strip, brass needs-you, lamp cards, bottom-sheet (65–70%) + wide side-drawer breakpoint, safe-area + 44px targets, z-index stack.
- **Phase 3 (rail + Wallets): `index.html` + `styles.css` mostly, small `app.js`.** CEO desk cards in rail with engines one-liner (P1.13, P2.1); Wallets rename + Auto-copy row (§3.5); per-CEO settings gating (P0.5); Tools dedup to picker+embed (P1.12).
- **Phase 4 (motion + mobile): `styles.css` + minor `app.js`.** Sheet spring/drag, lamp pulses (motion.dev cues already in tree — reuse), dimmer fades, focus-trap + swipe-dismiss, collision/padding final (P2.5), long-prose collapse (P2.6), 390px + wide snapshot QA.

Test hooks per phase: bump cache `v=` + snapshot (desktop narrow + 390px) + acceptance tests from §6 for the IDs in scope. Throwaway-CEO smoke before `master` push.

---

## 8. Risks and what NOT to build

**Risks:**
1. **Second work system.** The tree already has chip + `work-peek` + `paintWorkTabs`/`workCounts`/`openWork`. A parallel ribbon/sheet implementation forks truth and re-creates the citation-audit distrust (P0.4). Mitigation: extend, never duplicate; counts ≡ list enforced in review.
2. **Lying green.** Any "Running"/"Live" without recent real activity destroys trust permanently. Mitigation: staleness threshold + Quiet/Stuck promotion is P0, not polish; reviewer rejects green without activity proof.
3. **Chat as log tail.** Letting cron/versions/changelog into the narrative reverts P0.1/P1.5 instantly. Mitigation: renderer firewall + Details-fold rule in every review.
4. **Settings sprawl.** 50-heading drawer repeats P0.5. Mitigation: Advanced-behind-gear is a merge gate; new toggles default OFF for Cos (AGENTS.md law 6).
5. **Engine worship.** Exposing pools/gateways/failover re-teaches exactly what DESIGN-BRIEF forbids. Mitigation: copy-rules lint (§5) on every diff; attribution = pill only.
6. **Scroll destruction.** Sheet that resets thread position breaks the "room" metaphor. Mitigation: scroll-preserve acceptance (P1.7) on every sheet change.
7. **Credit slip.** Touching footer/About/first-run copy risks MIT non-compliance (BRAND.md). Mitigation: credit lines byte-identical; typo fix only.

**What NOT to build (explicit bans):**
- No third agent runtime — only Hermes Agent + OpenCode + Board glue (AGENTS.md 1–2, 8; OPENBOT.md "What we are not doing").
- No vendoring `nousresearch/hermes-agent` or `anomalyco/opencode` into this tree — wire binaries (law 8).
- No backend cron/Hermes changes in UI-only phases (Phase 1–2, this brief's Pass C) — read-only honesty hooks until backend pass is scheduled.
- No auto-invented goals/crons for empty states — chat proposes, human Accepts (DESIGN-BRIEF Goals rule).
- No Telegram CoS/occupancy/CRD, no cloud-desktop clone, no unsupervised pay-capable tools (OPENBOT.md month-ban).
- No passwords/TOTP/API keys in git, brains, chat logs, or pasted Go keys (STATUS.md Vault; Go key via `setup_opencode_go.py` prompt only).
- No new top-level tabs, no 5-tab header scroll, no second composer, no Tools-as-home, no per-fail popups beyond Needs-you.
- No engine-family pickers, failover-chain diagrams, or "board → Hermes → OpenCode" text in UI.
- No product renaming to Hermes/OpenCode/Nous/Anomaly/Grok marks; OttoBot stays the product; credit stays text (BRAND.md §§ Names/Credit).

**Done = shippable when:** §6 P0 all green on live URL (hard refresh) + 390px composer/sheet tests + throwaway-CEO smoke + Adam says push. One phase at a time to `master` → Railway.
