# Muse Spark implements Phase 1 design (OpenCode Go contributor-free).
# Cursor acts as operator: edit org/projects/openbot/MUSE-DIRECTIVE.md first.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -c "from openbot.keyring import push_engine_wallets; push_engine_wallets()"

$brief = "org\projects\openbot\MUSE-DESIGN-BRIEF.md"
$world = "org\projects\openbot\MUSE-WORLDCLASS-BRIEF.md"
$directive = "org\projects\openbot\MUSE-DIRECTIVE.md"
if (-not (Test-Path $brief)) { Write-Error "Missing $brief" }
if (-not (Test-Path $directive)) { Write-Error "Missing $directive" }

$prompt = @"
You are Muse, the design implementer for OttoBot. Read MUSE-DESIGN-BRIEF.md and MUSE-DIRECTIVE.md.

Implement the directive in the repo (primarily web/styles.css and web/index.html). Use existing CSS variables and BRAND.md tone.
When finished, append a '## Muse pass log' section to MUSE-DIRECTIVE.md with files touched and three bullets.
Do not edit Python backend or app.js unless the directive explicitly allows it.
"@

$runArgs = @("run", "-m", "opencode/muse-spark-1.3-contributor-free", "-f", $brief, "--dir", (Get-Location), "--auto", $prompt)
if (Test-Path $world) { $runArgs = @("run", "-m", "opencode/muse-spark-1.3-contributor-free", "-f", $brief, "-f", $world, "-f", $directive, "--dir", (Get-Location), "--auto", $prompt) }
else { $runArgs = @("run", "-m", "opencode/muse-spark-1.3-contributor-free", "-f", $brief, "-f", $directive, "--dir", (Get-Location), "--auto", $prompt) }
& opencode @runArgs
