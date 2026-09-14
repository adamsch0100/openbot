# Angle Map — SAA Homes Citation Hub (scored)

Scoring: `citation_demand × source_availability × brand_fit × risk_inverse × link_to_revenue` (each 1–5, weighted equally; max 25). Layer: national | state | local. Qualifier: M = magnet, B = bridge, C = cluster.

| # | Angle | Layer | Demand | Sources | Fit | Risk | Rev | **Score** | Qualifier | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | US housing affordability index + income needed to buy (NAR HAI) | national | 5 | 5 | 5 | 3 | 5 | **22.5** | M | CNBC/business-press staple; monthly refresh; feeds buyer CTA |
| 2 | 30-year mortgage rate trend (Freddie Mac PMMS/FRED) | national | 5 | 5 | 4 | 2 | 5 | **21.0** | M | Weekly numbers; always citable; evergreen + news-cycle spike |
| 3 | First-time buyer share, age, down payment (NAR Profile) | national | 4 | 5 | 5 | 3 | 5 | **22.0** | M | Historic-low 21% is a story editors repeat; links to CHFA context |
| 4 | US median existing-home price + 38-mo run of gains (NAR EHS) | national | 5 | 5 | 4 | 3 | 4 | **21.0** | M | Monthly magnet; national editors cite without caring about NoCO |
| 5 | FHFA HPI price-change index (purchase-only, quarterly) | national | 4 | 5 | 4 | 2 | 4 | **19.0** | M | Analysts/AI love the repeat-sales methodology |
| 6 | National inventory + months supply + cash sales share (NAR EHS) | national | 4 | 5 | 4 | 2 | 5 | **20.0** | M | Seller-side and news-cycle fuel; feeds /for-sellers/ |
| 7 | US homeownership rate + under-35 share (Census HVS) | national | 4 | 5 | 4 | 2 | 4 | **19.0** | M | Quarterly; story-rich "young buyers squeezed" |
| 8 | Colorado statewide median price + inventory pulse (CAOR) | state | 4 | 4 | 5 | 3 | 4 | **20.0** | B | State media + agencies cite; local credibility |
| 9 | Colorado population growth + Weld fastest-growing large county (Census/SDO) | state | 3 | 4 | 5 | 2 | 4 | **18.0** | B | Demand-story for NoCO in-migration |
| 10 | CHFA down payment assistance (up to $25k / 3–4%) | state | 4 | 4 | 5 | 2 | 5 | **20.0** | B | Highest lead link-to-revenue on the hub |
| 11 | CHFA income + purchase limits by county | state | 3 | 4 | 5 | 2 | 5 | **19.0** | B | Constantly searched; must match chfainfo.com exactly |
| 12 | CHFA Schools To Home (25% DPA for educators) | state | 3 | 4 | 5 | 2 | 5 | **19.0** | B | Teacher-search demand; distinct money page |
| 13 | Colorado Champions (first responders) + targeted-area DPA | state | 3 | 3 | 5 | 2 | 5 | **18.0** | B | Niche but high-intent; small source set — verify bravely |
| 14 | Larimer County median price, DOM, months supply (CAOR LMU) | local | 4 | 4 | 5 | 2 | 5 | **20.0** | C | County-level bridge between state and city |
| 15 | Weld County median price, DOM, months supply (CAOR LMU) | local | 4 | 4 | 5 | 2 | 5 | **20.0** | C | Same |
| 16 | Fort Collins market pulse (IRES/BizWest/SAA) | local | 5 | 3 | 5 | 2 | 5 | **20.0** | C | County LMU is primary; IRES public secondary; SAA figures only as clearly-labeled own data |
| 17 | Loveland market pulse + affordability vs Fort Collins | local | 4 | 3 | 5 | 2 | 5 | **19.0** | C | "Priced out of Fort Collins" is a real search |
| 18 | Greeley affordability anchor + G-HOPE | local | 4 | 3 | 5 | 2 | 5 | **19.0** | C | Most affordable NoCO entry; city program hook |
| 19 | Windsor/Timnath/Severance new-construction belt | local | 3 | 3 | 5 | 2 | 5 | **18.0** | C | Family + new-build search; thinner sources — quarantine-prone |
| 20 | "Price reductions % of active listings" (BizWest two-speeds) | local | 3 | 3 | 5 | 4 | 4 | **19.0** | optional | Great story, single secondary source — verify carefully or drop |

## Top quadrants to prioritize

1. **National magnets (1,3,4,6,2)** — these earn the DR cites and make the hub Forbes-class. Build first.
2. **CHFA bridge (10,11,12,13)** — highest lead link-to-revenue; money pages already exist.
3. **County + city cluster (14–19)** — internal equity + local press; primary sources are the CAOR LMU feeds.
4. **Timely spikes** — mortgage rate weeks, inventory shocks, NAR monthly releases: refresh ASAP, they bring fast links.

## Recommended hub URL(s)

- Canonical: `/resources/housing-statistics-2026/` (all layers, anchored sections)
- Fallback if length demands: `/resources/colorado-housing-statistics-2026/` companion for the state+CHFA bridge
- Glossary: `/glossary/` (separate layer, cross-linked) — see `glossary-seed.md`

## Quarantine-prone angles (watch)

- Windsor/Timnath/Severance (source depth thin, MLS public behind login)
- G-HOPE amount/zone details (city program docs, must match city source)
- Any "average price" stat where median exists (NAR prefers median; mislabeling sample vs population is a gate failure)