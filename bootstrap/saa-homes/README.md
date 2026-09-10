# SAA Homes Hermes bootstrap

Cron wrappers under `scripts/` are copied into `$OPENBOT_DATA_DIR/hermes-homes/saa-homes/scripts/`
on CEO bootstrap and gateway supervise. Live cron jobs call these by basename.

Source of truth for the Node engine remains `/data/workspaces/saa-homes/backend/src/services/alertDigest.js`.
