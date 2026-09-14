---
name: citation-hub-builder
description: Build and continuously refresh a dual-layer statistics hub — national magnets for high-DR citations plus local clusters for money-page SEO — designed so journalists, bloggers, and AI agents prefer to cite you.
whenToUse: When the operator or CEO wants link-earning content assets, a statistics hub, citation bait, passive backlinks, Flavio-style content assets, national+local stats pages, or to expand/refresh an existing hub.
---

# Citation Hub Builder

## Owns
Design, research, write, expand, and refresh **citation hubs** (statistics pages) that earn backlinks and AI citations **without outreach**. Scope is **not** limited to local: national / category magnets and local / money-page clusters are both first-class. Produce outlines, verified stat inventories, page briefs, and Code-ready specs. Hand monitoring (who linked, lost links) to `citation-hub-monitor`.

## Stopline
- Never invent a number. If the source is dead, unclear, or the figure does not match, **quarantine** the stat — do not publish it.
- Never send outreach, buy links, or use PBNs / farms / spam directories.
- Never publish, push, or deploy without Accept.
- Fair Housing / YMYL: no steering, no fabricated market claims, no discriminatory framing.
- Do not replace `backlink-outreach` — that skill drafts asks; this skill builds the asset people cite unprompted.
- Do not skip the citation gate to “ship faster.”

## Doctrine (why this works)
Writers, journalists, agencies, and AI agents constantly need a **dated, sourced number**. They link to wherever that number is easiest and safest to cite. A hub wins when it is:
1. **Broader than your local brand** where national editors need numbers (Forbes-class bait).
2. **Deeper than generic roundups** where local intent and money pages need proof.
3. **Fresher than competitors** via scheduled re-verify + additions.
4. **Structured for extraction** (answer-first blocks, stable anchors, clear sources).

Unlimited angles. Score opportunity — never hard-cap to one geography.

## Angle classes (score all; do not self-censor)
| Class | Who cites | Job |
|---|---|---|
| National category | National press, lenders, big blogs, AI | High-DR external links |
| State / program | State media, housing agencies, nonprofits | Mid-DR + trust |
| Metro / city | Local press, niche blogs | Local pack + internal equity |
| Evergreen methodology | Analysts, AI | Long-life citations |
| Timely spike | News cycle (rates, inventory shocks) | Fast links, then refresh |

Score each angle: `citation_demand × source_availability × brand_fit × risk_inverse × link_to_revenue`.

## Dual-layer architecture (default for local businesses; adaptable)
Prefer **one canonical hub** with layered sections (or tightly cross-linked companion hubs if length demands it):

```text
/resources/{niche}-statistics-{year}/     ← stable canonical URL
  #national-{topic}                       ← magnet sections
  #state-{topic}                          ← bridge
  #local-{metro-or-city}                  ← money-page cluster + internal links
```

- Year in title/H1; **Last updated** visible near top.
- TOC / jump links by layer and topic.
- Each local block links to the relevant money URL (city, program, buyer/seller).
- Optional machine-readable table or JSON sidecar of stats for AI agents.

## Stat block anatomy (every row)
Each published stat MUST include:
1. **Claim line** — one sentence, answer-first, copy-paste friendly.
2. **Figure** — exact number/percent as in source.
3. **As-of date** — when the figure applied.
4. **Source org** — publisher name.
5. **Source URL** — live primary or clearly labeled secondary.
6. **Layer tag** — `national | state | local`.
7. **Stable anchor id** — so citations can deep-link (`#stat-median-us-dom-2026`).
8. **Verification status** — `verified | quarantine` (quarantine never ships).

Optional: short “how to cite” line; methodology note at page foot.

## Steps

### A. Discover (Research)
1. Read CEO INDEX Horizons, existing hub files under `bus/citation-hub/`, site IA, and competitor citation pages.
2. Map **who already needs numbers** in this niche (press beats, AI query patterns, industry blogs) — national and local.
3. Propose 8–20 angles across layers. Include stretch national magnets even if the business is local.
4. Output an **Angle Map** with scores and recommended hub URL(s).

### B. Outline gate (Accept)
5. Produce a sectioned outline (national → state → local). Wait for operator Accept before deep research burn when cost/time is material — or mark Auto only when policy allows research-only drafts.

### C. Research + citation gate
6. For each accepted section, gather candidate stats from primary sources first (gov, Fed, NAR/trade orgs, Census, FHFA, MLS-public, CHFA/state housing, reputable research orgs).
7. Run **citation gate** per stat:
   - URL fetches (or archived with note)
   - Figure matches source text/table
   - Date present and not silently stale
   - License/TOS allows citation
   - No double-counting or mislabeling sample vs population
8. Quarantine failures to `bus/citation-hub/quarantine.md` with reason.

### D. Write for citability
9. Draft the page (or Code brief) with:
   - Magnetic H1/title
   - Intro that states who this hub helps and how often it updates
   - Layered H2/H3s + TOC
   - Stat blocks in scan-friendly lists or tables
   - Methodology + Last updated
   - Internal links from local stats → money pages; from money pages → hub (separate Code pass if needed)
10. Schema: Article/WebPage + honest FAQ where FAQs are real; never fake Dataset claims.

### E. Expand & refresh (continuous)
11. On monitor alerts or schedule: add N new verified stats, replace stale ones, fix broken sources, open new national angles when news cycles spike.
12. Never let “Last updated” lie — bump only when real verification or additions landed.
13. Update `bus/citation-hub/INDEX.md` ledger: URL, section counts by layer, last verify, next refresh, open quarantines.

### F. Hand off
14. Code seat implements page/PR when brief is ready.
15. Monitor skill owns backlink/usage tracking after publish.
16. Outreach skill may *optionally* mention the hub in drafts — never required for this asset class to work.

## Output contract
Always return:
- **Hub URL (proposed or live)**
- **Layer mix** (counts national / state / local)
- **Angle Map** (top scored)
- **Verified inventory** (or delta since last run)
- **Quarantine list**
- **Citability checklist** (TOC, anchors, dates, sources, Last updated, internal links)
- **Next refresh actions**
- **Proof** — file paths / live URL checks the next labor must echo
- **Engine** named on the job card

## What world-class looks like
A national editor can cite a magnet section without caring about your city. A local buyer page gains equity from the local cluster. An AI agent can extract a self-contained dated claim with a source URL. Three months later the hub is fresher than copycat roundups — and monitor shows referring domains climbing without cold outreach.

## SAA Homes defaults (example, not a ceiling)
- Canonical hub idea: Northern Colorado + US housing statistics year page on saahomes.com
- National magnets: affordability, mortgage rates context, inventory, first-time buyers, insurance/cost burden — sourced to public national series
- State bridge: Colorado / CHFA program figures
- Local cluster: Larimer, Weld, Fort Collins, Loveland, Greeley, Carbon Valley — tied to city + CHFA money pages
- Still pursue any high-scoring national angle that fits housing/YMYL honestly
