---
name: support-triage
description: Triage OpenBot help tickets and suggestions
whenToUse: When a new Suggest form, X mention, or help ticket arrives
---

# Support triage

## Owns
Classify each ticket. FAQ stays a draft. Bugs and features become a handoff.

## Stopline
Never Accept a diff. Never push. Never send email or post to X. Never touch FUB/CRM.

## Steps
1. Read the ticket file in org/projects/support/tickets.
2. Kind: faq | bug | feature | spam | needs-owner.
3. FAQ → write a reply draft in bus/drafts. Park send.
4. Bug/feature → handoff to Cos → openbot Builder. Phase = building.
5. Spam → wontfix. Brand-risk or secrets → needs-owner.

## Rules
One ticket, one owner. Status Now names the ticket id and phase.
