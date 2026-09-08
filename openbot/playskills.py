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
    if pid == "support" or preset in {"ops", "think"}:
        names.extend(["support-triage", "support-status-update"])
        if preset == "ops":
            names.append("support-announce")
    if pid in {"openbot", ""} and preset == "builder":
        names.append("openbot-builder-delight")
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
