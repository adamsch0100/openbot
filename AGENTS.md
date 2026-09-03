# AGENTS.md — Cursor / coding-agent law

Read `OPENBOT.md` and `brains/INDEX.md` before changing anything.
This repo is a control plane. Do not invent a third agent runtime.

1. Change only glue, board, docs, and presets.
2. If Hermes Agent or OpenCode already has it, wire the binary. Do not reimplement it.
3. End jobs by updating `brains/INDEX.md` or the agent brain: Now / Last / Next / Blocker.
4. No secrets in files. No passwords, TOTP, or API keys in git, brains, or chat logs.
5. New tools default OFF for Cos.
6. If you stall, write one-line Blocker in INDEX and stop.
7. Every job card names the engine that ran (board / OpenCode / Hermes Agent).
8. Do not vendor `nousresearch/hermes-agent` or `anomalyco/opencode` into this tree.
9. Do not use Hermes, OpenCode, Nous, Anomaly, or Grok Bot marks as our product name or logo.
10. Browser default is accessibility snapshot + refs. Screenshots are opt-in. See `BROWSER.md`.

Week 1 only: board on 127.0.0.1:8787, engine detect, status path, code path stub, job log, README + NOTICE.
If Builder folder → change → diff card → INDEX is not delightful, stop adding features.
