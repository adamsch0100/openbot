# Verification Steps for PR #40

## What Was Fixed

### 1. ✅ Hermes cron parsing (DONE)
**Problem**: `hermes cron list` output was parsed incorrectly, extracting table chrome (`│`, `Schedule:`, `Last`, `Dispatch:`) as job IDs instead of real jobs.

**Solution**:
- `cron_list()` now tries `hermes cron list --json` first (if supported)
- Falls back to robust table parsing that:
  - Strips box-drawing characters before parsing
  - Skips header lines correctly (only if first word exactly matches `ID`, `JOB`, etc.)
  - Filters out junk IDs using validation logic
- New `is_valid_job_id(job_id)` guard function rejects table chrome

**Tests**: 9 comprehensive tests in `tests/test_hermes_cron_parsing.py` — all pass

**Verify**:
```python
from openbot.hermes import cron_list, is_valid_job_id

# This should return structured job list with "jobs" key
result = cron_list(home="path/to/saa-homes-hermes")
print(f"Found {len(result.get('jobs', []))} jobs")
for job in result["jobs"]:
    print(f"  {job['id']} - {job['name']} - {job['schedule']}")

# Guard example
job_id = "daily-ranking-strike"
if is_valid_job_id(job_id):
    print(f"✅ {job_id} is valid")
else:
    print(f"❌ {job_id} is table chrome, skip it")
```

Expected: Real SAA Homes job names like `daily-ranking-strike`, not `│` or `Schedule:`

---

### 2. ⚠️ Gateway start status (NOT IMPLEMENTED - NO ENDPOINT EXISTS)
**User mentioned**: `POST /api/hermes/gateway/start` with `wait=false` returns ok but status stays `running:false`

**Current state**: No `/api/hermes/gateway/start` endpoint exists in the codebase.

**What exists**:
- `POST /api/engines/hermes/dashboard` — starts Hermes dashboard, waits for port bind
- `GET /api/engines/hermes/dashboard` — returns status with `running` field

**If this is about the dashboard endpoint**:
The existing code already waits for the port (`_wait_port` in `launch.py:415`) before returning, so it SHOULD return `running:true` after successful start.

**Possible issue**: If called with a different `hermes_home`, the dashboard might start but the status check uses a different home path.

**Verify**:
```bash
# Start dashboard
curl -X POST http://127.0.0.1:8787/api/engines/hermes/dashboard \
  -H "Content-Type: application/json" \
  -d '{"hermes_home": "/path/to/saa-homes-hermes"}'

# Check status
curl http://127.0.0.1:8787/api/engines/hermes/dashboard
```

Expected: `"running": true` after POST succeeds

**If a new `/api/hermes/gateway/start` endpoint is needed**, please specify:
- What should it do differently from dashboard start?
- What gateway service is it starting?
- Should it be non-blocking (return before port binds)?

---

### 3. ⚠️ migrate-delivery guard (NO SCRIPT EXISTS YET)
**User mentioned**: migrate-delivery must only touch real job IDs; add guard rejecting junk IDs.

**Current state**: No `migrate-delivery` script exists in the codebase yet.

**What's ready**:
- `is_valid_job_id(job_id)` guard function is available in `openbot/hermes.py`
- Can be imported and used in any script

**When you write migrate-delivery**, use it like this:
```python
from openbot.hermes import cron_list, is_valid_job_id

def migrate_delivery(source_home, target_home, dry_run=True):
    """Migrate cron jobs from one Hermes home to another."""
    result = cron_list(home=source_home)
    
    if not result.get("ok"):
        raise RuntimeError(f"Failed to list cron jobs: {result.get('text')}")
    
    jobs = result.get("jobs", [])
    print(f"Found {len(jobs)} jobs to migrate")
    
    for job in jobs:
        job_id = job["id"]
        
        # GUARD: Skip garbage IDs
        if not is_valid_job_id(job_id):
            print(f"⚠️  SKIP junk ID (table chrome): {job_id}")
            continue
        
        print(f"✅ Migrating: {job_id} - {job['name']}")
        
        if not dry_run:
            # ... actual migration logic ...
            pass

# Safe dry run first
migrate_delivery("/path/to/source", "/path/to/target", dry_run=True)
```

---

### 4. ✅ Tests (DONE)
**Status**: 9 comprehensive parser tests in `tests/test_hermes_cron_parsing.py`

**Run tests**:
```bash
cd /workspace
python3 -m unittest tests.test_hermes_cron_parsing -v
```

**Expected output**: All 9 tests pass

---

## Live Verification Steps

### For SAA Homes project:

1. **Test cron parsing**:
```python
from openbot.hermes import cron_list

# Use SAA Homes Hermes home path
result = cron_list(home="C:/path/to/saa-homes-hermes")

# Should see ~50 real jobs, not garbage
print(f"Job count: {len(result.get('jobs', []))}")
for job in result["jobs"][:5]:
    print(f"  {job['id']:20} {job['name']:30} {job['schedule']}")
```

Expected: Real job names like `daily-ranking-strike`, `weekly-report`, etc.

2. **Verify dashboard status**:
```bash
# Start dashboard for SAA Homes Hermes
curl -X POST http://127.0.0.1:8787/api/engines/hermes/dashboard \
  -H "Content-Type: application/json" \
  -d '{"hermes_home": "C:/path/to/saa-homes-hermes"}'

# Check running status
curl http://127.0.0.1:8787/api/engines/hermes/dashboard
```

Expected: `"running": true, "url": "http://127.0.0.1:9119"`

---

## Summary

| Item | Status | Notes |
|------|--------|-------|
| Cron parsing fix | ✅ DONE | Tests pass, ready to merge |
| `is_valid_job_id` guard | ✅ DONE | Available for migrate-delivery |
| Tests | ✅ DONE | 9 tests, all pass |
| Gateway start endpoint | ❌ NO ENDPOINT | Clarify: dashboard vs gateway? |
| migrate-delivery script | ❌ NOT WRITTEN | Use guard when writing it |

**PR #40 is MERGE-READY** for the cron parsing fix.

Gateway status and migrate-delivery need clarification or are future work.
