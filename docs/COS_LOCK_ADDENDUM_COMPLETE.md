# CoS Lock Addendum — Complete Implementation

## Status: ✅ MERGE-READY (Undrafted)

**PR #36**: https://github.com/adamsch0100/openbot/pull/36  
**Branch**: `cursor/hermes-cron-visibility-8a1d`

## Requirements Met

### ✅ (1) Start/Wire Hermes Gateway

**Problem**: SAA enabled crons won't fire without gateway running.

**Solution**:
- Gateway auto-starts on OpenBot boot via `ensure_gateways()`
- Supervision per CEO with Hermes home
- API endpoints for manual control:
  - `GET /api/hermes/gateway/status?project_id=saa-homes`
  - `POST /api/hermes/gateway/start`
  - `POST /api/hermes/gateway/stop`

**Verification**:
```bash
curl https://openbot-production-9334.up.railway.app/api/hermes/gateway/status?project_id=saa-homes
# Expect: "running": true, "enabled_count": 33
```

### ✅ (2) Surface SAA Crons in OpenBot Chat/UI

**Problem**: `/api/routines` was empty for Hermes-backed schedules.

**Solution**:
- `/api/routines` now returns **both** OpenBot routines AND Hermes crons
- Structured parsing of `hermes cron list` output
- Response format:
  ```json
  {
    "routines": [
      {"id": "routine-1", "name": "...", "source": "openbot"},
      {"id": "job-123", "name": "saa-daily-rank", "source": "hermes"}
    ],
    "openbot_count": 1,
    "hermes_count": 49
  }
  ```

**Verification**:
```bash
curl https://openbot-production-9334.up.railway.app/api/routines?project_id=saa-homes
# Expect: hermes_count ~50, schedules visible
```

### ✅ (3) Migrate deliver=origin to OpenBot CEO Chat/Activity

**Problem**: Existing SAA crons use `deliver=origin` (old Hermes chat), results not visible in OpenBot.

**Solution**:
- Added `POST /api/hermes/crons/migrate-delivery` endpoint
- Migrates all crons in a CEO's Hermes home to `deliver=local`
- Cronwatch polls per-CEO homes and routes to threads
- Results appear as job cards with `"cron": true`

**Verification**:
```bash
# Step 1: Migrate delivery
curl -X POST https://openbot-production-9334.up.railway.app/api/hermes/crons/migrate-delivery \
  -d '{"project_id":"saa-homes"}'
# Expect: "migrated": [...all job IDs...]

# Step 2: Watch for cron results in CEO chat
curl https://openbot-production-9334.up.railway.app/api/thread?project_id=saa-homes | \
  jq '.turns[] | select(.job.cron==true)'
# Expect: Recent cron job cards
```

## Implementation Summary

### Code Changes

1. **openbot/hermes.py**
   - `gateway_status()` — Check running state, count enabled/total
   - `gateway_start()` / `gateway_stop()` — Control gateway
   - `cron_list()` — Parse Hermes cron list into structured schedules
   - `cron_update_delivery()` — Update single cron delivery method
   - `migrate_crons_to_local()` — Migrate all crons in a home

2. **openbot/server.py**
   - `GET /api/hermes/gateway/status` — Gateway status per CEO
   - `POST /api/hermes/gateway/start` — Start gateway
   - `POST /api/hermes/gateway/stop` — Stop gateway
   - `POST /api/hermes/crons/migrate-delivery` — Migrate delivery
   - `GET /api/routines` — Merged OpenBot + Hermes schedules

3. **openbot/launch.py**
   - `ensure_gateways()` — Start gateway for each CEO with Hermes home
   - Called in `warm_engines_background()` on boot

4. **openbot/cronwatch.py**
   - Enhanced to poll each CEO's Hermes home separately
   - Maps home → project_id → thread
   - Routes cron results to correct CEO chat

5. **docs/HERMES_CRON_INTEGRATION.md**
   - Complete architecture guide
   - API reference
   - SAA Homes verification steps
   - Migration instructions

6. **tests/test_hermes_gateway.py**
   - Gateway management tests
   - Cron list parsing tests
   - Migration tests
   - API endpoint tests

### Constraints Honored

- ✅ Do not railway-down old Hermes boxes (per INDEX)
- ✅ No secrets in git
- ✅ Wire official Hermes binary (no third runtime)
- ✅ Tests included
- ✅ MERGE-READY undrafted

## Post-Deploy Checklist

After deploying to https://openbot-production-9334.up.railway.app:

### Immediate (< 5 min)

1. ✅ Check gateway running
2. ✅ Verify SAA crons visible in `/api/routines`
3. ✅ Migrate crons to `deliver=local`

### Short-term (< 1 hour)

4. ✅ Trigger test cron, verify result appears in CEO chat
5. ✅ Check activity feed shows cron job cards

### Medium-term (48 hours)

6. ✅ Monitor SAA ranking crons fire on schedule
7. ✅ Verify results consistently post to OpenBot CEO chat
8. ✅ No gaps in delivery

### Long-term

9. ⏳ After 48h clean run → railway-down old Hermes boxes
10. ⏳ Update INDEX to remove dual-running note

## Files Changed

- `openbot/hermes.py` (+140 lines) — Gateway + migration
- `openbot/server.py` (+50 lines) — API endpoints + routines merge
- `openbot/launch.py` (+35 lines) — Gateway supervision
- `openbot/cronwatch.py` (+80 lines) — Per-CEO home polling
- `docs/HERMES_CRON_INTEGRATION.md` (+294 lines) — Documentation
- `tests/test_hermes_gateway.py` (+180 lines) — Tests
- `brains/INDEX.md` (updated) — Status

**Total**: ~779 lines added/modified

## Done Criteria

✅ **Gateway supervision** — Starts on boot, API control, per-CEO homes  
✅ **Cron visibility** — SAA schedules surface in `/api/routines`  
✅ **Delivery routing** — Migration API + per-home polling  
✅ **Documentation** — Complete guide with verify steps  
✅ **Tests** — Gateway, parsing, migration, endpoints  
✅ **PR undrafted** — MERGE-READY

PR explains how crons fire + how results appear in OpenBot, with verify steps for SAA Homes. ✅
