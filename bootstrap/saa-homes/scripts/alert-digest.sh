#!/usr/bin/env bash
set -euo pipefail
# Bootstrapped Hermes cron wrapper — keep in repo so empty scripts/ never recurs.
cd /data/workspaces/saa-homes
exec node backend/src/services/alertDigest.js "$@"
