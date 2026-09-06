# INDEX

Source of truth for this OpenBot instance. Status questions read this file only.

Now: PR #44 MERGE-READY — Mobile UX fix (compact composer, strip Meta pricing junk, readable chat history)
Last: Operator Vitzer reported mobile "still terrible" with screenshot. Fixed: 9px "Talking to" label, 15px textarea (UI font not serif), stream padding max(140px,25vh), Meta Model API pricing/rate-limits stripped in cleanBotText, single-row composer controls 36-38px height. Tested 390×844, 393×851, 375×667.
Next: Operator test on real phone, merge if delightful
Blocker: —

## Vault

- Keys live in `secrets.local.json` on this machine (gitignored). Same idea as `.env`. Not markdown. Not chat.
- Site logins live in that same vault. You → Keys → Site logins, or approve them on a login card when a job hits a wall.
- Unlock PIN in You → Settings gates the board. Do not paste keys or passwords into chat.
- OpenCode (three Go wallets, same catalog): shared pool first, then SAA Homes / Conversion, then ListLogic. OpenRouter PAYG last.
- Seats are Auto unless you pin: Auto uses Muse Spark Contributor Free while OpenCode lists it, then Chat flash / Think-Code Arena / Ops cheap Go. Empty Chat can still be Board (INDEX) for free status.
- CEO pins: openbot + Nadia → shared pool. SAA Homes → SAA Go. ListLogic → ListLogic Go. If that wallet is empty the instance chain is next.
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
- Tickets: org/projects/openbot/inbox.md

## Engines

- board: this process
- OpenCode: found — board start warms `opencode web` on :4096 in the OpenCode tab
- Hermes Agent: found on D:\Users\adamm\hermes — board start warms `hermes dashboard` on :9119 in the Hermes tab
