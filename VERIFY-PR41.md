# PR #41 Verification Guide

## What was fixed

PR #40 failed because the parser expected single-row table format. The REAL Hermes cron format is multi-line blocks:

```
  7cb2a72c1cc8 [active]
    Name:      form-pipeline-health
    Schedule:  0 14 * * *
    Deliver:   origin
```

## Changes

1. **Parser rewrite**: Parse multi-line blocks with indented fields
2. **Job ID validation**: Require 12+ hex chars, reject label words (Name:, Schedule:, Next, Execution:)
3. **Gateway fixes**: Never 502, hard timeout returns running=false + error
4. **Migration filter**: Only migrate deliver=origin jobs

## Live verification on SAA Homes

### 1. Check /api/routines shows real Hermes jobs

```bash
curl http://127.0.0.1:8787/api/routines?project_id=saa-homes
```

**Expected:**
- `hermes_count` > 0 (not 0 like before)
- `hermes_crons` array contains real jobs:
  - `form-pipeline-health`
  - `daily-ranking-strike`
- **No junk IDs**: Name:, Schedule:, Next, Execution:, Skills:

### 2. Gateway status never 502

```bash
# Start gateway
curl -X POST http://127.0.0.1:8787/api/hermes/gateway/start \
  -H "Content-Type: application/json" \
  -d '{"project_id": "saa-homes"}'

# Check status (should show running: true)
curl http://127.0.0.1:8787/api/hermes/gateway/status?project_id=saa-homes
```

**Expected:**
- Start returns `running: true` or `started: true`
- Status returns `running: true` if gateway is up
- Status NEVER returns 502, even on timeout (returns 200 with error field)

### 3. Migrate dry run shows only real job IDs

```bash
curl -X POST http://127.0.0.1:8787/api/hermes/crons/migrate-delivery \
  -H "Content-Type: application/json" \
  -d '{"project_id": "saa-homes", "dry_run": true}'
```

**Expected:**
- `migrated` array contains hex IDs like `7cb2a72c1cc8`, `240631fc9f22`
- **No junk**: Name:, Schedule:, Next, Execution:, Skills:
- Jobs with `deliver: local` are skipped

## What to look for (FAIL signs)

❌ `hermes_count: 0` when SAA Homes has crons
❌ Job IDs like "Name:", "Next", "Execution:" in results
❌ Gateway status returns 502
❌ Migrate dry_run returns label words as IDs

## Success criteria

✅ `/api/routines` shows real job names (form-pipeline-health, daily-ranking-strike)
✅ `hermes_count` matches actual cron count
✅ All job IDs are hex-like (12+ chars)
✅ Gateway status always 200 (even on error)
✅ Migrate only targets deliver=origin jobs
✅ All 19 tests pass

## If verification passes

Ready to undraft and merge. HOLD real migrate until CEO live re-verify per user request.
