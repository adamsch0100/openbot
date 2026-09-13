# QA_PASS — overnight board

Walked on this VM: `python3 bin/openbot` → http://127.0.0.1:8787. Accessibility snapshots + refs. No secrets.

## Boot

| Check | Expected | Actual | Fix | Re-check |
| --- | --- | --- | --- | --- |
| First paint | ottobot · On it. | Pass | — | Pass |
| Composer `#form` | Clickable | Pass | — | Pass |
| Engines chip | Header chip, red if missing, never fake green | First walk: chip lived in footer and was easy to miss | Moved `#enginesChip` into header `.bar-right`; click opens Settings → Engines | v=169 HTML has chip in header; both binaries present so chip should read Engines: Hermes Agent · OpenCode |
| Footer / About credit | Three BRAND lines, Anomaly not mashed | HTML has three `<br />` lines. A11y snapshot once said Anthropic — DOM is Anomaly | Keep `#aboutCredit` / `#footerCredit` innerHTML; do not `textContent` smash | DOM grep Pass |
| Engine detect | Honest found vs missing | OpenCode 1.18.30 + Hermes present on PATH | Official installers, not vendored | Pass |
| 8787 bind | Board serves | Pass. Engine warm logged `/data` Permission denied | `_engine_data_root` falls back to `~/.openbot/engine-data` when `/data` is not writable and `OPENBOT_DATA_DIR` is unset | Restarted board; OpenCode web `ok` |
| Footer / About credit | Three BRAND lines, Anomaly not mashed | HTML has three `<br />` lines. A11y snapshot once said Anthropic — DOM is Anomaly | Keep `#aboutCredit` / `#footerCredit` innerHTML; do not `textContent` smash | DOM grep Pass |
| Engine detect | Honest found vs missing | OpenCode 1.18.30 + Hermes present on PATH | Official installers, not vendored | Pass |
| 8787 bind | Board serves | Pass. Engine warm logged `/data` Permission denied | `_engine_data_root` falls back to `~/.openbot/engine-data` when `/data` is not writable and `OPENBOT_DATA_DIR` is unset | After restart |

## Desk

| Check | Expected | Actual | Fix | Re-check |
| --- | --- | --- | --- | --- |
| Status / what is blocked | Cos, INDEX only, tools off | Pass | — | Pass |
| Chat-where / rail | OttoBot / Cos, not OpenBot / OpenCode | Host already OttoBot; Cos still said Chief of Staff | UI + `node_label` empty → Cos; packets say OttoBot Chat / Cos | Marker tests |
| YOUR MOVE | Aimed CEO name | Pass (OttoBot) | — | Pass |
| Doing / Next / Results | Distinct tabs | Pass | — | Pass |
| Add CEO | Form works; OttoBot does not mint a second host | Overnight Probe seated (throwaway). No OpenCode-named CEO | Delete Overnight Probe. Add OttoBot aliases to host id `openbot` | Probe deleted |
| Run Think now | Proposal + Do it / Ask Cos / Ask me from Chat | Job `fa60d7e0ac` Hermes Agent · HTTP 401 Invalid API key. `cron_attached: false`. INDEX Last recorded the fail. | Honest wall. Do not attach weekday cron. | Wall Pass; proposal skipped until keys |
| Builder dogfood | OpenCode diff → Accept/Reject | Job `b47feedec2` OpenCode · Invalid API key. Diff wandered into INDEX fail lines (not the CSS comment). | **Reject** restored. Cursor glue already on the branch. `public_remote_url` strips embedded credentials from git remotes so INDEX cannot store them. | Reject Pass |
| Receipts | tokens / $ | Job JSON has tokens/`$0.0` on the 401 jobs | `receiptLine` shows `{prompt}→{output} tok · $` (`$0.0000` ok) | Marker test |
| OpenCode / Hermes panes | Real session or wall, not blank fake | After data-dir fallback, POST `/api/engines/opencode/web` returns `ok` + session URL. Hermes dash `ok`. | `_engine_data_root` + `.embed-aim.wall` on start failure | Pass |

## Safety

| Check | Expected | Actual | Fix | Re-check |
| --- | --- | --- | --- | --- |
| Help | Ticket form, not smoke pings | Pass | — | Pass |
| Fix-key | Opens Keys | Path is `setSettings(true, "keys")`. No 401 card on this vault-empty walk | Keys tab relabeled Keys & wallets; order 2 | Code path Pass; 401 not live here |
| Restart | JSON, never naked 502 | Pass on gateway start | — | Pass |
| 390px | Composer + Send clickable | Pass under 480px rules | Chip max-width 76px so it does not clip Send | After v=169 |
| PR 106 / Railway / SAA cron | Untouched | Untouched | — | Pass |
| Secrets | None in git / QA / chat | Builder INDEX briefly echoed the origin URL with embedded credentials | Reject + `public_remote_url`. Git line is `https://github.com/adamsch0100/openbot` | Pass |

## Open P0

None that block Boot + Desk + Safety on the board chrome. Remaining Adam items live in INDEX Blocker (keys, Nous login, Railway).
