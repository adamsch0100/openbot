"""Internal bus: contracts, handoffs, gates, action log. Files, not chat."""

from __future__ import annotations

import re
from pathlib import Path

from .store import ROOT, list_jobs, now_iso

ORG = ROOT / "org"
ACTION_LOG = ORG / "ACTION_LOG.md"
RULES = ORG / "RULES.md"
SECRET = re.compile(
    r"(password|passwd|totp|secret|api[_-]?key|bearer|authorization:\s*\S+)",
    re.I,
)
IRREVERSIBLE = re.compile(
    r"\b(send|publish|post|tweet|email|purchase|pay|spend|transfer|delete|"
    r"sign\b|accept terms|push(?:ed|ing)?(?:\s+to)?\s+(?:origin|remote|prod)|"
    r"production|deploy|wire money|invoice)\b",
    re.I,
)
MARKETPLACE_HIRE = re.compile(
    r"\b(gmail|chrome|slack|notion|twitter|discord|whatsapp|outlook)\s+bot\b|"
    r"\bcreate\s+(me\s+)?(\d+\s+)?(bots|agents|ai employees)\b|"
    r"\bhire\s+(a\s+)?(gmail|chrome|slack|notion)\b",
    re.I,
)
FAILURE_NOTE = re.compile(
    r"\b(we just found a failure|new (operating )?rule:|never do this again|"
    r"turn that into a (permanent )?rule|add (this|that) (to|as) (a )?rule)\b",
    re.I,
)
AUDIT_ASK = re.compile(
    r"\b(audit (the )?(jobs|runs|week|log)|sample review|friday audit|"
    r"action log)\b",
    re.I,
)
BUS_LANES = (
    "research",
    "drafts",
    "evidence",
    "reviews",
    "approved",
    "archive",
    "handoffs",
)

CONTRACTS = {
    "cos": {
        "job": "Triage, delegate, watch handoffs, collect, escalate. Do not do the work.",
        "sources": "Staff INDEX four-liners, each CEO INDEX, inbox tails. Never the vault.",
        "judgment": "Done means the right specialist owns it and a file exists. Escalate only for judgment, permission, or missing facts.",
        "output": "A route (Code / Think / Research / Ops) or a status from files. No diffs. No fetches.",
        "forbidden": "No MCP, bash, browser, publish, pay, or inventing a third engine. No app-bots (Gmail/Chrome/Slack).",
    },
    "think": {
        "job": "Hard reasoning and plans. Tools off.",
        "sources": "This CEO INDEX, BRAIN, tickets, prior HANDOFF files.",
        "judgment": "A plan is complete when Code could execute it without guessing.",
        "output": "HANDOFF with TASK, STATUS, OUTPUT, UNCERTAINTIES, NEXT OWNER.",
        "forbidden": "Do not edit the repo, browse, cron, publish, or pay.",
    },
    "builder": {
        "job": "Change code in this CEO's folder via OpenCode.",
        "sources": "The Code folder, git, INDEX, the ticket, HANDOFF from Think/Research.",
        "judgment": "Done means a local diff the operator can Accept or Reject.",
        "output": "Local edits plus a HANDOFF. Diff card is the action gate.",
        "forbidden": "No git push, publish, pay, delete remotes, or production changes. Wait for Accept.",
    },
    "research": {
        "job": "Read approved public pages. Fetch first, snapshot only if extract fails.",
        "sources": "The pasted URL and primary pages it points to. Not rumors, not memory.",
        "judgment": "Every important claim is VERIFIED, INFERRED, or UNKNOWN. Stop if the source is wrong.",
        "output": "Evidence in bus/evidence plus a HANDOFF. Do not write the final public post.",
        "forbidden": "No passwords, TOTP, publishing, or treating fetch as verification of numbers you did not check.",
    },
    "ops": {
        "job": "Schedule work in Hermes cron. Tickets live in inbox/ops.md.",
        "sources": "The operator request, INDEX, existing crons.",
        "judgment": "A routine is good when it is silent on success and idempotent on retry.",
        "output": "A cron job id and schedule. Notify only on exception or approval.",
        "forbidden": "No browser, no send/publish/pay/delete/sign. Never bypass source or evidence gates.",
    },
    "ceo": {
        "job": "Own this project's outcome. Route Code to OpenCode; Think/Research/Ops to Hermes.",
        "sources": "This INDEX, the Code folder, inbox, bus/handoffs.",
        "judgment": "Done means INDEX Next is clear and a HANDOFF exists for specialist work.",
        "output": "Short RESULT plus a bus file. Diffs wait for Accept/Reject.",
        "forbidden": "Do not publish, pay, delete, or push without the operator. Chat is not memory. No app-bots.",
    },
    "worker": {
        "job": "Help this CEO using the lane the board routed.",
        "sources": "CEO INDEX, this BRAIN, the ticket, bus/handoffs.",
        "judgment": "Hand off through a file, not a giant chat blob.",
        "output": "HANDOFF.md fields filled. Next owner named.",
        "forbidden": "Do not skip gates. Do not use the CEO's personal master accounts.",
    },
}

MEMORY_POLICY = (
    "MEMORY POLICY: remember preferences, style, format, relationships, and durable rules. "
    "Do not treat memory as truth for prices, balances, dates, inventory, campaign stats, "
    "customer/employee state, contracts, or live docs. Re-open the source. "
    "If the source is down, say SOURCE UNAVAILABLE. Never silently substitute."
)


def _slug_project(project_id: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (project_id or "staff").lower()).strip("-")
    return raw[:40] or "staff"


def bus_dir(project_id: str | None) -> Path:
    return ORG / "projects" / _slug_project(project_id) / "bus"


def ensure_bus(project_id: str | None) -> Path:
    root = bus_dir(project_id)
    for name in BUS_LANES:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def contract_lines(kind: str) -> str:
    row = CONTRACTS.get(kind) or CONTRACTS["ceo"]
    return (
        "JOB: {job}\n"
        "SOURCES: {sources}\n"
        "JUDGMENT: {judgment}\n"
        "OUTPUT: {output}\n"
        "FORBIDDEN: {forbidden}"
    ).format(**row)


def contract_section(kind: str) -> str:
    return "## Contract\n\n" + contract_lines(kind) + "\n"


def has_contract(text: str) -> bool:
    blob = text or ""
    return "## Contract" in blob or bool(re.search(r"^JOB:", blob, flags=re.M))


def seed_contract(text: str, kind: str) -> str:
    body = (text or "").rstrip()
    if has_contract(body):
        return text if text.endswith("\n") or not text else text
    if not body:
        return contract_section(kind)
    return body + "\n\n" + contract_section(kind)


def seed_file_contract(path: Path, kind: str) -> None:
    if not path.is_file():
        return
    original = path.read_text(encoding="utf-8")
    updated = seed_contract(original, kind)
    if updated != original:
        path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")


def gates_block(preset: str) -> str:
    if preset == "builder":
        action = "Local edits are reversible. git push, publish, and production wait for Accept/Reject."
    elif preset == "research":
        action = "Read and file evidence. Do not publish or send."
    elif preset == "ops":
        action = "Attach cron only. Do not send, pay, delete, or publish from cron."
    elif preset == "think":
        action = "Plan only. Code executes after you hand off."
    else:
        action = "Route. Do not act externally."
    return (
        "THREE GATES — a job may not skip these.\n"
        "GATE 1 SOURCE: facts from an approved source (INDEX, repo, pasted primary URL) or STOP.\n"
        "GATE 2 EVIDENCE: mark important claims VERIFIED / INFERRED / UNKNOWN. Stop if evidence is thin.\n"
        f"GATE 3 ACTION: {action} "
        "Park send, publish, post, spend, delete, sign, and anything a stranger sees."
    )


def handoff_instruction() -> str:
    return (
        "HANDOFF: do not pass substantial work only through chat. Write bus/handoffs.\n"
        "TASK / STATUS / OUTPUT / SOURCES / DECISIONS / UNCERTAINTIES / NEXT OWNER / DO NOT ASSUME"
    )


def law_extra(preset: str, project_id: str | None = None, worker_id: str | None = None) -> str:
    kind = "worker" if worker_id else (preset if preset in CONTRACTS else "ceo")
    parts = [
        "CONTRACT:\n" + contract_lines(kind),
        gates_block(preset),
        MEMORY_POLICY,
        handoff_instruction(),
    ]
    rules = rules_excerpt(900)
    if rules:
        parts.append("RULES (scar tissue):\n" + rules)
    return "\n\n".join(parts)


def classify_gate(
    preset: str,
    message: str,
    *,
    diff_pending: bool = False,
    login_wall: bool = False,
    ok: bool = True,
    talk: bool = False,
) -> dict:
    irreversible = bool(IRREVERSIBLE.search(message or ""))
    if login_wall:
        action = "blocked"
        label = "login wall — approve a vault login or type it here"
    elif talk or preset in {"cos", "ask"}:
        action = "allow"
        label = "reversible · talk / route"
    elif diff_pending:
        action = "approval"
        label = "action gate · Accept / Reject the diff"
    elif irreversible:
        action = "approval"
        label = "irreversible language — park send/publish/pay/delete"
    elif preset == "ops":
        action = "approval"
        label = "ops cron · silent on success, approval for external acts"
    elif preset == "research":
        action = "allow"
        label = "reversible · read and file evidence"
    elif not ok:
        action = "blocked"
        label = "stopped"
    else:
        action = "allow"
        label = "reversible · drafts and local files"
    source = "stop" if (preset == "research" and not ok) else "ok"
    evidence = "required" if preset in {"research", "builder", "think"} else "n/a"
    return {
        "source": source,
        "evidence": evidence,
        "action": action,
        "irreversible": irreversible,
        "label": label,
    }


def redact(text: str) -> str:
    lines = []
    for raw in (text or "").splitlines():
        if SECRET.search(raw):
            lines.append("[redacted]")
        else:
            lines.append(raw[:400])
    blob = "\n".join(lines).strip()
    return blob[:2400]


def write_handoff(
    job_id: str,
    preset: str,
    message: str,
    result: str,
    *,
    project_id: str | None = None,
    worker_id: str | None = None,
    engine: str = "board",
    status: str = "complete",
    sources: str = "",
    next_owner: str = "",
    blocker: str | None = None,
) -> str:
    root = ensure_bus(project_id)
    path = root / "handoffs" / f"{job_id}.md"
    if blocker and status == "complete":
        status = "blocked"
    who = worker_id or project_id or "staff"
    body = (
        f"# HANDOFF {job_id}\n\n"
        f"TASK: {redact(message)[:800] or '—'}\n"
        f"STATUS: {status}\n"
        f"OUTPUT: {redact(result)[:1600] or '—'}\n"
        f"SOURCES: {redact(sources)[:800] or 'this job packet / INDEX'}\n"
        f"DECISIONS: parked irreversible actions; specialist {preset} via {engine}\n"
        f"UNCERTAINTIES: {redact(blocker or '—')}\n"
        f"NEXT OWNER: {next_owner or 'operator or Chief of Staff'}\n"
        f"DO NOT ASSUME: live prices, balances, logins, or anything not in SOURCES\n"
        f"SEAT: {who}\n"
        f"ENGINE: {engine}\n"
        f"AT: {now_iso()}\n"
    )
    path.write_text(body, encoding="utf-8")
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def append_action_log(fields: dict) -> None:
    ORG.mkdir(parents=True, exist_ok=True)
    if not ACTION_LOG.exists():
        ACTION_LOG.write_text(
            "# ACTION_LOG\n\n"
            "Consequential runs. Never passwords, tokens, or one-time codes.\n\n",
            encoding="utf-8",
        )
    line = (
        f"- {fields.get('at') or now_iso()} · {fields.get('bot') or 'staff'} · "
        f"{fields.get('engine') or 'board'} · {fields.get('preset') or 'cos'} · "
        f"job {fields.get('id') or '—'} · {fields.get('trigger') or 'chat'} · "
        f"{fields.get('status') or 'ok'} · gate {fields.get('gate') or 'allow'} · "
        f"files {fields.get('files') or '—'} · "
        f"external {fields.get('external') or 'none'} · "
        f"approval {fields.get('approval') or 'n/a'}\n"
    )
    if SECRET.search(line):
        line = re.sub(SECRET, "[redacted]", line)
    with ACTION_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)


def close_work_job(receipt: dict, result: str) -> dict:
    """Write HANDOFF + ACTION_LOG for specialist jobs. Talk/Cos stay off the bus."""
    preset = str(receipt.get("preset") or "cos")
    talk = bool(receipt.get("talk"))
    if talk or preset in {"cos", "ask"}:
        return receipt
    job_id = str(receipt.get("id") or "")
    if not job_id:
        return receipt
    project_id = receipt.get("project_id") if isinstance(receipt.get("project_id"), str) else None
    status = "blocked" if receipt.get("blocker") else ("partial" if receipt.get("diff_pending") else "complete")
    sources = str(receipt.get("url") or "")
    next_owner = "operator (Accept / Reject)" if receipt.get("diff_pending") else str(receipt.get("next") or "")
    rel = write_handoff(
        job_id,
        preset,
        str(receipt.get("message") or ""),
        result,
        project_id=project_id,
        worker_id=receipt.get("worker_id") if isinstance(receipt.get("worker_id"), str) else None,
        engine=str(receipt.get("engine") or "board"),
        status=status,
        sources=sources,
        next_owner=next_owner,
        blocker=str(receipt.get("blocker") or "") or None,
    )
    if preset == "research" and (sources or result):
        ev = ensure_bus(project_id) / "evidence" / f"{job_id}.md"
        ev.write_text(
            f"# Evidence {job_id}\n\n"
            f"SOURCE: {redact(sources) or '—'}\n"
            f"AT: {now_iso()}\n\n"
            f"{redact(result)}\n",
            encoding="utf-8",
        )
    gate = receipt.get("gate") if isinstance(receipt.get("gate"), dict) else {}
    files = rel
    if receipt.get("diff_pending"):
        files = f"{rel}; local diff pending"
    append_action_log(
        {
            "at": receipt.get("at") or now_iso(),
            "id": job_id,
            "bot": receipt.get("worker_id") or project_id or "staff",
            "engine": receipt.get("engine"),
            "preset": preset,
            "trigger": "chat",
            "status": status,
            "gate": gate.get("action") or "allow",
            "files": files,
            "external": "attempted" if gate.get("irreversible") else "none",
            "approval": "needed" if gate.get("action") == "approval" else "n/a",
        }
    )
    receipt["handoff_path"] = rel
    return receipt


def log_approval(job: dict, accepted: bool) -> None:
    append_action_log(
        {
            "at": now_iso(),
            "id": job.get("id"),
            "bot": job.get("worker_id") or job.get("project_id") or "staff",
            "engine": job.get("engine"),
            "preset": job.get("preset"),
            "trigger": "diff-card",
            "status": "accepted" if accepted else "rejected",
            "gate": "approval",
            "files": job.get("handoff_path") or "diff",
            "external": "none",
            "approval": "received" if accepted else "denied",
        }
    )


def append_rule(note: str) -> str:
    ORG.mkdir(parents=True, exist_ok=True)
    if not RULES.exists():
        RULES.write_text(
            "# RULES\n\nScar tissue. Narrowest place that stops this class of failure.\n\n",
            encoding="utf-8",
        )
    line = f"- {now_iso()} · {redact(note)[:500]}\n"
    with RULES.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return line.strip()


def rules_excerpt(limit: int = 900) -> str:
    if not RULES.is_file():
        return ""
    text = RULES.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("- ")]
    blob = "\n".join(lines[-8:])
    return blob[:limit]


def sample_audit(limit: int = 5) -> str:
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    work = [
        job
        for job in jobs
        if job.get("preset") not in {"cos", "ask"} and not job.get("talk")
    ][: max(1, min(limit, 8))]
    if not work:
        log = ACTION_LOG.read_text(encoding="utf-8") if ACTION_LOG.is_file() else ""
        if not log.strip():
            return "No specialist runs to audit yet. Code, Think, Research, or Ops will leave HANDOFF files and an ACTION_LOG line."
        return log[-1500:]
    lines = ["Sample review (files, not chat):"]
    repeats: dict[str, int] = {}
    for job in work:
        gate = job.get("gate") if isinstance(job.get("gate"), dict) else {}
        status = "blocked" if job.get("blocker") else ("pending-approval" if job.get("diff_pending") else "ok")
        repeats[status] = repeats.get(status, 0) + 1
        lines.append(
            f"- {job.get('at')} · {job.get('preset')} · {job.get('engine')} · "
            f"{status} · gate {gate.get('action') or '—'} · job {job.get('id')}"
        )
    lines.append("Counts: " + ", ".join(f"{key} {value}" for key, value in sorted(repeats.items())))
    lines.append("Add a rule only for a repeated failure. Remove a rule that blocks unrelated work.")
    return "\n".join(lines)


def marketplace_hire_reply() -> str:
    return (
        "Do not hire a Bot for an app. Split the org where work gets blocked.\n"
        "Research waiting → Research. Code waiting → Code. A reminder → Ops.\n"
        "Propose a new worker only when one bottleneck repeats often enough to deserve an owner.\n"
        "Tell me the bottleneck, the outcome, and what that seat must not do."
    )


def failure_rule_reply(message: str) -> str:
    saved = append_rule(message)
    return (
        "Logged that as a rule in org/RULES.md. Next specialist packets will see it.\n"
        f"{saved}\n"
        "Narrowest home: contract, skill, source policy, approval, handoff, or Ops cron — not a giant constitution."
    )


def cos_file_reply(message: str) -> str | None:
    if MARKETPLACE_HIRE.search(message or ""):
        return marketplace_hire_reply()
    if FAILURE_NOTE.search(message or ""):
        return failure_rule_reply(message or "")
    if AUDIT_ASK.search(message or ""):
        return sample_audit()
    return None


def seed_preset_brains() -> None:
    brains = ROOT / "brains"
    mapping = {
        "cos": "cos",
        "think": "think",
        "builder": "builder",
        "research": "research",
        "ops": "ops",
    }
    for name, kind in mapping.items():
        seed_file_contract(brains / f"{name}.md", kind)


def seed_org_contracts(project_ids: list[str] | None = None) -> None:
    seed_preset_brains()
    projects = ORG / "projects"
    if not projects.is_dir():
        return
    wanted = {_slug_project(item) for item in (project_ids or [])}
    for folder in projects.iterdir():
        if not folder.is_dir():
            continue
        if wanted and folder.name not in wanted:
            continue
        seed_file_contract(folder / "INDEX.md", "ceo")
        ensure_bus(folder.name)
        workers = folder / "workers"
        if not workers.is_dir():
            continue
        for worker in workers.iterdir():
            seed_file_contract(worker / "BRAIN.md", "worker")
