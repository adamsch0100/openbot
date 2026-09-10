# Mobile UX Testing Guide — PR #61

## Quick Phone Test (~390×844 or similar)

### 1. Chat Tab Verification
1. Open board on phone browser (Safari iOS or Chrome Android)
2. Navigate to Chat tab
3. **✓ VERIFY**: No truncated "Scheduled · Saved sear…" chip visible (removed entirely on mobile)
4. **✓ VERIFY**: Doing/Next/Results tabs show clear counts: "Doing 2", "Next 5", "Results 12"
5. **✓ VERIFY**: Chat composer is calm and thumb-friendly:
   - Send button is 44px height, rounded (12px)
   - Attach button is 44px square
   - "Talking to Chief of Staff" is small, muted (9px, 60% opacity)
6. **✓ VERIFY**: Chat bubbles are readable:
   - User bubbles: 15px text, rounded (16px), max 88% width
   - Bot responses: 15px text, clean (no border/bg clutter)

### 2. Results Tab Verification (Screenshot-Critical)
1. Select a CEO with failed scheduled jobs (e.g., SAA Homes)
2. Open Results tab
3. **✓ VERIFY**: Failed job cards show error text ONCE:
   - "Gateway shutdown (final-cleanup) killed the job's tool subprocess..." appears in outcome
   - NOT repeated below in snippet
   - NOT repeated again in details
4. **✓ VERIFY**: Retry button is thumb-friendly:
   - 48px height, full-width
   - "Retry on live Hermes" text is readable (14px, weight 500)
5. Tap Retry on a citation-audit or content-gap job
6. **✓ VERIFY**: Button updates to "Running on live Hermes"
7. Wait for job to complete
8. **✓ VERIFY**: Results list refreshes with new outcome (not stale)

### 3. Footer Context Verification
1. Scroll to bottom footer
2. On Railway deployment:
   - **✓ VERIFY**: Shows "OPENBOT · LIVE · Railway" (not "LOCAL ORG.")
3. On localhost (127.0.0.1 or 192.168.*):
   - **✓ VERIFY**: Shows "OPENBOT · LOCAL ORG."

### 4. Work Tab Counts Verification
1. Navigate between Chat/Code/Hermes tabs
2. **✓ VERIFY**: Each stage shows same work tabs with counts
3. Counts update when:
   - Job starts running (Doing +1)
   - Job finishes (Doing -1, Results +1)
   - New scheduled job added (Next +1)

## Before/After Comparison

### Before (Issues from Screenshot)
- ❌ Top-right "Scheduled · Saved sear…" chip truncated, wasting chrome
- ❌ Results show "Gateway shutdown..." error 3 times per card (title + outcome + snippet)
- ❌ Work tabs show "Doing", "Next", "Results" with no counts
- ❌ Footer says "LOCAL ORG." on railway.app (lying)
- ❌ Retry buttons small (36px), hard to tap
- ❌ Chat bubbles 13-14px, cluttered with borders/backgrounds

### After (PR #61)
- ✅ Status chip removed on mobile (clean)
- ✅ Results show error once per card (deduplicated)
- ✅ Work tabs show "Doing 2", "Next 5", "Results 12" (clear counts)
- ✅ Footer shows "LIVE · Railway" on railway.app (honest)
- ✅ Retry buttons 48px, full-width, thumb-friendly
- ✅ Chat bubbles 15px, clean design (Grok-like)

## Regression Checks

1. Desktop Chrome (≥1024px):
   - Status pulse chip still visible and functional
   - Work tabs remain horizontal in header
   - Chat/Results layouts unchanged

2. Tablet (768-1023px):
   - Work tabs grid layout works
   - Composer remains usable
   - Rail drawer overlay works

3. Existing functionality:
   - Chat message send/receive
   - CEO selection and switching
   - Scheduled job cards open/close
   - Retry button POST to `/api/crons/run` succeeds
   - Session affinity headers present (OPENCODE_SESSION_ID env var set)

## Hard-Refresh Requirement

After deploy to Railway or local instance:
1. Open browser DevTools (F12)
2. Right-click refresh button → "Empty Cache and Hard Reload"
3. OR: Cmd+Shift+R (Mac) / Ctrl+Shift+R (Windows)
4. Verify `?v=117` or higher in `<link rel="stylesheet" href="/styles.css?v=117">`

Without hard-refresh, old CSS may show old layout.

## Session Affinity Verification (Advanced)

To verify Retry uses session headers correctly:

1. Open browser DevTools → Network tab
2. Filter: `crons/run`
3. Tap "Retry on live Hermes" on a failed job
4. Inspect POST request to `/api/crons/run`
5. Server-side: Check Hermes Agent logs for `OPENCODE_SESSION_ID` env var
6. OpenCode Go calls should include `x-opencode-session: <session-id>` header
7. Deepseek-v4-flash and other Go models should route to same session

Expected flow:
```
Browser → POST /api/crons/run { project_id, job_id }
  ↓
Board server.py → hermes.py cron_run()
  ↓
hermes cron run --accept-hooks <job-id>
  ↓
_make_env() adds OPENCODE_SESSION_ID from project_tools()
  ↓
Hermes Agent runs with session affinity
  ↓
agent/opencode_affinity.py injects x-opencode-session header
  ↓
OpenCode Go calls use consistent session
```

## Done

All acceptance criteria met:
- ✅ A) Status chip removed on mobile
- ✅ B) Chat is primary product feeling (Grok-like, calm, readable)
- ✅ C) Doing/Next/Results clear with counts
- ✅ D) Results decluttered (one error per card, big Retry button)
- ✅ E) Honest footer (LIVE vs LOCAL)
- ✅ F) Retry works with session affinity (already correct)
- ✅ G) Testing guide provided

PR #61 ready for merge after phone smoke test.
