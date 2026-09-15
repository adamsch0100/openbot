# DESIGN — overnight layout

World-class here means the Chat CEO loop, not a new palette. No Muse/Kimi Auto pin.

## Phase 1 (Muse implements + Cursor reviews, 2026-09-15)

Fused **chat-dock**: inset pill work ribbon + composer card; activity sheet as drawer overlay (stream scroll preserved). Muse `opencode/muse-spark-1.3-contributor-free` implements per `MUSE-DIRECTIVE.md`; Cursor runs tests and browser QA. Cache `v=194`.

## P0 / P1 fixed

| Screen | Width | Problem | Fix |
| --- | --- | --- | --- |
| Header | desktop + 390 | Engines honesty lived only in the footer; walk missed it | `#enginesChip` in `.bar-right`; warn = danger; click → Settings → Engines |
| Footer / About | all | Credit was one mashed paragraph vs BRAND three lines | `#footerCredit` + `#aboutCredit` with `<br />` |
| Tools → OpenCode / Hermes | all | Unwritable `/data` traceback + iframe 502 looked like a blank session | Honest `.embed-aim.wall`; hide iframe; JSON error from `start_opencode_web` |
| Chat-where / rail | all | Cos labeled Chief of Staff; host leftovers said OpenBot | Cos / OttoBot on the simple surface |
| Composer / Send | 390 | Covered by 480px rules | Rechecked clickable; no clip on Send |

## P2 (list only)

| Screen | Width | Problem | Suggested fix |
| --- | --- | --- | --- |
| Header chip | 390 | Full “Engines: Hermes Agent · OpenCode” ellipsizes to ~76px | Short label `Engines` + `title` already; optional `data-short` |
| Settings drawer | 390 | Tab list is long; Engines is findable but scrolly | Sticky active tab or two-row nav |
| Spend chip | 390 | Breakdown hidden (`meter-line: none`) | Keep; Spend / caps panel has the rest |
| Rail org-now | desktop | Long INDEX Now lines still clip | `clipWire` already; pulse_headline is the Cos one-liner |
| Tools iframe | all | Official engine chrome inside iframe is their palette | Leave it — advanced pane |
| Contrast on `.engines-chip.ok` | dark | Muted on panel can read faint next to pulse | Slightly brighter ok color if a later walk complains |
