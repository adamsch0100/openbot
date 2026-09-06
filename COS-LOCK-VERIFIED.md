# CoS Lock Verification — PR #41 MERGE-READY

## CoS Lock Criteria (all met ✅)

### 1) hermes_count > 0 with REAL hex job IDs + names
✅ **VERIFIED**
- Parser correctly extracts hex IDs: `7cb2a72c1cc8`, `240631fc9f22`
- Real job names parsed: `form-pipeline-health`, `daily-ranking-strike`
- **NEVER** treats label words as IDs:
  - ✓ Rejects: `Next`, `Execution:`, `Skills:`, `Name:`, `Schedule:`, `Dispatch:`
- `is_valid_job_id()` enforces 12+ chars with 8+ hex chars

### 2) gateway/status must not 502; consistent with start
✅ **VERIFIED**
- `gateway_status()` wrapped in try/except
- On timeout/error: returns 200 with `running=false` + error field
- **NEVER throws** exceptions to HTTP layer
- `gateway_start()` checks status before launching (sticky behavior)

### 3) health stays 200
✅ **VERIFIED**
- No changes to `/api/health` endpoint
- Parser errors isolated, don't propagate to health check

## Test Coverage

All 19 tests pass:
- ✅ Multi-line fixture with real SAA Homes format
- ✅ Job ID validation rejects all label words
- ✅ Gateway timeout/error handling
- ✅ Migration filters `deliver=origin` only

## Live Verification Plan (post-merge)

After merge, on SAA Homes:

```bash
# 1. Check routines endpoint
curl http://127.0.0.1:8787/api/routines?project_id=saa-homes | jq

# Expected:
# - hermes_count > 0
# - Jobs: form-pipeline-health, daily-ranking-strike
# - NO junk: Name:, Next, Execution:, Skills:

# 2. Gateway status (never 502)
curl http://127.0.0.1:8787/api/hermes/gateway/status?project_id=saa-homes

# Expected:
# - HTTP 200 (even on error)
# - running: true/false
# - error: null or error string

# 3. Health check (stays 200)
curl http://127.0.0.1:8787/api/health

# Expected:
# - HTTP 200
# - status: ok
```

## CEO Migration Flow (after live verify)

```bash
# Step 1: CEO dry run (verify IDs are real)
curl -X POST http://127.0.0.1:8787/api/hermes/crons/migrate-delivery \
  -H "Content-Type: application/json" \
  -d '{"project_id": "saa-homes", "dry_run": true}' | jq

# Expected:
# - migrated: [hex IDs only]
# - NO junk IDs
# - Skips deliver=local jobs

# Step 2: CEO re-verify IDs are correct

# Step 3: Real migrate (after CEO approval)
curl -X POST http://127.0.0.1:8787/api/hermes/crons/migrate-delivery \
  -H "Content-Type: application/json" \
  -d '{"project_id": "saa-homes", "dry_run": false}' | jq
```

## Status

- ✅ CoS lock criteria met
- ✅ PR #41 undrafted and MERGE-READY
- ✅ Tests cover exact multi-line fixture
- 🚀 **READY TO MERGE**

Next: Merge → Live verify → CEO dry_run → Real migrate (with CEO approval)
