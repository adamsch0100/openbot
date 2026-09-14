# Citation Hub Plan — SAA Homes / Schwartz and Associates

> Drafted by: citation-hub-builder · 2026-09-14 · **Status: draft · awaiting Adam `accepted` · no public publish**
> Publish gate: Adam `accepted` (see Accept gates) + Research citation verify per stat.

---

## 1. Why this asset exists (tied to the goal)

**Goal:** Be the name Northern Colorado thinks of when buying or selling a home online.

A citation hub earns the **referring-domain backbone** the 27 area pages and CHFA cluster need to win Tier S, Tier A, and linkable informational queries. It is an **E-E-A-T weapon** (dated, source-verified, non-anonymous, no editorialized market data) that:

1. **Attracts links** — national and state reporters, researchers, bloggers, and local organizations cite clean single-number stats with primary-source chips instead of writing their own.
2. **Animates money pages** — every stat presented on the hub internal-links to a matching buyer/seller/program page, feeding the demand-capture system (Pillar 1 + Pillar 3).
3. **Proves we verify** — every stat carries a visible source org, direct URL, and "verified [date]." This is the opposite of anonymous AI content and mass-generated shells (Pillar 4).
4. **Keeps freshness as a moat** — quarterly re-verify keeps us one of the few *dated, sourced* NoCo stat resources; competitors serve stale unsourced numbers.

Fair Housing: hub stats are market/census/program facts only. No protected-class steering, no neighborhood income generalizations.

---

## 2. Doctrine (from INDEX.md)

**Dual-layer national magnets + Colorado/CHFA bridge + Northern Colorado local cluster.**

- **Layer 1 — National magnets (high-DR cites):** broad single-number stats reporters and national blogs love to cite (median price, 30-yr rate, first-time buyer share, homeownership rate, HPI, starts). High authority-pull, high link volume; lower direct lead value. Do NOT hard-cap angles to local — national is where referring domains come from.
- **Layer 2 — Colorado/CHFA bridge:** state-level market numbers + CHFA program facts. Unique to Colorado, uniquely winnable, feeds the program cluster (Pillar 1). This is the layer competitors cannot copy from a national template.
- **Layer 3 — Northern Colorado local cluster:** Larimer / Weld / Boulder county and city stats, each verified to a primary source (Census ACS, county assessor, Colorado Association of REALTORS). Highest lead value; every local stat drives an area/money page.
- **Internal linking is mandatory** — every stat card and every layer page links to at least one money page per the mapping table (§6). The hub only exists to feed money pages + earn links.

Layer tags used across the ledger: `national` · `state-co` · `program-chfa` · `local-noco`.

---

## 3. Objectives & success metrics (report monthly)

| Objective | Metric | Target direction |
|-----------|--------|------------------|
| Referring domains (fresh, earned) | New RDs citing /resources/ URLs | ↑ MoM; ≥3 new/wk after month 1 |
| Link quality | RDs from DR≥30 sites; gov/edu/org splits | ↑ share of quality |
| Search visibility | GSC impressions+clicks for `/resources/housing-statistics-2026/` and sub-pages | ↑ MoM |
| Anchor/keyword capture | `chfa down payment assistance`, `fort collins median home price`, `colorado first time homebuyer` → hub/cluster | rank ≤10 for ≥5 patterns by Q2 |
| Freshness | Share of published stats with `verified` stamp ≤90 days old | ≥80% always |
| Conversion | CTA clicks + form leads attributed to hub traffic (`interest=` tags) | ↑ MoM |
| Negative signal | Unverified stats accidentally published | NEVER; all unverified → quarantine |
| Risk | Broken source links (404/redirect on cite URLs) | <2% of cites at any check |

Freshness % definition: `stats stamped verified within last 90 days ÷ all published stats`.

---

## 4. Information architecture / URLs

Single canonical family under `/resources/`. Year in the hub slug keeps it evergreen-comparable; sub-pages are year-free so their authority accumulates.

```
/resources/housing-statistics-2026/                      HUB (money-page CTAs, stat-grid digest, glossary strip)
├── /resources/housing-statistics-2026/national-housing-market/     Layer 1 — national magnets
├── /resources/housing-statistics-2026/colorado-housing-market/     Layer 2 — Colorado/CHFA bridge
└── /resources/housing-statistics-2026/northern-colorado-housing-statistics/  Layer 3 — local cluster
```

Each layer page is fully citable standalone (no orphan stats). Optional deeper stat pages only if a stat becomes high-demand (e.g., `/national-housing-market/mortgage-rates/`) — decided at Accept gate, never auto-created.

### Page anatomy (every layer page + hub)

1. H1 with layer + year (e.g., "2026 Northern Colorado Housing Statistics")
2. Intro 60–90 words — local voice, dated, names Adam & Mandi as the data editors
3. Stat-card grid — each card = claim + big number + source chip + verified stamp + CTA
4. "Verified sources" appendix — every cite URL, checked by Research
5. FAQ (schema FAQPage via areaFaqs pattern)
6. Money-page CTA modules at top and bottom (intent-matched, Pillar 3)

Hub-only extras: layer navigation, glossary strip (topical-authority-glossary), print-citation block, "Last verified" line.

---

## 5. Citability UX (making people cite US by citing THEM)

| Element | Spec |
|---------|------|
| Verified chip | `✓ verified 2026-09-14` on every published stat — with the primary-source URL as the linked chip |
| Source chip | Org name + direct URL to primary table/report (`target="_blank" rel="noopener noreferrer"`) — we link OUT, they link back |
| Date stamps | `Published <date>` and `Last verified <date>` visible on page + in source block |
| Stat cards | Claim header, number (≥ font 3xl), unit/yr, source chip, one money CTA max |
| Definition tooltips | Glossary terms get inline hover/tooltip via topical-authority-glossary; hub glossary strip links to money pages too |
| Cite-this-block | One-click copy of `Source: org — City, CO — saahomes.com/resources/...` for journalists |
| Data honesty | Any stat NOT verified at primary source → **not published**; goes to quarantine.md. No "approx" gloss over unverified numbers |
| Fair Housing strip | Footer disclaimer: market-level facts only; equal housing opportunity; nothing guaranteed |

---

## 6. Internal links to money pages (mandatory budget)

Hub and every layer page carry 2–4 money links in-context + one CTA module top and one bottom.

| Layer / stat theme | Money page target(s) |
|--------------------|----------------------|
| National → buyer | `/for-buyers/`, `/properties/`, `/mortgage-calculator/` |
| National → seller | `/for-sellers/` (free market report capture) |
| 30-yr rate / rates | `/mortgage-calculator/`, `/for-buyers/` |
| CHFA / DPA / program | `/chfa-down-payment-assistance/`, `/chfa-schools-to-home/`, `/colorado-champions-home-loan-program/` |
| State CO market | `/for-sellers/` + top area page |
| NoCo local stat `{city}` | `/northern-colorado-areas/{slug}/` + `/properties/` |
| Veterans / VA stat | `/veterans/` |
| Luxury / $1M stat | `/luxury-real-estate/` |
| Assumable / mortgage stat | `/assumable-mortgages/` |

Anchor policy: descriptive, keyword-relevant ("Fort Collins homes for sale", "sell my home in Windsor", "CHFA down payment assistance"), never "click here". Area pages and blogs reciprocally link the hub (hub-and-spoke).

---

## 7. Accept gates (nothing publishes without them)

| Gate | Who | Fires when | Blocks |
|------|-----|-----------|--------|
| **G1 — Research citation verify** | Research seat | Every stat before publish | Any stat that cannot be found at its primary source URL → quarantine |
| **G2 — Builder review** | citation-hub-builder | Page assembled | Duplicate/unnumbered claims, missing CTAs, >1 DIY stat, no money-link budget met |
| **G3 — Adam `accepted`** | Adam | First publish of hub + any NEW page/stat-set; expansion of an ALREADY-accepted page that only refreshes stamps = auto | No public publish until Adam replies `accepted` |
| **G4 — Deploy** | Deploy (CI) | After G3 | Deploy if freshness stamps not updated |

No outreach sends from this asset (scope). Link-building on verified stats rides the existing `backlink-outreach` skill (draft → `approved` → send).

---

## 8. Rollout

1. **Sprint A — Skeleton:** hub + 3 layer pages shell, money-link budget, CTA modules, source-block pattern → Accept gate.
2. **Sprint B — Layer 1 (national):** publish 10 verified national stats (stat-candidates IDs N01–N10) → Accept.
3. **Sprint C — Layer 2 (CO/CHFA):** publish state + program stats (S01–S08, P01–P06) → Accept.
4. **Sprint D — Layer 3 (local):** publish NoCo stats (L01–L06), wire city area pages to hub → Accept.
5. **Sprint E — Web of citing:** glossary strip live; area pages + key blogs (market updates, program posts) add hub citations; handoff to citation-hub-monitor for first RD baseline; optional backlink-outreach drafts on top candidates.
6. **Steady state:** refresh-cadence.md weekly/monthly/quarterly loops.

---

## 9. Anti-patterns (never)

- Publish unverified numbers or "verified" stamps on stats that did not pass G1
- Downsource to Zillow/Realtor.com listings as "official" — primary/gov/association sources only
- Mass-generate per-city stat pages beyond accepted IA
- Editorialize market data or fabricate MoM trends
- Protected-class statistics or steering (Fair Housing)
- Outreach sends by this seat
- Let freshness debt exceed 20% (see refresh-cadence.md)

---

## 10. Success checkpoint (90 days)

≥3 new referring domains/wk citing /resources/* · ≥80% stats verified ≤90d · ≥5 keyword patterns ≤10 · ≥10 form leads attributed to hub CTAs · 0 stale stamps published.