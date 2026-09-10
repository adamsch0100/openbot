#!/usr/bin/env bash
set -euo pipefail
# Hourly runner — same engine; isDue() lets immediate searches through.
cd /data/workspaces/saa-homes
exec node backend/src/services/alertDigest.js "$@"
