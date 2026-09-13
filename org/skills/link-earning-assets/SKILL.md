---
name: link-earning-assets
description: Citation hub + topical glossary that earn links without outreach
whenToUse: When SAA Homes (or another product CEO) needs passive backlinks, a statistics page writers and AI can cite, or a niche glossary that feeds money pages
---

# Link-earning assets

OttoBot original playbook. Inspired by the public idea that the easiest page to cite wins links — not by copying anyone’s paid Claude Code pack. Do not unzip, vendor, or redistribute third-party skill files.

## Owns

Ship two citable assets on the aimed CEO’s site, then keep them fresh:

1. **Citation hub** — dated statistics, each traced to the organization that first published the number, with a live URL.
2. **Topical glossary** — one entity per URL, definition in the first 50 words, related-term links, byline, date, sources.

Both exist to earn referring domains and AI citations **without outreach or buying links**. Internal links must still flow to money pages.

## Stopline

- Do not invent, round-up, or “about” a statistic. If the URL 404s or the figure is undated, drop the row.
- Do not mass-generate thin glossary terms to hit a vanity count. Quality over spam. YMYL + Fair Housing always.
- Do not buy links, PBNs, Web 2.0 spam, or send backlink emails. Outreach stays draft → Adam `approved`.
- Do not auto-post to Facebook / GBP / X. Do not attach weekday Think cron on live SAA Railway Hermes.
- Do not treat SAA as the first publisher of a CHFA, HUD, city, or MLS number. Cite the origin.
- Publish, merge, and deploy wait for Accept. Name the engine on the job card (board / OpenCode / Hermes Agent).

## SAA Homes (better than a generic hub)

Horizon-week is a live city or CHFA page that can take a lead. These assets serve that:

| Asset | Live path | Who cites it | Money pages it must feed |
| --- | --- | --- | --- |
| Citation hub | `/housing-statistics/` (alias `/northern-colorado-housing-statistics/`) | Journalists, bloggers, AI agents needing a Colorado / CHFA / NoCO number | `/chfa-down-payment-assistance/`, `/for-buyers/`, `/contact/` |
| Glossary | `/glossary/` + `/glossary/{term}/` | Search + AI answers on CHFA and buyer terms | Same cluster + city hubs where the term is local |

Do **not** start with 100 unverified rows or 300 doorway definitions. Start with every figure already proven on CHFA.org, City of Greeley, or this site’s CHFA cluster — then add rows only after the citation gate.

## Citation gate (every number)

A row ships only when all of these are true:

1. **Figure** — exact number or range as published (not a paraphrase that changes the math).
2. **First publisher** — CHFA, City of Greeley, HUD, Census, IRES, etc. Never “SAA Homes research” unless we originated the dataset.
3. **Source URL** — fetched, HTTP 200, same claim visible on the page (or official PDF).
4. **As-of** — the publisher’s date or reporting window (e.g. Jan 1–Dec 31 2025).
5. **Retrieved** — ISO date we last verified the URL.
6. **Cite anchor** — stable `#id` so a writer can link the specific stat.

If any field is missing: omit the row and write Blocker or Next — do not pad.

## Glossary anatomy (every term URL)

1. H1 is the query (e.g. “What is CHFA down payment assistance?”).
2. **Definition in the first 50 words.**
3. Progressive depth: who it is for in Northern Colorado, how it connects to a program page, what to do next.
4. Related terms as real `<a href="/glossary/{slug}/">` links.
5. Byline (Adam and Mandi Schwartz), last-reviewed date, sources with URLs.
6. CTA to the matching money page and `(970) 999-1407` / contact form.
7. One entity per URL. Do not dump five programs onto one slug.

## How to run this job

1. Read this CEO’s INDEX Horizons and `org/projects/saa-homes/SEO-LINK-ASSETS.md`.
2. Inventory what already ranks (CHFA cluster, blog, city hubs). Brownfield first — do not create a second competing CHFA explainer.
3. **Think** (Hermes): outline hub sections + term inventory scored by lead impact, not keyword vanity. Park anything that needs a source.
4. **Research** only when a source URL must be re-fetched. Tools stay off for Cos status.
5. **Code** (OpenCode): data files + routes + sitemap/prerender + footer + `llms.txt`. Diff card. Accept before live.
6. After Accept: INDEX Last = live URLs; Next = refresh cadence or next verified batch. Do not declare “backlinks landed” without Ahrefs/GSC proof.

## Refresh (compounding)

A hub that goes stale stops being the easy cite. Schedule a **source re-fetch** when CHFA publishes new year highlights or income limits — as an INDEX Next, not a live-Railway weekday Think cron until cutover.

## What good looks like

A journalist can quote one number, click the source, and land on CHFA.org. An AI agent reading `llms.txt` finds the hub. A Fort Collins buyer on a glossary term is one click from `/chfa-down-payment-assistance/` and a form. The job card names the engine. No invented stats. No outreach.
