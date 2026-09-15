# Muse Spark — world-class product brief (docs only, no web/ edits).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -c "from openbot.keyring import push_engine_wallets; push_engine_wallets()"

$brief = "org\projects\openbot\MUSE-DESIGN-BRIEF.md"
$audit = "org\projects\openbot\MUSE-PRODUCT-AUDIT.md"
$out = "org\projects\openbot\MUSE-WORLDCLASS-BRIEF.md"
if (-not (Test-Path $brief)) { Write-Error "Missing $brief" }
if (-not (Test-Path $audit)) { Write-Error "Missing $audit" }

$prompt = @"
You are Muse, lead product designer for OttoBot. Read MUSE-DESIGN-BRIEF.md and MUSE-PRODUCT-AUDIT.md fully.

Write org/projects/openbot/MUSE-WORLDCLASS-BRIEF.md (create or replace). This is the north-star UX spec to reach world-class / shippable quality for Adam running real businesses.

Structure the brief:
1. Product promise (one paragraph, non-engineer)
2. Core loops (Goals → Work → Chat steering → Engines)
3. Screen inventory: Chat, Work sheet, Org rail, Tools (Code/Hermes), Setup/You — mobile + desktop behaviors
4. Component spec: briefing card, message types, work row, live strip, Needs-you card, CEO desk card
5. Copy rules (forbidden phrases vs allowed CEO voice); engine naming on cards
6. P0 / P1 / P2 backlog with acceptance criteria each
7. Phased implementation map (which files: index.html, styles.css, app.js — what each phase touches)
8. Risks and what NOT to build (no third runtime, no backend cron changes in UI-only phases)

Be opinionated and concrete. Reference audit IDs (P0.1 etc). Do not edit web/, Python, or backend. Only write MUSE-WORLDCLASS-BRIEF.md.
"@

opencode run -m "opencode/muse-spark-1.3-contributor-free" -f $brief -f $audit --dir (Get-Location) --auto $prompt

if (-not (Test-Path $out)) { Write-Error "Muse did not write $out" }
Write-Host "Wrote $out"
