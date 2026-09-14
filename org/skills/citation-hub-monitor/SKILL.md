---
name: citation-hub-monitor
description: Track who cites or links the citation hub, detect new and lost backlinks, freshness debt, and AI mentions — then hand precise rebuild actions to citation-hub-builder.
whenToUse: When checking hub performance, new backlinks, lost links, who is using our statistics page, citation tracking, freshness health, or after a hub publish/refresh.
---

# Citation Hub Monitor

## Owns
Observe the live citation hub(s): **new/lost backlinks**, citing URLs, quality mix, GSC/engagement signals, AI/GEO mentions, and **freshness debt** (stale or broken sources). Emit a short operator report and a **builder action queue**. Does not rewrite the hub — that is `citation-hub-builder`.

## Stopline
- Never invent referring domains or rankings.
- Never send outreach from this skill. If a cite opportunity needs a human pitch, queue a draft note for `backlink-outreach` / Approve — do not mail.
- Never auto-accept publish/deploy.
- Do not treat vanity traffic alone as success — prefer **citing pages** and **referring domains** to the hub URL(s).
- If Ahrefs/GSC/API credentials are missing, say so and use fetch/search fallbacks; mark Evidence UNKNOWN where needed.

## Why a separate skill
Building/researching stats ≠ watching the graph. Split keeps the builder honest and the monitor on a tight cadence.

## What to watch

### Backlinks (external)
- New referring domains / URLs → hub canonical (and important `#stat-` deep links if tools allow)
- Lost links (alert + suggested fix or outreach note)
- DR/quality mix — are national magnet sections attracting higher-DR cites?
- Anchor / context — are they citing the **number**?

### Usage / who is using it
- GSC queries & clicks on hub URL(s)
- Analytics landings + engagement (if connected)
- Referring page snapshots: “Site X cited stat #Y”
- AI surfaces: spot-check whether assistants name or link the hub (GEO)

### Freshness health
- % stats verified in last 90 days
- Broken source URL count
- Sections with zero cites (improve or prune via builder)
- “Last updated” vs actual verify ledger drift

## Steps
1. Read `bus/citation-hub/INDEX.md` for canonical URL(s), last verify, prior cite snapshot.
2. Pull backlink data (Ahrefs/GSC APIs if connected; else manual/search sample — label Evidence).
3. Diff vs last snapshot → **new cites**, **lost cites**, **unchanged**.
4. Sample top new citing pages: niche relevance, follow/nofollow, context quality.
5. Check freshness ledger + spot-fetch N source URLs for 404/mismatch.
6. Optional GEO probe: 3–5 queries that should pull hub stats; note cite/miss.
7. Write report to `bus/citation-hub/monitor-latest.md` and update `bus/citation-hub/cites-log.md` (append-only).
8. Emit **Builder action queue** (ordered): fix broken sources, refresh section X, add national angle Y, improve anchors/TOC, internal-link money page Z.
9. If a high-value site used a competitor’s outdated roundup, add an **outreach opportunity** note (draft only).
10. Patch CEO INDEX Last/Next when this was the labor: Next = top builder action or wait-with-monitor-date.

## Report format (Adam-facing, short)
```text
CITATION HUB MONITOR · {date} · engine {name}
Hub: {url}
New links: N (list top 5 with DR/context if known)
Lost links: N (list)
Best cite this period: {url} — why it matters
Freshness: {verified_pct}% · broken sources {n}
GEO spot-check: {hit/miss notes}
Builder next: 1) … 2) … 3) …
Outreach notes (draft only): …
Proof: bus/citation-hub/monitor-latest.md
```

## Cadence (routines)
- **Weekly** — new/lost links + top cites
- **Monthly** — section performance + builder expand list
- **Quarterly** — full freshness audit trigger for builder
- **On alert** — broken source or sudden lost DR spike → builder within days

## Output contract
- Monitor report path
- Cite delta (new/lost)
- Freshness debt summary
- Builder action queue
- Evidence level (VERIFIED|INFERRED|UNKNOWN)
- Engine named on the job card

## What world-class looks like
Operator sees in one screen whether national magnets are attracting real publishers, whether local clusters are cited or only internally useful, what broke, and the exact next builder move — no fluff dashboard.
