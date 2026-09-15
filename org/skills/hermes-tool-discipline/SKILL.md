---
name: hermes-tool-discipline
description: Default craft for multi-step Hermes work — narrow tools, verify writes, draft outbound
whenToUse: Any Think, Ops, or Research job that will call more than one tool, write externally, send a message, or spawn a subagent
---

# Hermes tool discipline

## Owns
How Hermes tools are used on this board. Tools are capabilities; skills are procedures. Expertise lives in skills, not in dumping manuals into the prompt.

## Stopline
- Do not paste the full Hermes tool catalog into replies or RESULT.
- Do not enable or install MCP mid-job. Off stays off; write Blocker.
- Outbound messages (email, SMS, social, CRM notes that notify) are **drafts** unless the domain skill explicitly says send — then park Needs-you when board law requires Accept.
- Never invent CRM / ledger field values. Read the record first.
- On permission / 403 / lockdown / auth errors: **stop and report**. Do not retry with a different field guess.
- Do not give a specialist terminal + unrestricted filesystem unless the skill forbids the dangerous paths and you enforce that brief.

## Steps
1. Open with a short plan: job, allowed tools, forbidden tools, done-check.
2. Prefer the narrowest tool. File over browser. API/MCP over clicking UI. Extract over dumping a whole page. Snapshot + refs over screenshots.
3. Load a domain skill (`skill_view` / board SKILL in the packet) before improvising. If none exists, finish the job then offer to save one.
4. After any external write, read it back. The artifact is proof — not the model’s claim.
5. Delegate only with a written brief: goal, tools allowed, tools forbidden, return artifact. Check that artifact before marking done.
6. Failures: log the exact tool error in RESULT / Blocker. No paraphrase that hides the code or message.

## Done means
- Plan items checked or explicitly dropped with reason
- External system matches the claimed change (or draft is parked)
- Desk status Now / Last / Next / Blocker updated
- Engine named **Hermes Agent** on the job card

## What good looks like
A junior with 80 tools never happens. One job, few tools, one proof. A stranger can verify the write without trusting the narrative.
