# SAA Homes — link-earning SEO plan (backlinks)

Addendum to `context/market-dominance-strategy.md` (four pillars + this fifth). Chat is not memory. This file is.

**Engine for this job:** board (plan + skill) → OpenCode / Cursor on the saahomes folder (pages). Hermes Think is the aimed CEO lane when vault keys exist.

## Why this beats “ask for links”

Public theory (Flavio Amiel, [Content Assets that Work](https://flavioamiel.com/content-assets-that-work/), 2026; X `@fba` 11 Sep 2026 — asset class: statistics page + glossary, zero outreach):

- Writers and AI agents link the **easiest verified number**, not the nicest pitch.
- A glossary that covers a niche with one entity per URL compounds internal links and AI citations.

SAA already owns city hubs + CHFA program pages. The gap is **passive citation**. Old `hermes/backlinks-log.csv` Web 2.0 / directory / HARO rows stay blocked. Do not revive them.

**Better than a generic 100-stat dump:** only Colorado Housing and Finance Authority, City of Greeley, and other first-publisher figures we can URL-verify. Internal links to `/chfa-down-payment-assistance/`, `/for-buyers/`, city hubs. Fair Housing + YMYL. Live `/glossary/` and `/housing-statistics/` currently serve homepage HTML (SPA fallback) — those URLs must become real pages.

X API credits on this desk: **$0.00**. Do not spend X for syndication; the article URL is enough.

## Pillar 5 — Citable assets (passive referring domains)

### A. Citation hub

| | |
| --- | --- |
| Paths | `/housing-statistics/` canonical; `/northern-colorado-housing-statistics/` alias |
| Who | Journalists, CHFA explainers, AI agents |
| Contents | Dated CHFA statewide production (2025 highlights), DPA caps, credit/contribution rules, Schools To Home, Champions, G-HOPE zones — each with source org, URL, as-of, retrieved |
| Schema | Dataset + FAQPage + BreadcrumbList |
| Conversion | CTA to CHFA DPA + contact `(970) 999-1407` |
| Refresh | When CHFA posts a new calendar-year highlight or income-limit PDF — INDEX Next, not weekday cron on live Railway |

### B. Topical glossary (CHFA + NoCO buyer terms)

| | |
| --- | --- |
| Paths | `/glossary/` A–Z index; `/glossary/{slug}/` one term |
| Anatomy | Definition in first 50 words; related terms; byline; date; sources |
| Scope (v1) | Program and buyer terms that already have proven copy on the CHFA cluster — not 300 doorway pages |
| Conversion | Each term → matching money page |

### C. Discoverability

- Footer Resources + CHFA resource hub cards
- `public/llms.txt` lists both assets so agents cite them
- Sitemap + prerender via `src/data/siteRoutes.js`
- No outreach emails unless Adam replies `approved` to a parked draft

## What we are not doing

- Buying links / PBNs / Web 2.0.
- Copying a paid Claude Code skill pack (personal licence, no redistribution).
- Fabricating Northern Colorado median prices without an IRES/MLS dated source.
- Auto-publish or attaching weekday Think cron on live SAA Hermes.
- Accepting parked SAA restore cards.

## Proof

- Draft: unique canonical on hub + one glossary term (not homepage). Patch in this repo: `org/projects/saa-homes/patches/0001-link-earning-assets.patch` (apply on `adamsch0100/saahomes`; this cloud agent cannot push that remote).
- Live (after Accept + deploy): HTTP 200, canonical self, Dataset JSON-LD, GSC coverage request.
- Backlinks: report referring domains only from Ahrefs/GSC — never invent “Forbes linked us.”

## Next batches (after v1 ships)

1. Re-fetch CHFA.org income/purchase-price PDFs when they rotate; add rows that pass the citation gate.
2. Add city-level housing figures only with dated IRES or Census URLs.
3. Grow glossary from Search Console queries that already impress but bounce — one term per URL.
