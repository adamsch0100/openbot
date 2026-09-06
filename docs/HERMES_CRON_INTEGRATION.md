# Hermes Cron Integration — Gateway, Status, and Delivery

This document explains how OpenBot integrates with Hermes Agent cron schedules and gateway.

## Architecture

OpenBot does **not** implement a second scheduler. Hermes Agent owns cron execution.
OpenBot wires `hermes gateway` and routes results back into CEO threads.

### Components

1. **Gateway Process** — Hermes Agent's cron daemon
2. **Status API** — `/api/hermes/gateway/status` exposes running state, enabled count
3. **Delivery Route** — Cron results post to OpenBot via `--deliver local`
4. **Cronwatch** — Polls `hermes cron runs` per CEO home and writes to threads

## Gateway Management

### Starting the Gateway

Gateways start automatically when OpenBot boots via `warm_engines_background()`:

```python
from openbot.launch import ensure_gateways

ensure_gateways()  # Start gateway for each CEO with a Hermes home
```

Manual start via API:

```bash
curl -X POST http://127.0.0.1:8787/api/hermes/gateway/start \
  -H 'Content-Type: application/json' \
  -d '{"project_id": "saa-homes"}'
```

### Checking Gateway Status

Per-CEO gateway status:

```bash
curl http://127.0.0.1:8787/api/hermes/gateway/status?project_id=saa-homes
```

Response:

```json
{
  "ok": true,
  "running": true,
  "enabled_count": 33,
  "total_count": 50,
  "next_fire": null,
  "home": "/data/hermes-homes/saa-homes"
}
```

**Fields:**
- `running`: Gateway process is alive
- `enabled_count`: Schedules not marked disabled
- `total_count`: All cron entries in `hermes cron list`
- `home`: Hermes home this gateway serves

## Cron Delivery to OpenBot

### How Cron Results Reach CEO Threads

1. **Creation** — Crons created with `--deliver local`:
   ```bash
   hermes cron create "0 9 * * *" "Daily ranking" \
     --name openbot-saa-homes-daily-rank \
     --deliver local
   ```

2. **Execution** — Gateway fires the schedule

3. **Polling** — `cronwatch.ingest_cron_runs()` polls each CEO's Hermes home:
   ```python
   hermes cron runs --limit 40  # in HERMES_HOME context
   ```

4. **Routing** — Fresh runs become job cards in the CEO's thread:
   - Updates `Last: cron {job_id}`
   - Posts snippet to INDEX
   - Writes to `threads/{ceo}.json`

### Verification

Check that cron results appear in the CEO chat:

```bash
# List recent jobs for a CEO
curl http://127.0.0.1:8787/api/thread?project_id=saa-homes | jq '.turns[-5:]'

# Should show role=bot jobs with "cron": true
```

## SAA Homes Verification

SAA Homes was transferred from a standalone Hermes Railway box into OpenBot.
Here's how to verify crons are firing and visible:

### 1. Confirm Gateway Running

```bash
curl http://127.0.0.1:8787/api/hermes/gateway/status?project_id=saa-homes
```

Expect: `"running": true`, `"enabled_count": 33`

If not running:

```bash
curl -X POST http://127.0.0.1:8787/api/hermes/gateway/start \
  -d '{"project_id": "saa-homes", "wait": true}'
```

### 2. Check Hermes Home

The imported SAA Homes Hermes home should be at `/data/hermes-homes/saa-homes`.

Verify in CEO INDEX:

```bash
curl http://127.0.0.1:8787/api/org | jq '.projects[] | select(.id=="saa-homes") | .tools.hermes_home'
```

### 3. List Active Schedules

```bash
# Inside the SAA Homes Hermes home
cd /data/hermes-homes/saa-homes
hermes cron list
```

You should see ~50 crons, 33 enabled.

### 4. Watch for Cron Results

Poll the activity feed:

```bash
curl http://127.0.0.1:8787/api/activity | jq '.jobs[] | select(.cron==true) | {id, at, text}'
```

Or check the SAA Homes thread:

```bash
curl http://127.0.0.1:8787/api/thread?project_id=saa-homes | \
  jq '.turns[] | select(.job.cron==true) | .job.at'
```

### 5. Trigger a Test Cron

Create a short test schedule:

```bash
cd /data/hermes-homes/saa-homes
hermes cron create "*/5 * * * *" "Test ping for SAA Homes" \
  --name openbot-saa-test-ping \
  --deliver local
```

Wait 5 minutes. Check:

```bash
curl http://127.0.0.1:8787/api/activity | jq '.jobs[0]'
```

Should show a recent cron job card.

## Troubleshooting

### Gateway Not Running

**Symptom:** `"running": false` in status API

**Fix:**

```bash
curl -X POST http://127.0.0.1:8787/api/hermes/gateway/start \
  -d '{"project_id": "saa-homes"}'
```

Check logs:

```bash
# OpenBot board logs
docker logs openbot-production-9334 2>&1 | grep gateway

# Hermes gateway logs (if separate)
hermes gateway logs
```

### Cron Results Not Appearing in Chat

**Symptom:** Gateway running, schedules enabled, but no job cards

**Check:**

1. Cron was created with `--deliver local`:
   ```bash
   hermes cron list | grep deliver
   ```

2. Cronwatch polling is working:
   ```bash
   # Check activity endpoint (forces ingestion)
   curl http://127.0.0.1:8787/api/activity
   ```

3. Hermes home is mapped to the right CEO:
   ```bash
   curl http://127.0.0.1:8787/api/org | jq '.projects[] | {id, hermes_home: .tools.hermes_home}'
   ```

### Old Hermes Boxes Still Required?

**Current State (2026-09-06):**

Per INDEX, dual Telegram / old Railway Hermes boxes remain up during SAA Homes transfer.
Do **not** railway-down those boxes until SAA ranking succeeds in OpenBot.

**Verification:**

If SAA Homes crons fire and post results to OpenBot CEO chat for 48h without gaps,
the old boxes can be deprecated.

## API Reference

### GET `/api/hermes/gateway/status`

Query params:
- `project_id` (optional): CEO scope. Omit for staff.

Returns:

```json
{
  "ok": true,
  "running": boolean,
  "enabled_count": number,
  "total_count": number,
  "next_fire": string | null,
  "home": string
}
```

### POST `/api/hermes/gateway/start`

Body:

```json
{
  "project_id": "saa-homes",
  "wait": false
}
```

Returns:

```json
{
  "ok": true,
  "text": "gateway started"
}
```

### POST `/api/hermes/gateway/stop`

Body:

```json
{
  "project_id": "saa-homes"
}
```

Returns:

```json
{
  "ok": true,
  "text": "gateway stopped"
}
```

## See Also

- `openbot/hermes.py` — Gateway functions (`gateway_status`, `gateway_start`, `gateway_stop`)
- `openbot/cronwatch.py` — Polls cron runs and routes to threads
- `openbot/launch.py` — `ensure_gateways()` supervision
- `openbot/routines.py` — Multi-step scheduled flows (separate from Hermes cron)
