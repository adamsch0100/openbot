# INDEX

Source of truth for this OpenBot instance. Status questions read this file only.

Now: PR #53 merged (OpenCode Go provider fix). OpenCode/deepseek-v4-flash now calls opencode-go, not Anthropic.
Last: Rebased #53 onto #52. Both session carry + Anthropic failover AND split_model Go mapping are in master.
Next: Continue from Chief of Staff — no infrastructure changes needed
Blocker: —

## Vault

- Keys live in `secrets.local.json` on this machine (gitignored). Same idea as `.env`. Not markdown. Not chat.
- Site logins live in that same vault. You → Keys → Site logins, or approve them on a login card when a job hits a wall.
- Unlock PIN in You → Settings gates the board. Do not paste keys or passwords into chat.
- OpenCode (three Go wallets, same catalog): shared pool first, then SAA Homes / Conversion, then ListLogic wallet if still in the keyring. OpenRouter PAYG last.
- Seats are Auto unless you pin: Auto stays on OpenCode Go (flash). Muse Spark on an OpenRouter id is not Auto. OpenRouter PAYG is last after the three Go wallets. Empty Chat can still be Board (INDEX) for free status.
- CEO pins: openbot + Support → shared pool. SAA Homes → SAA Go. Nadia and ListLogic CEOs are retired from routing (folders stay on disk).
- Hermes native: Nous Portal subscription. Subscribe at portal.nousresearch.com/r/adam-schwartz. Connect with `hermes portal` or paste `NOUS_API_KEY`. Not in this vault yet, so Auto is Go then OpenRouter.
- PAYG: OpenRouter after the three Go wallets are empty, plus OpenCode Zen after Go quota
- Not imported: Telegram, SMTP, GitHub, Meta — those stay on Railway. TOTP and CAPTCHA still stop on this screen.

## Railway Hermes (source)

- ListLogic Hermes
- SAA Homes Hermes
- SAA Conversion Hermes
- Each already had a Go key and the same OpenRouter fallback. Lab keys stay on those Hermes instances if they were already there.

## Instance

- URL: http://127.0.0.1:8787
- Phase: operator-only (local org)
- Work dir: C:\Users\adamm\Projects\openbot
- Default: Auto on OpenCode Go, then the other Go wallets, OpenRouter last.
- Plan: org/projects/openbot/INDEX.md
- Tickets: org/projects/support/tickets (file via You → Help; Support is a CEO)
- Support files: org/projects/support/INDEX.md

## Engines

- board: this process
- OpenCode: found — board start warms `opencode web` on :4096 in the OpenCode tab
- Hermes Agent: found on D:\Users\adamm\hermes — board start warms `hermes dashboard` on :9119 in the Hermes tab
