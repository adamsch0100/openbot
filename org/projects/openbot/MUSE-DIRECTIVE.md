# Muse pass directive (Cursor writes this; Muse implements)

**Pass:** Phase 2C — world-class visual polish (briefing + sheet + rail hints)  
**Model:** `opencode/muse-spark-1.3-contributor-free`  
**Read first:** `MUSE-WORLDCLASS-BRIEF.md` §4 components, §6 P1.4–P1.7, §7 Phase 2 CSS half  
**Do not touch:** `openbot/*.py`, Hermes, cron, secrets. **Do not rewrite** `app.js` logic — CSS/HTML only unless a class hook is missing.

## Must do (visual)

1. **Today briefing** (`.today-brief`, `.today-stats`, `.today-link`) — executive serif headline, brass kicker, Needs-you row reads urgent without screaming; mobile 390px wrap.
2. **Message types** — `.bubble.msg-briefing`, `.msg-needs-you`, `.msg-answer` distinct; status fields inside briefing use existing `.status-fields` spacing.
3. **Work sheet** — `.activity-sheet` bottom drawer: drag-handle pseudo, dimmer on `.chat-shell.activity-open::before`, max-height leaves `#chatDock` tappable (z-index stack in brief §3.1).
4. **Work rows** — `.work-row`, `.engine-pill`, `.work-row-head` align on one line desktop; stack on phone.
5. **Live strip** — `.work-status.live-now-strip` + `.live-watch-btn` feel part of dock cluster (not floating orphan).
6. **Starter chips** — `.starter-chips` / `.starter-chip` match ribbon bronze; 44px targets.
7. **Failed ribbon** — `.ribbon-fail` red-first when visible; sits before Running.
8. **Settings** — `.drawer-top-actions` layout; advanced tabs stay hidden until Advanced (class `.hidden` on nav buttons — do not remove).
9. Bump cache in `web/index.html`: `styles.css?v=196` and `app.js?v=195` (JS bumped by Cursor).

## Must not

- No new npm deps, no new pages, no third work system.
- No “board”, “engine pool”, “Cos” in user-visible copy.
- Do not break `#workTabs` / `paintWorkTabs()` / `data-work` including `failed`.
- Footer MIT credit lines byte-identical.

## Done when

- Desktop + 390px snapshots feel like one executive desk: Today card, chat, ribbon, composer, sheet.
- Append **Muse pass log** below with files + 3 bullets.

## Muse pass log (Phase 1)

Files touched: `web/styles.css`, `web/index.html` (cache `v=193` → `v=194`, chat-folder placeholder copy). No `app.js` or backend changes.

- Fused `#chatDock` desk cluster; ribbon segment states; activity sheet drawer.
- Chat head typography; removed “Board” from placeholder copy.

## Muse pass log (Phase 2C)

Files touched: `web/styles.css` (Phase 2 block polished in place), `web/index.html` (cache `styles.css?v=195` → `v=196`; `app.js` stays `v=195`). No `app.js`, backend, or footer-credit changes.

- Today briefing is an executive card (serif headline, brass kicker + left rule, urgent-without-screaming Needs-you pill, labeled Working-on/Up-next lines); stats wrap and links hit 44px targets at 390px.
- Briefing / Needs-you (brass) / Answer read as three voices; work rows use one pattern (truncating title + uppercase engine pill + state, one line desktop, stacked phone); live strip fused to the dock cluster with bronze spine + Watch button.
- Sheet chrome fixed: drag handle is an absolutely-positioned pill (no longer a flex child that shoved the title), dimmer sits under the sheet on overlay sizes and is hidden on the wide side-by-side layout, Failed segment is red-first (`order: -1`), settings top actions share one row; mobile keeps thread < dimmer < sheet < dock.
