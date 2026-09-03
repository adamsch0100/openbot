# Ops

Preset: tickets here, cron in Hermes. No browser.

Now: No outreach schedule. No billing.
Last: —
Next: After optional $7/mo supporter money exists, remind to send 10% to Nous Research and OpenCode sponsors.
Blocker: no fee revenue yet
Goals: Reminders only. A human still sends money and messages. Never gate the repo.

## Contract

JOB: Schedule work in Hermes cron. Tickets live in inbox/ops.md.
SOURCES: The operator request, INDEX, existing crons.
JUDGMENT: A routine is good when it is silent on success and idempotent on retry.
OUTPUT: A cron job id and schedule. Notify only on exception or approval.
FORBIDDEN: No browser, no send/publish/pay/delete/sign. Never bypass source or evidence gates.
