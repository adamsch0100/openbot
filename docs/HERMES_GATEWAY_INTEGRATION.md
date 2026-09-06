# Hermes Gateway Integration — Lazy, Non-Blocking Design

OpenBot now provides **optional** Hermes gateway supervision with strict non-blocking guarantees.

## Hard Constraints

1. **NO boot-blocking** — Gateway start is fully lazy and never stalls the HTTP server
2. **Fast health checks** — `/api/health` stays fast even if gateway is down
3. **No synchronous warm** — Gateway starts only on first request, not on import
4. **Timeout protection** — All gateway operations have timeouts (default 5s for status)

## Architecture

### Gateway Lifecycle

- **Lazy start**: Gateway only starts when explicitly requested via API
- **Per-CEO homes**: Each CEO with `hermes_home` gets its own gateway process
- **Daemon threads**: Gateway processes run detached, never block HTTP handlers
- **Graceful degradation**: If gateway is down, `/api/routines` shows OpenBot routines only

### Cron Result Routing

Hermes remains the scheduler. OpenBot polls cron runs and routes results to CEO threads:

1. **Per-home polling**: `cronwatch.py` polls each CEO's Hermes home separately
2. **Thread routing**: Results post to correct CEO thread via `project_id`
3. **deliver=local**: Crons created with `--deliver local` route to OpenBot CEO chat
4. **deliver=origin**: Old crons still route to Hermes origin (pre-migration)

## API Reference

### Gateway Status

```http
GET /api/hermes/gateway/status?project_id=saa-homes
```

**Response:**

```json
{
  "running": true,
  "enabled_count": 33,
  "total_count": 50,
  "next_fire": null,
  "error": null,
  "project_id": "saa-homes"
}
```

**Guarantees:**
- Returns within 5 seconds (default timeout)
- Never blocks HTTP server startup
- Returns `running: false` if gateway isn't running (doesn't start it)

---

### Gateway Start

```http
POST /api/hermes/gateway/start
Content-Type: application/json

{
  "project_id": "saa-homes",
  "wait": false,
  "timeout": 30
}
```

**Response:**

```json
{
  "ok": true,
  "running": true,
  "started": true,
  "error": null,
  "project_id": "saa-homes"
}
```

**Parameters:**
- `project_id`: CEO scope (null for staff)
- `wait`: If true, wait for gateway to respond before returning (default: false)
- `timeout`: Max seconds to wait if `wait: true` (default: 30)

**Guarantees:**
- With `wait: false`, returns immediately after spawning process
- With `wait: true`, polls status until timeout
- Never blocks HTTP server (runs in background thread)

---

### Gateway Stop

```http
POST /api/hermes/gateway/stop
Content-Type: application/json

{
  "project_id": "saa-homes"
}
```

**Response:**

```json
{
  "ok": true,
  "stopped": true,
  "error": null,
  "project_id": "saa-homes"
}
```

---

### List Routines (Merged)

```http
GET /api/routines?project_id=saa-homes
```

**Response:**

```json
{
  "routines": [
    {
      "id": "routine-abc123",
      "name": "Daily SAA Health Check",
      "schedule": "0 9 * * *",
      "enabled": true,
      "source": "openbot",
      "project_id": "saa-homes"
    }
  ],
  "hermes_crons": [
    {
      "id": "cron-xyz789",
      "name": "saa-check-ranking",
      "schedule": "0 9 * * *",
      "enabled": true,
      "source": "hermes",
      "project_id": "saa-homes"
    }
  ],
  "openbot_count": 1,
  "hermes_count": 50,
  "total": 51
}
```

**Guarantees:**
- Returns OpenBot routines even if gateway is down
- Hermes crons only included if gateway responds within timeout
- Never blocks or fails the entire request

---

### Migrate Delivery (origin → local)

```http
POST /api/hermes/crons/migrate-delivery
Content-Type: application/json

{
  "project_id": "saa-homes",
  "dry_run": false
}
```

**Response:**

```json
{
  "ok": true,
  "migrated": ["cron-abc", "cron-def", "cron-xyz"],
  "failed": [],
  "total": 50,
  "dry_run": false,
  "project_id": "saa-homes"
}
```

**Parameters:**
- `project_id`: CEO scope (null for staff)
- `dry_run`: If true, report what would be migrated without changing (default: false)

**What it does:**
- Updates all crons with `deliver=origin` to `deliver=local`
- Ensures cron results route to OpenBot CEO chat instead of old Hermes origin
- Skips crons already using `deliver=local`

---

## SAA Homes Verification Steps

After deploying to Railway (`https://openbot-production-9334.up.railway.app`):

### 1. Check Gateway Status

```bash
curl https://openbot-production-9334.up.railway.app/api/hermes/gateway/status?project_id=saa-homes
```

**Expect:**
- `"running": true` (or false if not started yet)
- `"enabled_count": 33` (or close, depends on SAA setup)
- `"total_count": 50` (or close)

### 2. Start Gateway (if not running)

```bash
curl -X POST https://openbot-production-9334.up.railway.app/api/hermes/gateway/start \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"saa-homes","wait":true}'
```

**Expect:**
- `"ok": true`
- `"running": true`
- `"started": true`

### 3. List SAA Crons in /api/routines

```bash
curl https://openbot-production-9334.up.railway.app/api/routines?project_id=saa-homes | jq
```

**Expect:**
- `"hermes_count": 50` (or close, matching SAA setup)
- `"hermes_crons": [...]` with all SAA schedules listed
- Both OpenBot routines and Hermes crons in unified response

### 4. Migrate Existing Crons to deliver=local

```bash
curl -X POST https://openbot-production-9334.up.railway.app/api/hermes/crons/migrate-delivery \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"saa-homes","dry_run":false}'
```

**Expect:**
- `"migrated": [...]` with all job IDs that were using `deliver=origin`
- `"failed": []` (empty if all migrations succeeded)
- `"total": 50` (matching total crons)

### 5. Watch Cron Results in CEO Chat

```bash
curl https://openbot-production-9334.up.railway.app/api/thread?project_id=saa-homes | \
  jq '.turns[] | select(.job.cron==true)'
```

**Expect:**
- Cron job receipts in the SAA Homes CEO thread
- Each receipt has `"cron": true`, `"engine": "Hermes Agent"`, `"preset": "ops"`
- Results appear within minutes of scheduled fire time

### 6. Verify Health Endpoint (Non-Blocking)

```bash
time curl https://openbot-production-9334.up.railway.app/api/health
```

**Expect:**
- Returns `{"ok": true, ...}` within ~100ms
- Even if gateway is down or slow, health check stays fast
- No timeouts or 502 errors

### 7. After 48h Clean Run → Railway-Down Old Boxes

**INDEX constraint**: Do not railway-down old Hermes boxes until SAA ranking succeeds in OpenBot for 48 consecutive hours.

**Verification:**
1. Confirm SAA Homes crons firing (check `/api/thread` for recent receipts)
2. Confirm ranking jobs completing (check INDEX or CEO thread)
3. After 48h of successful runs, operator can railway-down old boxes

---

## Troubleshooting

### Gateway not starting

```bash
# Check Hermes binary present
curl https://openbot-production-9334.up.railway.app/api/engines | jq '.hermes'

# Check Hermes home configured for CEO
curl https://openbot-production-9334.up.railway.app/api/org | \
  jq '.projects[] | select(.id=="saa-homes") | .tools.hermes_home'

# Start gateway with wait flag to see errors
curl -X POST https://openbot-production-9334.up.railway.app/api/hermes/gateway/start \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"saa-homes","wait":true,"timeout":60}'
```

### Crons not firing

```bash
# Check gateway running
curl https://openbot-production-9334.up.railway.app/api/hermes/gateway/status?project_id=saa-homes

# Check cron list
curl https://openbot-production-9334.up.railway.app/api/routines?project_id=saa-homes | \
  jq '.hermes_crons | map(select(.enabled==true))'

# Check cron recent runs (via Hermes CLI on Railway VM)
hermes cron runs --limit 10
```

### Cron results not appearing in CEO chat

```bash
# Check delivery mode (should be "local" after migration)
curl https://openbot-production-9334.up.railway.app/api/routines?project_id=saa-homes | \
  jq '.hermes_crons[] | .raw' | grep deliver

# Re-run migration if still "origin"
curl -X POST https://openbot-production-9334.up.railway.app/api/hermes/crons/migrate-delivery \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"saa-homes"}'
```

---

## Design Notes

### Why Lazy Gateway?

PR #36 caused Railway timeouts/502s because `warm_engines_background()` called gateway start synchronously on boot. If Hermes gateway hung or took >30s, the HTTP server never finished starting.

**New design:**
- Gateway ONLY starts on first explicit request (e.g. `/api/hermes/gateway/start`)
- `/api/routines` gracefully degrades: shows OpenBot routines, skips Hermes crons if gateway down
- `/api/health` never touches gateway code
- All gateway operations use timeouts and background threads

### Why Per-CEO Homes?

SAA Homes has ~50 schedules in `/data/hermes-homes/saa-homes`. If all CEOs shared one gateway, a crash or config issue would break all crons. Isolated homes = isolated blast radius.

### Why deliver=local?

Old Hermes crons used `deliver=origin` (posts to Hermes dashboard topic/chat). OpenBot needs results in CEO threads so operator sees them in the unified board. Migration changes `deliver=origin` to `deliver=local`, which routes results through `cronwatch.py` into OpenBot.

---

## Testing

Run gateway tests:

```bash
python3 -m pytest tests/test_hermes_gateway.py -v
```

**Test coverage:**
- Gateway status (fast, non-blocking)
- Gateway start (lazy, daemon process)
- Gateway stop (graceful termination)
- Cron list parsing
- Migrate delivery (dry-run and real)
- Routines merge (OpenBot + Hermes)
- Non-blocking guarantees (timeout tests)

---

## Summary

✅ **Gateway supervision** — Lazy start, per-CEO homes, never blocks HTTP server  
✅ **Cron routing** — Results post to correct CEO thread via per-home polling  
✅ **/api/routines visibility** — Shows OpenBot routines + Hermes crons (unified)  
✅ **Delivery migration** — API to migrate `deliver=origin` → `deliver=local`  
✅ **Non-blocking** — Health endpoint stays fast, no synchronous gateway warm  
✅ **Documentation** — Complete guide with SAA Homes verification steps  
✅ **Tests** — Gateway management, cron parsing, migration, timeout guarantees

**Done when:** PR explains non-blocking design; operator can verify SAA Homes crons firing and visible in OpenBot; no risk of hanging `/api/health`.
