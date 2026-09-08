---
name: support-status-update
description: Keep Working-on phases honest after each job
whenToUse: After Builder runs, a diff lands, or the owner Accepts/Rejects
---

# Support status update

## Owns
Ticket Now / Last / Next. Working-on board.

## Stopline
Do not change git. Do not Accept. Do not announce live.

## Steps
1. received → triage when classified.
2. building when openbot Builder claims the handoff.
3. in_review when a diff card is pending.
4. shipped on Accept; wontfix on Reject.
5. After shipped, draft an announce into bus/drafts.

## What good looks like
A stranger can read the Working-on pane and know what is in flight.
