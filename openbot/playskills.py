"""Board-owned Skills (HOW). Hermes --skills is the runtime; these files are the playbook."""

from __future__ import annotations

import re
from pathlib import Path

from .store import ROOT

ORG = ROOT / "org"
SKILLS_ROOT = ORG / "skills"
FRONT = re.compile(r"^---\n(.*?)\n---\n?", re.S)

DOGFOOD = {
    "support-triage": {
        "description": "Triage OpenBot help tickets and suggestions",
        "whenToUse": "When a new Suggest form, X mention, or help ticket arrives",
        "body": """# Support triage

## Owns
Classify each ticket. FAQ stays a draft. Bugs and features become a handoff.

## Stopline
Never Accept a diff. Never push. Never send email or post to X. Never touch FUB/CRM.

## Steps
1. Read the ticket file in org/projects/support/tickets.
2. Kind: faq | bug | feature | spam | needs-owner.
3. FAQ → write a reply draft in bus/drafts. Park send.
4. Bug/feature → handoff to Cos → openbot Builder. Phase = building.
5. Spam → wontfix. Brand-risk or secrets → needs-owner.

## Rules
One ticket, one owner. Status Now names the ticket id and phase.
""",
    },
    "support-status-update": {
        "description": "Keep Working-on phases honest after each job",
        "whenToUse": "After Builder runs, a diff lands, or the owner Accepts/Rejects",
        "body": """# Support status update

## Owns
Ticket Now / Last / Next. Working-on board.

## Stopline
Do not change git. Do not Accept. Do not announce live.

## Steps
1. received → triage when classified.
2. building when openbot Builder claims the handoff.
3. in_review when a diff card is pending.
4. shipped on Accept; wontfix on Reject.
5. After shipped, draft an announce into bus/drafts.

## What good looks like
A stranger can read the Working-on pane and know what is in flight.
""",
    },
    "openbot-builder-delight": {
        "description": "Folder → change → diff card → INDEX for OpenBot itself",
        "whenToUse": "When Support or Cos hands a ticket to openbot Builder",
        "body": """# OpenBot Builder delight

## Owns
Local code change in the openbot folder via OpenCode.

## Stopline
No git push, no merge, no production. Diff waits for Accept/Reject.

## Steps
1. Read the Support ticket / HANDOFF TASK.
2. Change only glue, board, docs, presets. Wire hermes/opencode binaries.
3. Produce a local diff. Name the engine on the job card.
4. Patch INDEX Now/Last/Next. Do not treat chat as memory.

## Rules
If Builder folder → change → diff → INDEX is not delightful, stop adding features.
""",
    },
    "support-announce": {
        "description": "Draft X/changelog copy after a shipped ticket",
        "whenToUse": "After the owner Accepts a ticket diff",
        "body": """# Support announce

## Owns
Draft changelog and X copy in bus/drafts.

## Stopline
Never post. Needs-you before anything public.

## Steps
1. One sentence: what shipped.
2. No engine brand as the product. No secrets.
3. Park the draft. Wait for approval_id.
""",
    },
    "ceo-heartbeat": {
        "description": "Weekday CEO Think: why, review last labor, propose Next",
        "whenToUse": "When HEARTBEAT_TASK runs, or the operator asks what to do next from PULSE",
        "body": """# CEO heartbeat

## Owns
Audit scar and last labor against Proof, then propose one next-best-action tied to Horizons. Write Why. Classify from Next, not Why.

## Stopline
Do not edit the repo. Do not browse unless Evidence needs a source and Research is the lane. Never publish, delete, or sign. Financial (pay, price, spend) follows AUTO POLICY. Never auto-post. Do not invent busywork when Horizon-week is a live page.

## Steps
1. Read SCAR and LAST LABOR REVIEW. Failed / drifted / unproven stays until matching lane echoes Proof, or Skip note clears the scar.
2. Read PULSE (schedule, last jobs, git, week proof, repeats) and Horizons. Re-open live stats if the move depends on them.
3. Name what you are not doing (Alternatives) so the operator can challenge the why.
4. Output exactly: Why, Horizon, Evidence (VERIFIED|INFERRED|UNKNOWN), Alternatives, Review (implemented|drifted|failed|unproven|none), Lane (code|research|ops|none), Next, Auto (yes|no), Uncertainties, Discuss, Proof.
5. Auto: no if Evidence is UNKNOWN, Review/Scar is drifted/failed/unproven, Next is off-horizon or week already proven, Next is publish/delete/sign, or AUTO POLICY for that class is notify. Financial includes pay, price, and spend.

## What good looks like
A stranger can read Why and know why this move serves this week's Horizon. Proof is checkable from files, not a receipt.
""",
    },
    "engine-hermes": {
        "description": "How OttoBot seats use Hermes Agent — menu, home isolation, cron, MCP locks",
        "whenToUse": "Every Think, Ops, or Research job on a seated CEO. Cos never loads this.",
        "body": """# Engine — Hermes Agent

## Owns
The Hermes menu for this CEO seat: what is unlocked, what stays off, and how RESULT lands back on the board.

## Stopline
- Status / “what’s going on” / pulse → **tools off**. Desk status (STATUS / INDEX) only. Never start a gateway to answer a status question.
- Use **this CEO’s** `hermes_home` only. Do not touch another CEO’s home, cron table, MEMORY.md, or skills.
- Do not invent tools Hermes does not expose on this home.
- No Telegram / Discord / Slack mesh from the board. No SMS. No CRM send. No spend, publish, pay, delete, or sign.
- Chat is not memory. MEMORY.md / USER.md on this home are durable; thread JSON is for humans.

## Menu (know it; do not turn everything on)

| Capability | When unlocked on this seat |
|---|---|
| Desk status read/write | Always for status path (tools off) |
| Skills (`--skills` / skill_view) | After board sync into this home |
| Cron / schedule | Ops lane; create with deliver that posts RESULT to **this** CEO thread |
| Snapshot browser | Research only; a11y snapshot + refs; screenshots opt-in |
| MCP tools | Only servers this CEO toggled — never “all catalog” |
| Memory | This home’s MEMORY.md / USER.md |
| Delegation / long jobs | Think / Ops when the ticket says so |

Full picture ≠ all tools on. Name the unlocked item you will use.

## Steps
1. Confirm lane: Think (decide) · Ops (schedule / watch) · Research (look). Wrong lane → stop and reclassify.
2. Load the matching domain skill before improvising. Prefer board SKILL.md already in the packet.
3. Stay inside this CEO folder + hermes_home. Cross-CEO work is a Cos handoff, not a side quest.
4. Cron jobs: silent on success; failures and artifacts return as RESULT (≤ 20 lines). Raw log stays in `jobs/`.
5. MCP: if a needed server is off, write Blocker and stop — do not install or enable MCP yourself.
6. End by patching this CEO’s desk status: Now / Last / Next / Blocker. Name the engine **Hermes Agent** on the job card.

## What good looks like
A stranger can read RESULT and know which Hermes capability ran, on which CEO home, and what file or schedule proves it. No other CEO’s cron or memory was touched.
""",
    },
    "engine-opencode": {
        "description": "How OttoBot seats use OpenCode — folder, diff card, Accept gate, MCP locks",
        "whenToUse": "Every Builder / Code job on a seated CEO. Cos never loads this.",
        "body": """# Engine — OpenCode

## Owns
Local code change in the aimed CEO’s work folder via OpenCode. Diff card waits for the human. Push/merge/deploy stay operator.

## Stopline
- Path is `opencode run` → **diff card** → Accept / Reject. Never silent-apply to production.
- No git push, merge, force-push, or production deploy from this seat.
- No secrets in the repo, brains, or RESULT. Keys stay in vault / env, never in diffs.
- Do not reimplement Hermes cron, gateway, or browser inside OpenCode.
- Cos never sees GitHub / git MCP schemas. MCP only when this CEO toggled it onto Code.
- No “while I’m here” refactors. Ticket scope only.

## Menu (know it; do not turn everything on)

| Capability | When unlocked on this seat |
|---|---|
| Edit files in CEO work folder | Builder / Code jobs |
| LSP / diagnostics | Via OpenCode in that folder |
| GitHub / git MCP | Only if this CEO authorized MCP for Code |
| Diff card + Accept/Reject | Always — human gate |
| Push / merge / publish | Operator only, never auto |

## Steps
1. Read the ticket / HANDOFF. Confirm the aimed CEO folder (not another CEO’s tree).
2. Change glue, board, docs, presets, or that CEO’s product code — wire `hermes` / `opencode` binaries; do not vendor those engines.
3. Produce a local diff. Name the engine **OpenCode** on the job card.
4. RESULT ≤ 20 lines + VERIFY (what to check). Raw log stays in `jobs/`.
5. Patch this CEO’s desk status: Now / Last / Next / Blocker. Diff parks on Needs-you until Accept.
6. Reject restores. Accept is human-only for merge/push when policy says so.

## What good looks like
Folder → change → diff card → desk status. A stranger can Accept or Reject without reading chat. Scope matches the ticket; no engine reimplementation, no secrets in the tree.
""",
    },
    "hermes-tool-discipline": {
        "description": "Default craft for multi-step Hermes work — narrow tools, verify writes, draft outbound",
        "whenToUse": "Any Think, Ops, or Research job that will call more than one tool, write externally, send a message, or spawn a subagent",
        "body": """# Hermes tool discipline

## Owns
How Hermes tools are used on this board. Tools are capabilities; skills are procedures. Expertise lives in skills, not in dumping manuals into the prompt.

## Stopline
- Do not paste the full Hermes tool catalog into replies or RESULT.
- Do not enable or install MCP mid-job. Off stays off; write Blocker.
- Outbound messages (email, SMS, social, CRM notes that notify) are **drafts** unless the domain skill explicitly says send — then park Needs-you when board law requires Accept.
- Never invent CRM / ledger field values. Read the record first.
- On permission / 403 / lockdown / auth errors: **stop and report**. Do not retry with a different field guess.
- Do not give a specialist terminal + unrestricted filesystem unless the skill forbids the dangerous paths and you enforce that brief.

## Steps
1. Open with a short plan: job, allowed tools, forbidden tools, done-check.
2. Prefer the narrowest tool. File over browser. API/MCP over clicking UI. Extract over dumping a whole page. Snapshot + refs over screenshots.
3. Load a domain skill (`skill_view` / board SKILL in the packet) before improvising. If none exists, finish the job then offer to save one.
4. After any external write, read it back. The artifact is proof — not the model’s claim.
5. Delegate only with a written brief: goal, tools allowed, tools forbidden, return artifact. Check that artifact before marking done.
6. Failures: log the exact tool error in RESULT / Blocker. No paraphrase that hides the code or message.

## Done means
- Plan items checked or explicitly dropped with reason
- External system matches the claimed change (or draft is parked)
- Desk status Now / Last / Next / Blocker updated
- Engine named **Hermes Agent** on the job card

## What good looks like
A junior with 80 tools never happens. One job, few tools, one proof. A stranger can verify the write without trusting the narrative.
""",
    },
}


def skills_root() -> Path:
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    return SKILLS_ROOT


def skill_dir(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")[:80]
    return skills_root() / (slug or "skill")


def parse_skill(text: str, name: str = "") -> dict:
    meta = {"name": name, "description": "", "whenToUse": ""}
    body = text or ""
    match = FRONT.match(body)
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            if key in meta:
                meta[key] = val.strip()
        body = body[match.end() :]
    return {
        "name": meta["name"] or name,
        "description": meta["description"],
        "whenToUse": meta["whenToUse"],
        "body": body.strip(),
        "text": text,
    }


def render_skill(name: str, description: str, when_to_use: str, body: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"whenToUse: {when_to_use}\n"
        "---\n\n"
        f"{(body or '').rstrip()}\n"
    )


def write_skill(name: str, description: str, when_to_use: str, body: str) -> dict:
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")[:80]
    if not slug:
        raise ValueError("name required")
    dest = skill_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)
    text = render_skill(slug, description, when_to_use, body)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")
    return parse_skill(text, slug)


def read_skill(name: str) -> dict | None:
    path = skill_dir(name) / "SKILL.md"
    if not path.is_file():
        return None
    return parse_skill(path.read_text(encoding="utf-8"), name)


def list_board_skills() -> list[dict]:
    seed_dogfood_skills()
    rows = []
    for path in sorted(skills_root().glob("*/SKILL.md")):
        parsed = parse_skill(path.read_text(encoding="utf-8"), path.parent.name)
        parsed["path"] = str(path.relative_to(ROOT)).replace("\\", "/")
        rows.append(parsed)
    return rows


def seed_dogfood_skills() -> None:
    for name, spec in DOGFOOD.items():
        path = skill_dir(name) / "SKILL.md"
        if path.is_file():
            continue
        write_skill(name, spec["description"], spec["whenToUse"], spec["body"])


def skill_packet(project_id: str | None, preset: str) -> str:
    """Inject matching Skill playbooks into a job packet."""
    seed_dogfood_skills()
    names: list[str] = []
    pid = str(project_id or "")
    # Engine menu + craft first (Cos stays blind — no engine skills).
    if preset in {"think", "ops", "research"}:
        names.extend(["engine-hermes", "hermes-tool-discipline"])
    if preset == "builder":
        names.append("engine-opencode")
    if pid == "support" or preset in {"ops", "think"}:
        names.extend(["support-triage", "support-status-update"])
        if preset == "ops":
            names.append("support-announce")
    if preset == "think":
        names.append("ceo-heartbeat")
    if pid in {"openbot", ""} and preset == "builder":
        names.append("openbot-builder-delight")
    # SAA Homes — passive link assets (national magnets + local clusters)
    if pid == "saa-homes" and preset in {"think", "research", "ops", "builder"}:
        names.extend(
            [
                "citation-hub-builder",
                "citation-hub-monitor",
                "topical-authority-glossary",
            ]
        )
    bits = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        skill = read_skill(name)
        if not skill:
            continue
        bits.append(
            f"SKILL {skill['name']} (HOW this job is done; a routine is only WHEN it runs):\n"
            f"whenToUse: {skill.get('whenToUse')}\n"
            f"{skill.get('body')}"
        )
    return "\n\n".join(bits)


def sync_skills_to_hermes_home(hermes_home: str | None) -> int:
    """Copy board Skills into a Hermes home so `hermes --skills` can load them."""
    if not hermes_home:
        return 0
    dest_root = Path(hermes_home) / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill in list_board_skills():
        dest = dest_root / skill["name"]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(skill["text"] or "", encoding="utf-8")
        count += 1
    return count
