# OpenBot browser — same jobs, not the same meter

Grok Bot’s “cloud browser” feels good because a page stays open, logins stick, and you can watch it.
That stack is expensive because it usually means: a warm VM + a pixel desktop + screenshots stuffed into the model on every turn.

OpenBot keeps the *jobs* (open site, click, type, extract, stay logged in when you consent).
It drops the *always-on desktop in the prompt*.

Do not write a third browser engine. Wire Hermes Agent’s browser tools. They already speak snapshots, refs, CDP, local Chrome, and optional cloud backends.

## What “same functionality” actually means

| Job people mean | Cheap way | Expensive way (avoid as default) |
|---|---|---|
| Read a public page | `web_extract` / fetch. No browser. | Headless Chrome |
| Click / fill a JS app | Hermes `browser_snapshot` + `@eN` click/type | Screenshot + vision model every step |
| Watch the agent work | Optional live view to *your* screen only | Stream frames into the LLM context |
| Stay logged in | Consent-gated profile snapshot, or you log in on your machine | Shared cloud VM with everyone’s cookies |
| Hard site (CAPTCHA, bank) | Stop. Human on the real screen | Agent fights the wall with pixels |

## Cost ladder (always climb, never start at the top)

1. **Fetch / extract** — HTML or readability text. Cents. Default for “what does this page say.”
2. **Snapshot session** — one Chromium, accessibility tree + element refs. Hermes already truncates snapshots (~15k chars) and pages the rest from cache. This is the Research preset default.
3. **One screenshot** — user or policy opt-in when the tree is lying (canvas, map, chart).
4. **Live view** — CDP screencast to the *board UI*, never into the job packet.
5. **Cloud browser vendor** — Browserbase / Browserless / Tool Gateway only when local Chrome cannot (no display server, need stealth pool). Session dies when the job dies.

Grok Bot bills you for 4–5 on almost every browse. We bill 1 or 2 unless you ask.

## Persistence without a warm cloud PC

You want state. You do not want a desktop that idles for hours.

- **Job session:** Chromium lives for this Research job only. Idle timeout, then kill.
- **Named session (opt-in):** `research-mls`, `research-title` — cookies for that name, cold when idle. Wake on the next ticket. Not a 24/7 VM.
- **Real profile (explicit consent):** Hermes can copy your Chrome/Brave/Edge profile into `~/.hermes/browser-profile/` and drive a *snapshot* of it. Live profile is not opened. Toggle off deletes the copy.
- **Login walls:** the job stops on a card. Approve a vault login, type one on that card (it is not stored in chat), or sign in on your glass. TOTP and bank walls still stay on your screen.

Cookies on disk ≠ computer left on. That is the whole cheaper trick.

## What the model sees vs what you see

**Model (job packet):** URL, title, compact a11y snapshot with `@e1` refs, last action result, optional one image.

**You (board):** same cards, plus optional “watch” pane attached to CDP. Frames go browser → UI. They do not go browser → GPU screenshot → vision tokens → next prompt.

Hermes `browser_snapshot` is the contract. OpenBot renders it. Screenshots are a button, not a loop.

## Where the browser runs (pick in this order)

1. **Local Chromium / your Chrome via `/browser connect`** — $0 infra. Best for you-first instance on a real machine.
2. **Headless Chromium on the same box as the board** — still $0 extra vendor, a bit of RAM (~0.7–1 GB while the job is alive).
3. **Hermes Tool Gateway** — if you already pay Nous Portal; no second browser SaaS.
4. **Metered cloud (Browserless, Browserbase)** — last resort. Those products bill *browser-open time*. Close the session when INDEX is updated.

Never keep a cloud browser open “so the bot has a computer.” That is Grok Bot’s meter.

## OpenBot policy (Research preset)

- Tools off unless the router chose Research or the user pasted a URL and confirmed “open browser.”
- First hop is extract. Promote to snapshot only if the page is an app or extract failed.
- Snapshot refs for click/type. No coordinate clicking.
- Password / TOTP fields: block agent input; hand to human.
- Screenshot default OFF. Live view default OFF. Both are UI, not prompt.
- Job card lists: backend (local | gateway | vendor), seconds open, snapshot chars, screenshot count, $ estimate.
- Hard cap: N browser-seconds per day. Hit cap → extract-only.

## Week 3 build (not Week 1)

Week 1 is board + INDEX + `opencode run`.
Week 3 is this ladder on top of Hermes browser, plus the watch pane that does not touch the LLM.

If Hermes already has the tool, wire it. Do not reimplement Playwright inside `openbot/`.
