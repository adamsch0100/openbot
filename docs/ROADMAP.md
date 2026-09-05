# OpenBot Roadmap

Product map for OpenBot — the self-hosted control plane routing to Hermes Agent and OpenCode.

See `OPENBOT.md` for the spec and `AGENTS.md` for coding law.

## What Already Works (Live on Railway)

OpenBot is **shipping at https://openbot-production-9334.up.railway.app** with real operator usage:

### Core Infrastructure ✓
- **Board server** — Python stdlib-only HTTP server on loopback/Railway (8787)
- **Engine detection** — finds `hermes` and `opencode` binaries, offers install links
- **Railway deployment** — healthcheck, 0.0.0.0 binding, environment variables
- **First-run flow** — folder picker, engine detection, PIN setup, credit lockup display

### Memory & Routing ✓
- **INDEX + brains** — `brains/INDEX.md` is source of truth; 4-line brains (Now/Last/Next/Blocker) per bot
- **Org tree** — Chief of Staff, CEO projects, named workers (Think/Code/Research/Ops lanes)
- **Router** — message classification routes to Cos/Builder/Research/Ops/Think presets
- **Thread storage** — UI chat history stored per CEO/worker, but NOT sent as prompt (job packets only)
- **Job log** — receipts in `jobs/` with engine, model, tokens, USD estimate, diff metadata

### Agent Execution ✓
- **Cos (Chat)** — Hermes Agent chat with auto keyring fallback, files-first replies, staff briefing
- **Builder** — `opencode run` with JSON event streaming, git snapshots, diff+untracked capture
- **Think** — Hermes Agent job packets (INDEX + brain + extra), session resume, skills, login staging
- **Research** — fetch + Hermes snapshot with accessibility trees, login wall detection
- **Ops** — inbox tickets + Hermes cron creation (schedule parsing or Hermes-planned job)

### Spend & Wallets ✓
- **Keyring** — multiple OpenCode/OpenRouter/Nous accounts with fallback order, per-CEO overrides
- **Spend tracking** — job receipts, wallet classification (Go included quota vs PAYG), empty wallet detection
- **Spend caps** — configurable USD cap with period (week/month), staff + per-CEO overrides
- **Wallet failover** — automatic keyring walk on "insufficient balance" errors, mark-empty persistence

### UX & Approvals ✓
- **Diff cards** — Accept/Reject on Builder diffs, git restore on reject
- **Login walls** — vault logins (username/pass per site), auto-fill staging, approval flow
- **PIN unlock** — operator PIN gates the board (cookie-based unlock tokens)
- **Model picker** — seat config (Chat/Think/Code/Research/Ops) with Auto ladder, per-CEO pins
- **Live streaming** — SSE-based `chat/stream` with delta, progress, stop button
- **Activity feed** — job cards, pending approvals (diff/login), Hermes cron ingestion
- **Composer attachments** — attach button, drag-drop, paste images; thumbnails in thread; paths in job packets for Hermes/OpenCode

### Advanced ✓
- **MCP toggles** — GitHub MCP on Builder (per-CEO), OAuth credential flow
- **Hermes import** — import Railway Hermes backups, connect remote instances, pull Telegram sessions
- **Skills config** — Hermes skill allowlist (Tools OFF for Cos, on-demand for Think/Research/Ops)
- **Browser snapshots** — fetch-first ladder, snapshot worker, LOGIN_WALL marker, vault staging
- **Git awareness** — status, diff against HEAD, untracked detection, snapshot/restore
- **Multi-lane queueing** — concurrent CEO threads, message queuing during live runs
- **Reliability fixes** — Muse contributor auto-ack (500f218), CEO chat bleed fix (a9d5f66)

### Credit & Branding ✓
- **NOTICE + README** — required MIT credit lockup (Hermes Agent, OpenCode)
- **Footer** — three-line attribution, engine links, "LOCAL ORG." on mark
- **BRAND.md compliance** — no rebrand, no affiliation claim, engine name on every job card

---

## Gaps vs World-Class Multi-Agent Chat OS

OpenBot has **Week 1 done**. Here's what a hosted-bot-killer still needs:

### 1. Durable Memory UX
**What's missing:**
- INDEX edits are raw text (no structured goal/context cards)
- No memory search across job history or thread archives
- Brain notes are unstructured (no templates for project types)
- No agent-facing "last 5 decisions" summary view

**Impact:** Users manually rewrite INDEX; agents don't learn project patterns.

### 2. Sidebar Agents / Parallel Work
**What's missing:**
- No multi-agent orchestration (one composer fires one chain)
- Workers exist but have no autonomous task queue
- No "Builder is stuck, ask Research for a doc" handoff detection
- Cos doesn't spawn CEO workers automatically

**Impact:** User must manually switch CEOs; no true multi-agent collaboration.

### 3. Async Handoffs & Bus Protocol
**What's partially there:**
- `bus/` folder exists with seed contracts (`ensure_bus`, `seed_org_contracts`)
- `HANDOFF` mentioned in contracts but not enforced

**What's missing:**
- No standardized handoff file schema (TASK/STATUS/OUTPUT/NEXT OWNER)
- Agents don't read `bus/` to pick up work
- No handoff routing (e.g., Builder → Research when docs needed)
- Inbox is one-way (user → agent), not agent → agent

**Impact:** Agents only work when user sends a message; no self-driven task queues.

### 4. Routines (Scheduled Multi-Step Flows)
**What's missing:**
- Ops cron is single Hermes jobs (no multi-step routines)
- No routine templates (daily standup, weekly review, monitoring flows)
- Cron doesn't trigger CEO → worker chains
- No "every morning: check PRs, run tests, post summary" flow

**Impact:** User must manually sequence multi-step daily work.

### 5. Coding Worker Reliability
**Known bugs (some fixed, some open):**
- ✅ **FIXED (500f218):** Cos Chat instant fail on Muse Spark contributor confirm
- ✅ **FIXED (5f78632):** Hermes non-interactive model prompt blocks board runs
- ✅ **FIXED (a9d5f66):** CEO Chat bleed and pending-composer lock
- ⚠️ **Status unknown:** ListLogic SQLite history loss (INDEX: "Do not railway scale old Hermes boxes")

**What's missing:**
- No automatic retry on transient OpenCode failures
- No Builder validation (does the diff actually compile/lint/test?)
- No rollback if Accept → production breaks
- Git snapshot is local only (no branch/PR integration yet)

**Impact:** Diffs may be syntactically broken; operator catches errors manually.

### 6. Spend Transparency
**What's there:**
- Job receipts with prompt/cached/output tokens, USD estimate, wallet label
- Spend summary (used/cap/remaining) visible on board

**What's missing:**
- No per-project cost breakdown in UI (only latest spend)
- No month-over-month trend charts
- No "this CEO burned $X this week" alert
- OpenCode Go quota is from API; no local prediction when it'll hit zero

**Impact:** User discovers overspend after the fact.

### 7. First-Run & Onboarding
**What's there:**
- Folder picker, engine detect, PIN setup, first-run flag

**What's missing:**
- No "try a test job" tutorial after setup
- No sample project template (e.g., "hello world" OpenCode change)
- No engine version check (Hermes 0.x vs 1.x breaking changes)
- No OpenCode auth check (`opencode auth status`) before first Builder run

**Impact:** New users may not realize OpenCode needs separate login.

### 8. Observability & Debugging
**What's missing:**
- No live Hermes tool call progress (only OpenCode emits step-start events)
- No log tail for Hermes sessions (must open raw Hermes dashboard)
- No "replay this job with --verbose" debug mode
- Job receipts don't link to raw OpenCode JSON logs

**Impact:** Debugging "why did Research fail?" requires diving into Hermes CLI.

---

## Next PRs (Locked Ship Order from OpenBot CEO)

These are the **ranked next 3 PRs** per the CEO + CoS forward plan. Each scoped for focused implementation.

---

### **PR #1: Builder Delight Loop** ⭐
**The Week 2 gate per OPENBOT.md**: folder → `opencode run` → streaming Diff Accept/Reject → INDEX update.

**Problem:**
Builder flow works but isn't delightful yet. Operator still opens multiple windows to see INDEX updates or check job progress.

**User value:**
Ask for a one-file change → see streaming progress → Accept diff → Brief/INDEX updates immediately in the same composer view. No second window required.

**Acceptance criteria:**
1. Operator asks "add a comment to utils.js explaining the retry logic"
2. Builder streams OpenCode progress (step-start events visible)
3. Diff card appears inline with Accept/Reject
4. Operator clicks Accept
5. Brief card updates showing the change in Now/Last/Next
6. All in one composer thread — zero window switching

**What's already there:**
- `opencode run` with JSON event streaming ✓
- Diff capture + Accept/Reject flow ✓
- INDEX patching on job finish ✓

**What needs polish:**
- Stream progress rendering (OpenCode step-start events → UI progress chips)
- Inline Brief updates after Accept (currently requires refresh or status ask)
- One-shot "ask → accept → done" without clicking between panels

**Files/areas touched:**
- `web/app.js` — render OpenCode progress chips in stream, auto-refresh Brief after Accept
- `openbot/router.py` — ensure INDEX patch happens synchronously before Accept response
- `openbot/server.py` — Accept endpoint returns updated INDEX in response

**Estimated complexity:** Low-Medium (UI polish + sync flow, no new engine calls).

---

### **PR #2: Chat OS Reliability** ⭐
**The stability gate**: kill Cos/CEO hang, bleed, silent fail; always stream progress; Muse/Hermes confirm auto-ack.

**Problem:**
Recent fixes (500f218, a9d5f66) addressed Muse auto-ack and CEO chat bleed, but reliability still needs hardening. Cos status and CEO Chat must never silently fail or hang.

**User value:**
Send 10 Cos status questions + 5 CEO Chat messages → zero empty failures, zero hangs, zero "Chat didn't come back."

**Acceptance criteria:**
1. Run test suite: 10 Cos status asks (INDEX reads) + 5 CEO Chat sends (Hermes oneshot)
2. All 15 complete with visible response (even if "Hermes missing" or "wallet empty")
3. Zero silent failures (empty reply with no error card)
4. Zero composer locks longer than job timeout
5. Progress always visible (streaming or "Hermes chat starting…" chip)

**What's already fixed:**
- ✅ Muse contributor confirm auto-ack (500f218)
- ✅ CEO chat bleed isolated (a9d5f66)
- ✅ Pending-composer lock with message queueing (a9d5f66)

**What needs hardening:**
- Timeout handling: if Hermes doesn't respond in N seconds, show error card (not silent hang)
- Fallback messaging: if all keyring accounts fail, show "wallets empty" card immediately
- Progress rendering: every Cos/Chat job shows at least one progress event

**Files/areas touched:**
- `openbot/router.py` — add timeout guards on Hermes chat, fallback error cards
- `openbot/hermes.py` — surface timeout/failure as structured error (not silent empty)
- `web/app.js` — ensure every job shows progress chip, render timeout errors clearly
- `tests/` — add reliability test suite (10 status + 5 chat sends)

**Estimated complexity:** Medium (timeout logic + error surfacing + test harness).

---

### **PR #3: Sidebar Agent OS** ⭐
**The multi-agent UX**: avatars/initials, Now/Blocker chips from INDEX, busy/unread, fast CoS↔CEO switch.

**Problem:**
CEO list exists but doesn't feel like a team. No avatars, no status chips, no visual "who's working vs idle."

**User value:**
Open board → see named teammates with avatars/initials, Now/Blocker from their INDEX, busy indicator during jobs, unread badge for pending approvals. Switch CoS ↔ CEO in <3 seconds.

**Acceptance criteria:**
1. Sidebar shows Chief of Staff + all CEOs with:
   - Avatar (initials if no image, e.g., "NH" for Nadia, "CS" for CoS)
   - Now chip (pulled from that CEO's INDEX, e.g., "Builder job 3f4a2c in listlogic.homes")
   - Blocker chip if Blocker ≠ "—" (red/yellow indicator)
   - Busy spinner during active job
   - Unread badge for pending approvals (diff, login wall)
2. Click CEO → switch composer context in <3 seconds
3. Visual feels like a teammate panel (not a file list)

**What's already there:**
- Org tree with Chief of Staff + CEOs ✓
- INDEX per CEO with Now/Last/Next/Blocker ✓
- Activity feed with pending approvals ✓
- CEO/worker rename on master ✓

**What needs building:**
- Avatar/initial generation (2-letter initials from CEO name)
- INDEX field extraction per CEO (read Now/Blocker on sidebar render)
- Busy/unread state tracking (live jobs + pending approvals)
- Fast context switching (currently page-level state, needs optimized fetch)

**Files/areas touched:**
- `web/app.js` — sidebar rendering with avatars, Now/Blocker chips, busy/unread badges
- `web/styles.css` — avatar circles, chip badges, teammate panel layout
- `openbot/server.py` — `GET /api/org/summary` endpoint (returns all CEOs with INDEX Now/Blocker)
- `openbot/org.py` — helper to extract Now/Blocker from each CEO's INDEX

**Estimated complexity:** Medium (new UI components + per-CEO INDEX parsing, no new engine calls).

---

## Deferred / Later Candidates

These are **lower-priority** or **post-MVP** features. Ship the locked 3 PRs first, then revisit.

### Handoff Bus Protocol
Standardized `bus/` file schema for agent → agent async handoffs. Useful but not blocking delight or reliability.

### Builder Validation Gate
Syntax/lint/test check before Accept. Valuable but Builder delight (streaming + inline Brief) is higher leverage.

### Spend Dashboard
Per-CEO cost breakdown with trend charts. Nice-to-have; current spend summary + cap enforcement already works.

### Onboarding Tutorial
Auto-run test job after first-run. Helpful but not critical; first-run wizard already guides setup.

### Routine Scheduler
Multi-step daily flows (e.g., standup = git status → summarize → post). Powerful but complex; defer until core Chat OS is rock-solid.

### Kanban UX Over INDEX
Visual cards for Now/Next/Blocker instead of markdown editing. Improves memory UX but not urgent.

### Memory Pane Enhancements
Structured goal/context cards, search across job history. Useful but INDEX already works.

### Skills Catalog Polish
UI for browsing and toggling Hermes skills. Already configurable in Settings; catalog is polish.

---

## Reliability Bug Status (From Commit Messages)

| Bug | Status | Commit | Notes |
|-----|--------|--------|-------|
| **Cos Chat Muse fail** | ✅ **FIXED** | 500f218 | Hermes prompted `Use this model [y/N]` in non-interactive mode. Now auto-acks contributor-tier confirms when model is already seated. |
| **CEO Chat bleed** | ✅ **FIXED** | a9d5f66 | Chat was a locked global live turn. Now allows CEO switch during runs, queues messages, keeps Chat as fresh Hermes oneshot (no Telegram mid-tool junk). |
| **Pending-composer lock** | ✅ **FIXED** | a9d5f66 | Composer locked during any live run. Now queues messages per CEO/worker, unlocks after turn. |
| **ListLogic SQLite history loss** | ⚠️ **UNKNOWN** | Mentioned in INDEX | "Do not `railway scale` old Hermes boxes — use `railway down -y`." Possible: scaling drops ephemeral volume. **Action:** Verify if Hermes homes persist on Railway, or if this is operator error (old boxes = stale snapshots). |

**Recommendation:**
- ListLogic SQLite issue needs investigation: does Railway Hermes use ephemeral storage? If yes, document "use Hermes import → backup flow" in runbook.
- If bug is "scaling doesn't preserve Hermes home," that's not OpenBot's bug (it's upstream Hermes deploy). Close as "won't fix, document workaround."

---

## Design Principles (Enforce These in PRs)

1. **Chat dies. Files stay.** — Memory is INDEX + brains + bus, not thread JSON.
2. **Wire engines, don't reimplement.** — If Hermes/OpenCode has it, call the binary. No third agent loop.
3. **Job receipts, not prompts.** — `jobs/` stores metadata. Raw logs are ephemeral or in engine homes.
4. **Tools on demand.** — Cos has no tools. Builder/Research/Ops get tools only when user asks.
5. **Spend caps bind PAYG, not Go.** — OpenCode Go quota runs first. PAYG (OpenRouter) eats the cap.
6. **Approval gates stay.** — Diffs, logins, spends all require human OK. No autonomous publish/pay/delete.
7. **Credit lockup is non-negotiable.** — README + footer + NOTICE always carry the three-line attribution.

---

## Anti-Roadmap (Not in Scope)

These are **explicitly excluded** per OPENBOT.md and AGENTS.md:

- ❌ **Vendoring Hermes/OpenCode source** — call binaries only, never merge upstream code
- ❌ **Multi-tenant SaaS in v1** — Phase 1 is self-hosted, your-instance-only. Phase 2 per OPENBOT.md: others clone the repo and spin **their own** instance (not a shared multi-tenant cloud).
- ❌ **Cloning Grok Bot UI pixel-perfect** — inspired by shape, not a fork
- ❌ **Shared cloud browser / CRD as default** — snapshot + refs, screenshots opt-in
- ❌ **Eternal chat context** — no replaying 200-turn threads into every job
- ❌ **Third agent runtime** — OpenBot is routing + INDEX, not a new CodeAct loop
- ❌ **Claiming affiliation** — no "Powered by Hermes" or "Official OpenCode Board"
- ❌ **Secrets in git/chat/brains** — vault only, never API keys in markdown
- ❌ **CoS on Telegram** — Chief of Staff stays on the board (CEOs have Telegram cohesion)
- ❌ **Chat-as-database** — thread JSON is UI only, not the memory layer

---

## Success Metrics (How We Know We're Winning)

1. **Builder delight:** One-file change → Accept → Brief updates, zero window switching. (**PR #1**)
2. **Chat OS reliability:** 10 Cos + 5 CEO Chat sends, zero empty failures. (**PR #2**)
3. **Sidebar Agent OS:** Named teammates feel present in <3s, busy/unread visible. (**PR #3**)
4. **Operator never rewrites the same INDEX line twice** → memory is durable (ongoing)
5. **Zero wallet-empty hangs** → keyring failover + error cards always surface issues (ongoing)

---

## How to Use This Roadmap

- **Cloud agents:** Implement locked PRs in order: #1 Builder delight, then #2 Chat OS reliability, then #3 Sidebar Agent OS.
- **Human operators:** The CEO + CoS locked this ship order. Deferred items live in "Later Candidates."
- **Contributors:** Follow AGENTS.md + OPENBOT.md. Do NOT implement features from Anti-Roadmap.
- **Cursor session:** Paste this file + "implement PR #1" → agent follows acceptance criteria.

**Note on renames:** CEO/worker rename already ships on master (org tree with Chief of Staff → CEOs → workers). Not a new PR.

Next PR: **#1 Builder Delight Loop** (the Week 2 gate per OPENBOT.md).

---

*OpenBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly). Not affiliated with, sponsored by, or endorsed by those projects.*
