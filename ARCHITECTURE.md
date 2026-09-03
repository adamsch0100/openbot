# OpenBot architecture — cheap by default, capable on demand

Companion to `OPENBOT.md`. This is the “why it is cheaper than Grok Bot and still feels like a teammate” file.

## The problem we are solving

Grok Bot feels good because:

- Named bots
- A chat you can keep talking in
- Browser, terminal, files, MCP, logins in one surface

It gets expensive because the hosted design usually does all of this on every turn:

1. Re-send the entire conversation (and tool dumps) as prompt tokens
2. Keep a cloud desktop warm
3. Browse with screenshots / pixel streams (images are token-heavy)
4. Advertise every tool and every MCP to every bot
5. Hide the model and the meter

OpenBot keeps the *surface* and changes the *meter*.

Chat is the UI. Files are the memory. Engines are rented only for a job.

## Product shape

```
┌─────────────────────────────────────────────┐
│  OpenBot board  (local UI, one composer)    │
│  looks like a bot chat. is not the database │
└──────────────┬──────────────────────────────┘
               │ routes
     ┌─────────┼──────────┐
     ▼         ▼          ▼
  Cos       Builder     Research / Ops
  files     OpenCode    Hermes + snapshot
  only      + git MCP   browser / cron
```

Chief of Staff is the dispatcher, not an engine. CEOs own OpenCode (folder) and Hermes (private home). They do not DM. INDEX, inbox, and BRAIN are the bus. Cos status is a short projection of those files — not a replay of chat, and not a third runtime.

Do not vendor QwenPaw / Scroll. That stack is another agent loop (CodeAct over a session environment). OpenBot already keeps history off the prompt: thread JSON is UI, INDEX is memory, jobs stay on disk.

- **OpenBot** = control plane: routing, INDEX, job log, spend cap, presets, board UI
- **Hermes Agent** = ops, memory, skills, cron, long jobs (official binary)
- **OpenCode** = code edits, diffs, LSP, MCP (`opencode run` / `opencode web`)

Do not write a third agent loop.

## Internal chat that is not eternal context

The board stores a *thread for the human*. The model does not get that thread raw.

### What the human sees

A Grok-Bot-like column:

- Bot name + avatar
- Composer always at the bottom
- Cards in the stream: text, diff, INDEX update, job cost, snapshot, blocker
- Optional “open raw Hermes / OpenCode” for power users

### What the model actually receives

A **job packet**, not the archive:

```
SYSTEM: agent law + preset (Cos / Builder / Research / Ops)
INDEX:  brains/INDEX.md          (short, current)
BRAIN:  brains/<bot>.md          (Now / Last / Next / Blocker)
TICKET: inbox/<bot>.md           (if any)
TASK:   this user message only
HINTS:  last 3 job RESULT lines  (not the full chat)
```

Rules:

- Status questions: INDEX only, tools OFF, cheap model
- Follow-ups in the same thread still start from INDEX + brain, not from turn 47
- If the user says “as I said earlier,” OpenBot searches the thread locally and injects one quote — it does not replay the week
- After every job, the engine writes a RESULT and OpenBot patches INDEX / brain
- Thread JSON lives on disk for the UI. It is never the prompt

That is how you keep “internal chat” without paying for a novel on every keystroke.

## Memory per bot (without stuffing history)

Each bot is a folder, not a context window.

```
brains/
  INDEX.md              # board source of truth
  cos.md
  builder.md
  research.md
  ops.md
inbox/
  builder.md            # four-line tickets only
```

Each brain is four lines plus optional notes:

```
Now:
Last:
Next:
Blocker:
```

Hermes already persists `MEMORY.md` / `USER.md` / `SOUL.md` and loads skills on demand. Use that for *durable* preference memory. Do not duplicate it in the chat log.

OpenCode sessions are disposable after the diff + RESULT land in INDEX.

User-facing “choose a bot” = choose a brain + a preset + a pinned model. Same computer is *not* required. Isolation is a feature.

## Tools only when necessary

Default is **no tools**. Tools are a preset, not a personality.

| Preset    | Engine              | Tools                         | Typical model        |
|-----------|---------------------|-------------------------------|----------------------|
| Cos       | none / tiny local   | files read, INDEX write       | small / local        |
| Builder   | OpenCode            | workspace + git MCP           | mid coding model     |
| Research  | Hermes + snapshot   | fetch + a11y snapshot         | mid + cheap search   |
| Ops       | Hermes              | cron, notify, no browser      | small                |

Spin-up rules:

- Terminal / coding session: only on Builder, via `opencode run` in the chosen folder
- Browser: Research only, **accessibility snapshot + refs**, not a live pixel desktop
- Screenshot: explicit button. Never default
- MCP: off until the user toggles it onto *one* preset (usually Builder)
- Login walls: stop and ask the human on *their* screen. Do not keep a shared logged-in cloud browser
- Cron: Hermes schedule, result posted back to INDEX, not a running chat

OpenCode’s own docs say MCP tools consume context — enable only what you need. Hermes toolsets and MCP filtering exist for the same reason. Wire those switches. Do not invent a new permission system.

## Cost architecture (the actual product)

Every turn has a visible receipt.

```
job_id
preset
engine
model
prompt_tokens
cached_tokens
output_tokens
tools_on
usd_estimate
cap_remaining
```

Hard rules:

1. **Status path is free-ish.** Tools off. INDEX only. Small model.
2. **Work path is one-shot.** Start job → engine runs → RESULT → stop. No warm VM.
3. **No screenshot default.** Snapshots are text. Images are opt-in.
4. **No tool catalog dump.** Cos never sees GitHub MCP schemas.
5. **Spend policy, not one pile of dollars.** Job receipts stay the local ledger. OpenCode Go is a quota wallet (percent used from their API). PAYG (Zen, OpenRouter, API keys) is a dollar cap you set. Default: cap binds PAYG only; while Go still has room, OpenCode does not eat the cap. Hit a hard cap → Chief of Staff / INDEX only until reset or you raise it. Zen card balance is not on the public API yet.
6. **Model picker is first-class.** Pin per bot. Default ladder:
   - Cos / status: cheapest available (local if present, else a small OpenRouter or Zen model)
   - Builder: user’s coding model (OpenCode already lists providers)
   - Research: mid model + cheap fetch
   - Hard reasoning: user opts in per job
7. **Cache what is stable.** INDEX + law + brain change slowly; put them first so providers can prefix-cache.
8. **Never re-send tool output.** Summarize to RESULT (≤ 20 lines). Raw logs stay in `jobs/<id>.log`.

This is why it beats a hosted cloud bot on a 2025–2026 income: you pay inference for the *job*, not rent for a desktop plus a 200k prompt.

## Routing algorithm (keep this dumb)

```
if message is status / “what’s going on” / “what’s blocked”:
    Cos or Hermes tools-OFF + INDEX
elif message is code change / diff / test / commit in a folder:
    Builder → opencode run
elif message is “every morning” / “watch this” / “remind”:
    Ops → Hermes cron
elif message has a URL or “look at this site”:
    Research → snapshot worker
else:
    ask one clarifying chip: Status / Code / Research / Schedule
```

Do not hide a 12-way agent picker behind the composer. Four presets. One composer.

## UX that still feels like Grok Bot

Steal the *feeling*, not the machine:

- Named bots with avatars (ours, not their marks)
- Persistent left rail of bots
- Cards instead of walls of tool JSON
- “Work in this folder” chip
- Diff card with Accept / Reject
- Job cost under every assistant bubble
- Advanced drawer: tokens, engine, MCP toggles, raw brain, OpenCode session, Hermes cron

Do not steal:

- Their name, logo, or “cloud computer” copy
- A shared logged-in VM as the default
- Eternal transcript-as-memory

## First build (do not skip)

Week 1 is the whole bet:

1. Local board on `http://127.0.0.1:8787`
2. Detect `hermes` and `opencode` binaries; link official installers if missing
3. One composer → status path (INDEX) and code path (`opencode run`)
4. Job log with token / $ estimate
5. README + NOTICE (MIT wrap, no trademark)

If Builder “folder → change → diff card → INDEX” is not delightful, stop adding Research chrome.

## What “done” means for affordability

A user can:

- Chat internally all day with Cos and spend cents
- Point Builder at a repo, get a diff, see $0.04 on the card
- Pin Hermes 70B local for Ops and Grok / Claude / GPT for Builder
- Turn GitHub MCP on for one bot and off for the rest
- Hit a weekly cap instead of an uncapped cloud meter

They never have to know which engine ran unless they open the drawer.
