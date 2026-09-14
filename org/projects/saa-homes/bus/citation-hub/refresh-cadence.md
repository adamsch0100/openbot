# Refresh cadence — citation hub + monitor loop

Skills: `citation-hub-builder` (mutate asset) · `citation-hub-monitor` (observe) · OttoBot seats/models from **Settings** (no ad-hoc provider overrides).

## Weekly (Research · citation-hub-monitor)
1. Diff referring domains / URLs to hub (Ahrefs/GSC if connected; else sample + label Evidence).
2. Note lost links (especially DR50+).
3. Spot-fetch 10 source URLs for 404/mismatch.
4. GEO spot-check: 3 prompts that should surface hub stats.
5. Write `monitor-latest.md`; append `cites-log.md`.
6. Emit ranked **builder action queue** (fix sources → refresh section → add national angle → internal links).
7. No outreach sends from monitor.

## Monthly (Think → Research · citation-hub-builder)
1. Read monitor-latest + angle-map; score new national/state/local angles (do not self-limit to local).
2. Add ≥5 candidate stats or refresh stale magnets (rates, NAR monthly).
3. Research runs citation gate; quarantine failures.
4. Code brief only after Accept for public page changes.

## Quarterly
1. Full re-verify of all published stats.
2. Prune zero-cite thin sections or upgrade them.
3. Glossary batch (+10 terms) via `topical-authority-glossary`.
4. Report to Adam: new RDs, freshness %, top cites, next magnets.

## Alert → action
| Signal | Owner | SLA |
|---|---|---|
| Broken source on published magnet | Builder + Research | 7 days |
| Lost DR50+ link | Monitor note → optional outreach draft | Approve-gated |
| 0 new RDs for 45 days post-publish | Builder expands national magnets | Next monthly |
| Verified_pct < 70% | Quarterly full re-verify | Same quarter |

## OttoBot wiring
- Routines live under `bus/routines/` for SAA Homes.
- Skill packet injects the three skills on Think/Research/Ops/Builder for `saa-homes`.
- Connectors toggles enable the skills on those seats.
- Models: whatever Auto / seated models Adam set in Settings.
