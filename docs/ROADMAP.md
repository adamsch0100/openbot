# OpenBot Roadmap

Product map for OpenBot — the self-hosted control plane routing to Hermes Agent and OpenCode.

See `OPENBOT.md` for the spec and `AGENTS.md` for coding law.

## What Already Works (Shipped on Master)

OpenBot is **shipping at https://openbot-production-9334.up.railway.app** with real operator usage.

The following PRs (#1–#15) are **shipped on master** and form the v1 foundation:

### Core Infrastructure ✓
- **PR #1–#4: Board + Engine + Railway + First-run** — Python stdlib HTTP server, engine detection (hermes/opencode binaries), Railway healthcheck + 0.0.0.0 binding, folder picker, PIN setup, credit lockup display

### Memory & Routing ✓
- **PR #5: INDEX + brains + Org tree** — `brains/INDEX.md` source of truth, 4-line brains (Now/Last/Next/Blocker) per bot, Chief of Staff + CEO projects + named workers (Think/Code/Research/Ops lanes)
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
- **PR #6: Builder delight** — folder → `opencode run` → streaming progress → Diff Accept/Reject → inline INDEX updates
- **PR #7: Chat reliability** — Cos/CEO hang/bleed/silent fail hardening, Muse auto-ack (500f218), CEO chat bleed fix (a9d5f66)
- **PR #8: Sidebar Agent OS** — avatars/initials, Now/Blocker chips from INDEX, busy/unread badges, fast CoS↔CEO switch
- **Diff cards** — Accept/Reject on Builder diffs, git restore on reject
- **Login walls** — vault logins (username/pass per site), auto-fill staging, approval flow
- **PIN unlock** — operator PIN gates the board (cookie-based unlock tokens)
- **Model picker** — seat config (Chat/Think/Code/Research/Ops) with Auto ladder, per-CEO pins
- **Live streaming** — SSE-based `chat/stream` with delta, progress, stop button
- **Activity feed** — job cards, pending approvals (diff/login), Hermes cron ingestion

### Advanced ✓
- **PR #9: Composer attachments** — attach button, drag-drop, paste images; thumbnails in thread; paths in job packets for Hermes/OpenCode
- **PR #10: Connectors UX** — Settings → Connectors panel, Hermes skills + MCP catalog, per-seat toggles, per-CEO overrides
- **PR #11: @seat mentions + handoff cards** — @-mention seats in composer with autocomplete, agent-to-agent handoff cards (from→to, task/status/output)
- **PR #12: Memory pane** — editable Now/Last/Next/Blocker cards, search across INDEX and job RESULT snippets, edit fields + Save to patch INDEX/brains
- **PR #13: Handoff bus protocol** — standardized `bus/handoffs/` file schema (TASK/STATUS/OUTPUT/FROM/TO/NEXT OWNER), agents read open handoffs on job start, Memory pane displays open handoffs with claim button
- **PR #14: Builder validation gate** — pre-Accept validation runs syntax/lint checks (Python `py_compile`, JS `node --check`, optional ruff/eslint), failures block Accept with Force Accept escape hatch
- **PR #15: Routines** — multi-step scheduled flows (ordered steps like morning: Code status → Think summarize → Ops note), Hermes cron integration, resume capability for failed steps, Settings UI
- **MCP toggles** — GitHub MCP on Builder (per-CEO), OAuth credential flow
- **Hermes import** — import Railway Hermes backups, connect remote instances, pull Telegram sessions
- **Skills config** — Hermes skill allowlist (Tools OFF for Cos, on-demand for Think/Research/Ops)
- **Browser snapshots** — fetch-first ladder, snapshot worker, LOGIN_WALL marker, vault staging
- **Git awareness** — status, diff against HEAD, untracked detection, snapshot/restore
- **Multi-lane queueing** — concurrent CEO threads, message queuing during live runs

### Credit & Branding ✓
- **NOTICE + README** — required MIT credit lockup (Hermes Agent, OpenCode)
- **Footer** — three-line attribution, engine links, "LOCAL ORG." on mark
- **BRAND.md compliance** — no rebrand, no affiliation claim, engine name on every job card

---

## Gaps vs World-Class Multi-Agent Chat OS

OpenBot has **Week 1 + foundational v1 ship complete**. PRs #1–#15 shipped the board, Builder delight, Chat reliability, Sidebar Agent OS, Turn report stream, Hermes progress visibility, Keep-going, Composer attachments, Connectors UX, @mentions + handoff cards, Memory pane, Handoff bus protocol, Builder validation, and Routines.

Here's what remains to reach **world-class Chat OS** status:

### 1. True Parallel Multi-Agent
**Current state:**
- ✅ Cos can @mention seats and create handoffs
- ✅ Handoff bus protocol exists (`bus/handoffs/` with TASK/STATUS/OUTPUT)
- ✅ Routines run multi-step flows, but one seat at a time

**What's missing:**
- Cos cannot spawn multiple workers simultaneously (no concurrent task queue)
- Worker pool has no autonomous task queue (agents only work when user sends message)
- No "Builder stuck, auto-route to Research" handoff detection
- Agents don't autonomously pick up `bus/handoffs/` work without manual prompt

**Impact:** Operator must manually sequence multi-agent work. True parallel collaboration (e.g., Code + Research + Think all working at once on different subtasks) is not possible.

### 2. Coding Worker Hardening
**Current state:**
- ✅ Builder validation gate (syntax/lint checks before Accept)
- ✅ Diff Accept/Reject flow with git restore on reject
- ✅ Reliability fixes shipped (Muse auto-ack, CEO chat bleed)

**What's missing:**
- No automatic retry on transient OpenCode failures (network blips, rate limits)
- No rollback if Accept → production breaks (only pre-Accept validation)
- Git snapshot is local only (no branch/PR integration beyond snapshot)
- No "Accept → test → rollback if test fails" path

**Impact:** Transient failures require manual retry. Broken Accepts stay broken until manually reverted.

### 3. Spend Dashboard
**Current state:**
- ✅ Job receipts with prompt/cached/output tokens, USD estimate, wallet label
- ✅ Spend summary (used/cap/remaining) visible on board
- ✅ Spend caps enforce USD cap with period (week/month)

**What's missing:**
- No per-CEO cost breakdown in UI (only global spend summary)
- No week-over-week trend charts or burn alerts
- No "this CEO burned $X this week, 50% of cap" proactive alert

**Impact:** Operator discovers overspend after the fact, no proactive budget warnings.

### 4. Onboarding
**Current state:**
- ✅ Folder picker, engine detect, PIN setup, first-run flag
- ✅ First prompt: "What is this project and what is blocked?"

**What's missing:**
- No sample/test job after first-run (e.g., "try a one-file change" tutorial)
- No Hermes auth check (`hermes portal status` or session check) before first Think/Research/Ops
- No OpenCode auth check (`opencode auth status`) before first Builder run
- No engine version check (Hermes 0.x vs 1.x breaking changes)

**Impact:** New users may hit "not authenticated" errors on first real job instead of at setup time.

### 5. Observability
**Current state:**
- ✅ Live streaming progress for OpenCode (step-start events → UI progress chips)
- ✅ Activity feed with job cards, timestamps, engine/model used

**What's missing:**
- No live Hermes session log tail (can only see "Hermes running…" or final output)
- No "replay this job with --verbose" debug mode
- Job receipts don't link to raw Hermes/OpenCode session logs
- No way to see Hermes tool calls mid-job (only after completion)

**Impact:** Debugging "why did Research fail?" requires opening raw Hermes dashboard or CLI.

### 6. Polish Pack
**Current state:**
- ✅ Skills catalog in Settings → Connectors with per-seat toggles
- ✅ Routine templates (Settings → Routines with create form)
- ✅ Memory pane with search across INDEX and job RESULT snippets
- ✅ `data-job-id` on job bubbles for stream jump

**What's missing:**
- Skills catalog UX is functional but not polished (no skill descriptions, no "popular skills" section)
- Routine templates are blank-slate create form (no "morning standup" or "weekly review" presets)
- Memory search → stream jump needs consistent `data-job-id` on all job bubbles (some missing)

**Impact:** Onboarding friction. Users must discover skills and routine patterns manually.

### 7. Self-Build Loop
**Current state:**
- ✅ Builder can open PRs (manual operator flow)
- ✅ OpenCode sessions work in OpenBot repo folder

**What's missing:**
- OpenBot doesn't use OpenCode Go seats to open its own PRs (operator manually drives Builder)
- No "weekly: OpenBot Builder opens a PR for next ROADMAP item" routine

**Impact:** Dogfooding is manual. OpenBot doesn't autonomously improve itself.

### 8. E2E World-Class Audit
**Current state:**
- ✅ OpenBot runs on Railway front+back
- ✅ PRs #1–#15 shipped and tested by operator

**What's missing:**
- No Cloud Agent E2E test run against live Railway OpenBot
- No Cos sign-off that "this is world-class" before operator handoff
- No automated regression suite (weekly: spin up OpenBot, run Builder/Research/Ops test jobs)

**Impact:** World-class claim is operator-verified, not agent-verified. Risk of regressions on new PRs.

---

## Next PRs (Locked Ship Order)

These are the **serial next 8 PRs** locked by the operator. Each scoped for focused implementation. Ship in this order.

---

### **WC-1: True Parallel Multi-Agent** ⭐

**Why:**
OpenBot has handoffs, routines, and @mentions but no autonomous task queue. Cos cannot spawn multiple workers to run simultaneously. Operators must manually sequence work that should run in parallel (e.g., Code diff + Research doc fetch + Think summarize all at once). This is the core Chat OS gap.

**Acceptance criteria:**
1. Cos can spawn multiple CEO workers simultaneously (e.g., "Builder: add logging; Research: fetch API docs" in one message)
2. Worker pool has autonomous task queue: agents check `bus/handoffs/` on idle and claim open work
3. Handoff detection: when Builder job emits "need docs", auto-route handoff to Research without operator prompt
4. Concurrent execution: 3+ workers running at once, each with live progress visible in sidebar
5. Queue visibility: sidebar shows queued tasks per CEO (e.g., "2 tasks queued for Nadia")
6. Comprehensive tests: spawn 3 workers, verify all run concurrently, verify handoff auto-routing
7. ROADMAP + INDEX updated

**Out of scope:**
- Dependency graphs (sequential task chains)
- Multi-seat fan-out from one handoff (one handoff → one seat for v1)
- Full Kanban UX over `bus/` (visual cards, drag-drop)

**Estimated complexity:**
High. Requires task queue implementation in board, concurrent worker management, handoff auto-routing logic, sidebar queue rendering. Touches router, board, sidebar UI, handoff bus integration. Core architectural change.

---

### **WC-2: Coding Worker Hardening** ⭐

**Why:**
Builder has validation gate but no retry on transient failures (network blips, OpenCode rate limits). No rollback if Accept → production breaks. Git integration stops at local snapshot. Operators manually retry failed jobs and manually revert broken Accepts.

**Acceptance criteria:**
1. Automatic retry on transient OpenCode failures: 3 retries with exponential backoff (2s, 4s, 8s) on network errors or rate limits
2. Accept → rollback path: if operator clicks "Revert Accept" on activity card, git restores the snapshot and removes job from activity
3. Branch/PR integration: Builder can optionally push to branch and open PR (not just local snapshot)
4. Test-after-accept flow: if repo has `npm test` or `pytest`, optionally run tests after Accept and offer rollback if tests fail
5. Comprehensive tests: mock transient OpenCode failure, verify retry; Accept → Revert → verify git restore; branch push + PR creation
6. ROADMAP + INDEX updated

**Out of scope:**
- Full CI/CD integration (webhook listeners, GitHub Actions triggers)
- Automatic rollback without operator approval
- Multi-commit rollback (only last Accept snapshot for v1)

**Estimated complexity:**
Medium-High. Requires retry logic in OpenCode runner, rollback flow in diff handler, branch/PR integration in Builder preset. Touches router, builder.py, git.py, activity feed UI.

---

### **WC-3: Spend Dashboard** ⭐

**Why:**
Spend caps work but operators only see global spend summary. No per-CEO burn breakdown, no proactive alerts when 50% of weekly cap is hit. Operators discover overspend after the cap blocks a job.

**Acceptance criteria:**
1. Per-CEO cost breakdown in UI: Settings → Spend shows each CEO's weekly/monthly burn
2. Week-over-week trend: line chart of daily burn for last 2 weeks
3. Proactive alerts: when CEO hits 50% of weekly cap, show alert in sidebar (yellow badge) and activity feed
4. Cap-exceeded notice: when cap blocks a job, show "Nadia hit $X cap, resets in 3 days" in activity
5. Comprehensive tests: simulate 10 jobs across 3 CEOs, verify per-CEO totals, verify 50% alert triggers
6. ROADMAP + INDEX updated

**Out of scope:**
- Spend forecasting ("at this rate, cap in 2 days")
- Per-seat spend breakdown (only per-CEO for v1)
- Spend export (CSV download of receipts)

**Estimated complexity:**
Medium. Requires spend aggregation by CEO, weekly/monthly rollup logic, alert triggers, chart rendering. Touches spend.py, settings UI, sidebar badges, activity feed.

---

### **WC-4: Onboarding** ⭐

**Why:**
First-run setup works but doesn't verify engine auth before first real job. New users hit "OpenCode not authenticated" or "Hermes portal missing" errors on first Builder/Think job instead of at setup time. No sample job to verify board works.

**Acceptance criteria:**
1. After first-run folder picker + PIN setup, offer "Run test job" button (e.g., "Create a hello.txt file with Builder")
2. Test job runs Builder, creates file, shows diff card, operator Accepts, INDEX updates
3. Before test job: check Hermes auth (`hermes portal status` or session check), show "Hermes not authenticated" card if missing
4. Before test job: check OpenCode auth (`opencode auth status`), show "OpenCode not authenticated" card if missing
5. Auth check cards have "Authenticate now" button (opens `hermes portal` or `opencode auth login` instructions)
6. Comprehensive tests: mock unauthenticated engines, verify auth check cards appear; mock authenticated engines, verify test job runs
7. ROADMAP + INDEX updated

**Out of scope:**
- Full tutorial flow (multi-step wizard)
- Sample project template (repo scaffolding)
- Engine version compatibility checks (Hermes 0.x vs 1.x)

**Estimated complexity:**
Low-Medium. Requires auth check calls to Hermes/OpenCode, test job definition, auth card rendering, first-run flow extension. Touches server.py (first-run), hermes.py, builder.py, web UI (auth cards).

---

### **WC-5: Observability** ⭐

**Why:**
Live streaming works for OpenCode (step-start events → UI chips) but not for Hermes. No "replay job verbose" mode. Debugging "why did Research fail?" requires opening raw Hermes dashboard. Job receipts don't link to raw logs.

**Acceptance criteria:**
1. Hermes session log tail: during Think/Research/Ops jobs, stream Hermes tool calls to UI (e.g., "fetch: example.com", "snapshot: 3 links parsed")
2. Replay verbose mode: activity feed job cards have "Replay verbose" button; opens modal with full Hermes/OpenCode session log
3. Job receipts link to raw logs: each job card in activity feed has "View raw log" link (opens `jobs/{id}.log` in new tab or modal)
4. Hermes progress chips: Hermes tool calls render as progress chips in stream (like OpenCode step-start events)
5. Comprehensive tests: mock Hermes session with tool calls, verify progress chips appear; verify replay verbose retrieves full log
6. ROADMAP + INDEX updated

**Out of scope:**
- Real-time log tail from Hermes homes (only session-start to session-end for v1)
- Log search/filtering (only full log display)
- Distributed tracing (correlation IDs across Hermes/OpenCode)

**Estimated complexity:**
Medium-High. Requires Hermes session log parsing, streaming tool calls to UI, replay modal, job log storage. Touches hermes.py, router.py (stream events), activity feed UI, replay modal.

---

### **WC-6: Polish Pack** ⭐

**Why:**
Skills catalog, routine templates, and Memory search → stream jump are functional but not polished. Onboarding friction: users must discover skills manually, routine patterns are blank-slate, Memory search jump requires consistent `data-job-id`.

**Acceptance criteria:**
1. Skills catalog polish: Settings → Connectors shows skill descriptions (one-liner per skill), "Popular skills" section with recommended skills for Think/Research/Ops
2. Routine templates: Settings → Routines has "Create from template" dropdown with presets ("Morning standup: Code status → Think summarize", "Weekly review: Think list last week → Research fetch changelog → Ops note")
3. Memory search → stream jump: ensure ALL job bubbles have `data-job-id` attribute (audit + fix missing ones), Memory search results link directly to job bubble in stream
4. Routine preset loads template steps into create form (user can edit before saving)
5. Comprehensive tests: verify skill descriptions render, verify template presets load, verify Memory search jump links to correct job bubble
6. ROADMAP + INDEX updated

**Out of scope:**
- Custom skill creation (only toggle existing Hermes skills)
- Routine editor (visual step builder, drag-drop reorder)
- Memory semantic search (only keyword search for v1)

**Estimated complexity:**
Low-Medium. Requires skill descriptions data, routine template definitions, `data-job-id` audit, template UI. Touches connectors UI, routines UI, memory pane, job bubble rendering.

---

### **WC-7: Self-Build Loop** ⭐

**Why:**
OpenBot doesn't dogfood itself. Operator manually drives Builder to open PRs. No "weekly: OpenBot Builder opens a PR for next ROADMAP item" routine. Missing self-improvement automation.

**Acceptance criteria:**
1. Self-build routine: create routine "Weekly self-build" with steps ("Builder: implement next ROADMAP PR", "Think: review diff for correctness", "Ops: open PR with summary")
2. Routine uses cheap OpenCode Go seats (not PAYG) for self-build jobs
3. Self-build PR template: PR title "OpenBot self-build: [ROADMAP item]", body includes ROADMAP acceptance criteria checklist
4. Self-build flag: Settings → Advanced has "Enable self-build loop" toggle (off by default)
5. Comprehensive tests: enable self-build, trigger routine, verify Builder job runs in openbot folder, verify PR opens against openbot repo
6. ROADMAP + INDEX updated

**Out of scope:**
- Auto-merge self-build PRs (operator reviews and merges manually)
- Self-build approval gate (operator can disable routine)
- Multi-PR self-build (only one PR per routine run)

**Estimated complexity:**
Low-Medium. Requires self-build routine definition, PR template, OpenCode seat enforcement, self-build toggle. Touches routines.py, router.py (seat enforcement), settings UI.

---

### **WC-8: E2E World-Class Audit** ⭐

**Why:**
World-class claim is operator-verified, not agent-verified. No Cloud Agent E2E test run against live Railway OpenBot. No automated regression suite. Risk of regressions on new PRs.

**Acceptance criteria:**
1. Cloud Agent E2E test: spawn Cloud Agent, point at live Railway OpenBot (https://openbot-production-9334.up.railway.app), run test suite (Builder: create file + Accept, Research: fetch doc, Ops: create cron)
2. Test suite passes: Builder diff accepted, Research doc fetched, Ops cron created
3. Cos world-class sign-off: after E2E test passes, Cos writes "World-class audit complete: [date]" to `brains/INDEX.md` or `org/projects/openbot/AUDIT.md`
4. Regression suite: automated weekly routine runs E2E test against Railway, posts result to activity feed
5. Comprehensive tests: E2E test script with assertions, regression routine definition
6. ROADMAP + INDEX updated

**Out of scope:**
- Full integration test suite (only smoke tests for v1)
- Performance benchmarks (latency, throughput)
- Load testing (concurrent users, stress tests)

**Estimated complexity:**
Medium. Requires E2E test script (Cursor Cloud Agent or external script), test assertions, regression routine. Touches routines.py, test suite (new `tests/e2e/`), Cos brief integration.

---

## Deferred / Later Candidates

These are **lower-priority** or **post-MVP** features. Ship WC-1 through WC-8 first, then revisit.

### Kanban UX Over INDEX
Visual cards for Now/Next/Blocker instead of markdown editing. Improves memory UX but not urgent. Current Memory pane with edit fields + Save works.

### Multi-Seat Fan-Out
One handoff → multiple seats (e.g., "Research + Think both summarize this doc"). Useful but complex. WC-1 ships single-seat handoffs first.

### Full CI/CD Integration
Webhook listeners for GitHub Actions, auto-rollback on test failures. Valuable but WC-2 ships manual rollback path first.

### Spend Forecasting
"At this rate, cap in 2 days" alerts. Nice-to-have; WC-3 ships per-CEO burn breakdown and 50% alerts first.

### Engine Version Compatibility Checks
Hermes 0.x vs 1.x breaking change detection. Helpful but not critical; WC-4 ships auth checks first.

### Distributed Tracing
Correlation IDs across Hermes/OpenCode for cross-engine debugging. Powerful but complex; WC-5 ships log tail and replay verbose first.

### Custom Skill Creation
User-defined Hermes skills. Advanced feature; WC-6 ships skill catalog polish first.

### Auto-Merge Self-Build PRs
OpenBot auto-merges its own PRs after tests pass. Risky; WC-7 ships operator-reviewed self-build first.

### Performance Benchmarks
Latency, throughput, load testing. Important for scale but not for world-class v1; WC-8 ships smoke tests first.

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
- ❌ **Multi-tenant SaaS in v1** — Phase 1 is self-hosted, your-instance-only
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

1. **True parallel multi-agent:** Cos spawns 3 workers simultaneously, all make progress concurrently. (**WC-1**)
2. **Coding worker hardening:** Builder retries transient failures, Accept → rollback path works. (**WC-2**)
3. **Spend dashboard:** Per-CEO burn visible, 50% cap alert triggers proactively. (**WC-3**)
4. **Onboarding:** First-run auth checks pass, sample job Accepts on first try. (**WC-4**)
5. **Observability:** Hermes tool calls stream live, replay verbose shows full log. (**WC-5**)
6. **Polish pack:** Skills catalog has descriptions, routine templates load presets. (**WC-6**)
7. **Self-build loop:** OpenBot opens its own PR for next ROADMAP item. (**WC-7**)
8. **E2E world-class audit:** Cloud Agent E2E test passes, Cos signs world-class. (**WC-8**)

---

## How to Use This Roadmap

- **Cloud agents:** Implement locked PRs in order: WC-1 through WC-8.
- **Human operators:** The CEO + CoS locked this ship order. Deferred items live in "Later Candidates."
- **Contributors:** Follow AGENTS.md + OPENBOT.md. Do NOT implement features from Anti-Roadmap.
- **Cursor session:** Paste this file + "implement WC-1" → agent follows acceptance criteria.

---

Next: WC-1 True parallel multi-agent

---

*OpenBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly). Not affiliated with, sponsored by, or endorsed by those projects.*
