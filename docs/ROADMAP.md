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

## Next 5 Shippable PRs (Ranked by User-Felt Impact)

Each PR is scoped for **one cloud agent turn** with concrete acceptance criteria.

---

### **PR #1: Handoff Bus Protocol (Async Agent → Agent Work)**
**Problem:**
CEOs and workers don't hand off work to each other. User must manually ping Builder, then Research, then Builder again.

**User value:**
"Ask Builder to add auth" → Builder writes `bus/need-docs-auth.md` → Research auto-picks it up → writes `bus/handoff-auth-research.md` → Builder resumes without user sending 3 messages.

**Acceptance criteria:**
1. Standardized handoff schema:
   ```markdown
   TASK: What I need
   STATUS: blocked | waiting | done
   OUTPUT: What I produced (file paths, summary)
   NEXT OWNER: research | builder | cos
   ```
2. `bus/` polling on job finish: if `NEXT OWNER` matches my preset, read the handoff and run.
3. Router recognizes "need docs for X" → writes handoff instead of chat reply.
4. UI shows active handoffs in Activity feed (e.g., "Builder → Research: need API docs").

**Files/areas touched:**
- `openbot/bus.py` — add `parse_handoff()`, `write_handoff()`, `pending_handoffs()`
- `openbot/router.py` — check `bus/` at job finish, trigger next agent if handoff exists
- `web/app.js` — render handoff cards in activity stream
- `brains/INDEX.md` — update contract: "End jobs with a HANDOFF file if another agent should continue."

**Estimated complexity:** Medium (new file protocol + router logic, no new engine calls).

---

### **PR #2: Builder Validation Gate (Syntax/Lint/Test Check)**
**Problem:**
Builder diffs may have syntax errors, linting failures, or broken tests. Operator only finds out after Accept when they try to run the code.

**User value:**
Accept button is disabled until `npm run lint && npm test` passes (or Python equiv). No more "Builder broke the build."

**Acceptance criteria:**
1. After OpenCode finishes, detect project type (package.json → Node, pyproject.toml → Python, etc.).
2. Run validation command in snapshot before showing diff card:
   - Node: `npm run lint && npm test` (if scripts exist)
   - Python: `ruff check . && pytest` (if tools installed)
   - Skip if no validation tools found.
3. Validation failure → show error on diff card, block Accept, offer "Reject and ask Builder to fix."
4. Validation pass → Accept enabled as normal.

**Files/areas touched:**
- `openbot/gitutil.py` — add `validate_project(folder, snapshot)` (detect type, run checks)
- `openbot/router.py` — call `validate_project()` after Builder finishes, store result in job receipt
- `openbot/server.py` — diff card API includes `validation_status` (passed/failed/skipped)
- `web/app.js` — render validation errors on diff card, disable Accept button if failed

**Estimated complexity:** Medium-High (project type detection + subprocess validation, error parsing).

---

### **PR #3: Spend Dashboard (Per-CEO Cost Breakdown)**
**Problem:**
User sees total spend but not "which CEO burned money." No trend chart. No proactive alert when nearing cap.

**User value:**
Open "Usage" panel → see spend by CEO (table + chart), last 7 days trend, per-lane breakdown (Chat $0.12, Code $3.45, Think $1.20).

**Acceptance criteria:**
1. New `GET /api/spend/breakdown` endpoint:
   - Input: `?period=week` (or month)
   - Output: `{ projects: [{ id, name, spend_usd, by_preset: { chat, code, think, research, ops } }], timeline: [{ date, spend_usd }] }`
2. Parse all job receipts in period, group by `project_id` + `preset`, sum `usd_estimate`.
3. Usage panel renders:
   - Per-CEO table (name, spend, % of cap)
   - 7-day line chart (date vs spend)
   - Per-lane pie chart (optional, nice-to-have)
4. Alert chip on board if spend > 80% of cap: "Usage: $47.60 / $50.00 (95%) — consider raising cap or pausing CEOs."

**Files/areas touched:**
- `openbot/store.py` — add `spend_breakdown(period, start_date=None)` (read jobs, group, sum)
- `openbot/server.py` — `GET /api/spend/breakdown`
- `web/app.js` — fetch breakdown on Usage panel open, render table + chart (use simple canvas or SVG)
- `web/index.html` + `web/styles.css` — layout for breakdown table + chart

**Estimated complexity:** Medium (aggregation logic + chart rendering, no new agent calls).

---

### **PR #4: Onboarding Tutorial (Post-Setup Test Job)**
**Problem:**
After first run, user sees blank board. No guidance on "what do I do now?" No confidence engines actually work.

**User value:**
First-run wizard finishes → board auto-runs a test job (Cos reads INDEX, Builder makes trivial change if folder is a repo) → user sees job card + diff card immediately.

**Acceptance criteria:**
1. After first-run (folder + PIN set), if `engines.opencode.present && work_dir is a git repo`:
   - Auto-queue Builder job: "Add a comment to README.md that says 'OpenBot test job {timestamp}.'"
   - Show job card with "Test job running…" in stream.
2. If OpenCode missing, queue Cos job: "What is blocked right now?" → show staff briefing reply.
3. Test job runs in background (same as normal job), result shows in Activity + Stream.
4. Optional: "This was a test. Try asking for a real change." hint after test job finishes.

**Files/areas touched:**
- `openbot/config.py` — add `first_run_test_done` flag to config
- `openbot/server.py` — after `POST /api/config` sets `work_dir`, check `first_run_test_done`; if false, enqueue test job
- `openbot/router.py` — handle test job as normal (no special logic needed)
- `web/app.js` — render "Running your first test job…" in stream header if `setup_just_done` flag

**Estimated complexity:** Low (reuse existing job flow, just auto-trigger once).

---

### **PR #5: Routine Scheduler (Multi-Step Daily Flows)**
**Problem:**
Ops cron is one-shot Hermes jobs. No "every morning: check new GitHub issues → summarize → post to Telegram" flow.

**User value:**
Settings → Routines → "Daily Standup: every weekday 9am, run Builder (git status) → Think (summarize) → Ops (post to Telegram)."

**Acceptance criteria:**
1. New `routines.json` config (or in org profile per CEO):
   ```json
   [
     {
       "id": "daily-standup",
       "schedule": "0 9 * * 1-5",
       "steps": [
         { "preset": "builder", "prompt": "git status summary" },
         { "preset": "think", "prompt": "Summarize last 24h changes" },
         { "preset": "ops", "prompt": "Post summary to Telegram" }
       ],
       "enabled": true
     }
   ]
   ```
2. On Hermes cron trigger (or board-side scheduler if Hermes not available):
   - Fetch routine config, execute steps in order, carry `PRIOR RESULT` to next step.
3. Routine log shows full chain result in Activity feed.
4. UI: Settings → Routines panel → Add/Edit/Disable routines (form: name, cron, steps list).

**Files/areas touched:**
- `openbot/org.py` — store routines in org profile or per-CEO tools
- `openbot/cronwatch.py` — hook routine execution (or new `openbot/routines.py` module)
- `openbot/router.py` — `handle_routine(routine_id)` → run step chain, same as `handle()` but looped
- `openbot/server.py` — `GET /api/routines`, `POST /api/routines`, `PUT /api/routines/:id`, `DELETE /api/routines/:id`
- `web/app.js` + `web/index.html` — Routines panel UI (list, add form, cron input, steps builder)

**Estimated complexity:** High (new scheduler abstraction, multi-step chain logic, UI for step builder).

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
- ❌ **Multi-tenant SaaS** — v1 is self-hosted, your-instance-only
- ❌ **Cloning Grok Bot UI pixel-perfect** — inspired by shape, not a fork
- ❌ **Shared cloud browser as default** — snapshot + refs, screenshots opt-in
- ❌ **Eternal chat context** — no replaying 200-turn threads into every job
- ❌ **Third agent runtime** — OpenBot is routing + INDEX, not a new CodeAct loop
- ❌ **Claiming affiliation** — no "Powered by Hermes" or "Official OpenCode Board"
- ❌ **Secrets in git/chat/brains** — vault only, never API keys in markdown

---

## Success Metrics (How We Know We're Winning)

1. **Operator never rewrites the same INDEX line twice** → memory is durable
2. **Builder → Research → Builder chain runs without 3 user messages** → async handoffs work
3. **Zero "Accept → build breaks" incidents in a week** → validation gate works
4. **User sees spend breakdown on day 1** → transparency wins trust
5. **First-run wizard → test job → user says "that was easy"** → onboarding smooth
6. **Daily standup runs unattended for a week** → routines are reliable

---

## How to Use This Roadmap

- **Cloud agents:** Pick a PR, read acceptance criteria, implement in one turn.
- **Human operators:** Vote on PRs by impact to your workflow. Reorder if needed.
- **Contributors:** Follow AGENTS.md + OPENBOT.md. Do NOT implement features from Anti-Roadmap.
- **Cursor session:** Paste this file + "implement PR #2" → agent follows acceptance criteria.

Next PR: **#1 Handoff Bus Protocol** (highest leverage for multi-agent collaboration).

---

*OpenBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly). Not affiliated with, sponsored by, or endorsed by those projects.*
