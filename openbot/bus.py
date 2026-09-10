"""Internal bus: contracts, handoffs, gates, action log. Files, not chat."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import ROOT, list_jobs, now_iso

ORG = ROOT / "org"
ACTION_LOG = ORG / "ACTION_LOG.md"
RULES = ORG / "RULES.md"
SECRET = re.compile(
    r"(password|passwd|totp|secret|api[_-]?key|bearer|authorization:\s*\S+)",
    re.I,
)
DRAFT_OK = re.compile(
    r"\b(draft|queue|prepare|suggest|do not send|don't send|park)\b",
    re.I,
)
APPROVAL_TTL_MIN = 60
DENIED_MCP = frozenset({"fub", "followupboss", "flask-isa", "flask_isa", "stripe"})
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
        "judgment": "A routine is good when it is silent on success and idempotent on retry. Routines load a Skill (HOW); cron is only WHEN.",
        "output": "A cron job id and schedule. Notify only on exception or approval.",
        "forbidden": "No browser, no send/publish/pay/delete/sign. Never bypass source or evidence gates.",
    },
    "support": {
        "job": "Own tickets and suggestions. Triage, schedule, tell the status story, draft replies.",
        "sources": "Support INDEX, ticket files, OpenBot docs, bus/handoffs.",
        "judgment": "FAQ drafts stay in bus/drafts. Bugs/features hand off to Cos → openbot Builder.",
        "output": "Ticket phase updates, HANDOFF files, draft replies. Diffs wait for Accept/Reject.",
        "forbidden": "No Accept, no push, no live X post, no CRM/FUB, no unsupervised send.",
    },
    "ceo": {
        "job": "Run this company. Own P&L. Pay for this seat first, then profit. Spin Code/Think/Research/Ops or a named worker when a bottleneck repeats. No CFO/COO bots — you are the C-suite.",
        "sources": "This INDEX (doctrine + north-star), the Code folder, inbox, bus/handoffs, live site/metrics.",
        "judgment": "Done means INDEX Next is a next-best-action tied to revenue. Ask Cos if stuck. Ping Adam only for keys, money, login, publish, pay, delete, sign.",
        "output": "Short RESULT plus a bus file. Name the engine. Diffs and public posts wait for Accept/Reject.",
        "forbidden": "Do not publish, pay, delete, or push without the operator. Do not auto-post to Facebook/X. Chat is not memory. No extra C-suite bots.",
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
    if str(project_id or "") == "support" and not worker_id:
        kind = "support"
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
        # Success is silent. Park only when irreversible (handled above).
        # Do not stamp approval / draft spam on OPS_OK.
        action = "allow"
        label = "ops · silent on success"
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
    from_seat: str = "",
    to_seat: str = "",
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
        f"FROM: {from_seat or who}\n"
        f"TO: {to_seat or (next_owner if next_owner not in {'operator', 'operator or Chief of Staff'} else '—')}\n"
        f"NEXT OWNER: {next_owner or 'operator or Chief of Staff'}\n"
        f"SOURCES: {redact(sources)[:800] or 'this job packet / INDEX'}\n"
        f"DECISIONS: parked irreversible actions; specialist {preset} via {engine}\n"
        f"UNCERTAINTIES: {redact(blocker or '—')}\n"
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
    
    # Determine handoff routing (from previous → current preset)
    handoff_list = receipt.get("handoff") or []
    from_seat = handoff_list[-2] if len(handoff_list) >= 2 else ""
    to_seat = preset
    
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
        from_seat=from_seat,
        to_seat=to_seat,
    )
    
    # Add handoff metadata for UI card display ONLY on real multi-step chains
    # (len >= 2 means Cos routed then agent ran, or agent→agent handoff)
    if len(handoff_list) >= 2:
        handoff_from = handoff_list[-2]
        handoff_to = preset
        if handoff_from != handoff_to and handoff_to not in {"cos", "ask"}:
            receipt["handoff_from"] = handoff_from
            receipt["handoff_to"] = handoff_to
            receipt["handoff_status"] = status
            receipt["handoff_task"] = str(receipt.get("message") or "")
            receipt["handoff_output"] = result
            receipt["handoff_next_owner"] = next_owner
    
    # Auto-create handoffs based on result signals
    if status == "complete" and not receipt.get("blocker"):
        from .queueworker import auto_create_handoffs
        created = auto_create_handoffs(receipt, result, project_id)
        if created:
            receipt["auto_handoffs"] = created

    if preset == "research" and (sources or result):
        ev_rel = write_evidence_record(
            job_id,
            project_id=project_id,
            produced_by=str(receipt.get("engine") or "research"),
            source=sources,
            result=result,
        )
        receipt["evidence_path"] = ev_rel
        ev_file = ROOT / ev_rel
        blob = ev_file.read_text(encoding="utf-8") if ev_file.is_file() else result
        if not evidence_has_source(blob):
            receipt["blocker"] = receipt.get("blocker") or "unsourced evidence — bounce"
            status = "blocked" 
    gate = receipt.get("gate") if isinstance(receipt.get("gate"), dict) else {}
    files = rel
    if preset == "research" and receipt.get("evidence_path"):
        files = f"{rel}; {receipt.get('evidence_path')}"
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
        "approval": receipt.get("approval_id")
        or ("needed" if gate.get("action") == "approval" else "n/a"),
        }
    )
    receipt["handoff_path"] = rel
    return receipt


def load_open_handoffs(project_id: str | None, *, limit: int = 20) -> list[dict]:
    """Load open handoffs (STATUS not complete/partial) for a CEO scope.
    
    Returns list of dicts with: id, task, status, output, from_seat, to_seat, 
    next_owner, path. Sorted newest first.
    """
    root = ensure_bus(project_id)
    handoffs_dir = root / "handoffs"
    if not handoffs_dir.is_dir():
        return []
    
    results = []
    files = sorted(handoffs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    for path in files[:limit]:
        try:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            
            # Extract fields from structured format
            fields = {}
            for line in lines:
                if line.startswith("TASK:"):
                    fields["task"] = line[5:].strip()
                elif line.startswith("STATUS:"):
                    fields["status"] = line[7:].strip()
                elif line.startswith("OUTPUT:"):
                    fields["output"] = line[7:].strip()
                elif line.startswith("FROM:"):
                    fields["from_seat"] = line[5:].strip()
                elif line.startswith("TO:"):
                    fields["to_seat"] = line[3:].strip()
                elif line.startswith("NEXT OWNER:"):
                    fields["next_owner"] = line[11:].strip()
            
            status = fields.get("status", "").lower()
            # Only include open/claimed/blocked handoffs, not complete/partial
            if status not in {"complete", "partial"}:
                # Try relative_to(ROOT), fallback to absolute path
                try:
                    rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
                except ValueError:
                    rel_path = str(path)
                    
                results.append({
                    "id": path.stem,
                    "task": fields.get("task", "—"),
                    "status": status or "open",
                    "output": fields.get("output", "—"),
                    "from_seat": fields.get("from_seat", "—"),
                    "to_seat": fields.get("to_seat", "—"),
                    "next_owner": fields.get("next_owner", "—"),
                    "path": rel_path,
                })
        except (OSError, UnicodeDecodeError):
            continue
    
    return results


def create_handoff(
    task: str,
    project_id: str | None,
    from_seat: str,
    to_seat: str,
    next_owner: str = "",
    output: str = "",
) -> dict:
    """Create an open handoff for async work.
    
    Returns {"ok": bool, "message": str, "handoff_id": str|None, "path": str|None}
    """
    if not task or not to_seat:
        return {"ok": False, "message": "task and to_seat required", "handoff_id": None, "path": None}
    
    import uuid
    handoff_id = f"handoff-{uuid.uuid4().hex[:8]}"
    
    try:
        path_str = write_handoff(
            job_id=handoff_id,
            preset=to_seat,
            message=task,
            result=output or "—",
            project_id=project_id,
            status="open",
            next_owner=next_owner or to_seat,
            from_seat=from_seat,
            to_seat=to_seat,
            engine="board",
        )
        return {
            "ok": True,
            "message": f"Handoff {handoff_id} created",
            "handoff_id": handoff_id,
            "path": path_str,
        }
    except (OSError, ValueError) as err:
        return {"ok": False, "message": f"Failed to create: {err}", "handoff_id": None, "path": None}


def claim_handoff(handoff_id: str, project_id: str | None, claimant: str) -> dict:
    """Claim an open handoff by changing STATUS to claimed and setting NEXT OWNER.
    
    Returns {"ok": bool, "message": str, "handoff": dict|None}
    """
    root = ensure_bus(project_id)
    path = root / "handoffs" / f"{handoff_id}.md"
    
    if not path.is_file():
        return {"ok": False, "message": "Handoff not found", "handoff": None}
    
    try:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        
        # Check current status
        current_status = ""
        for line in lines:
            if line.startswith("STATUS:"):
                current_status = line[7:].strip().lower()
                break
        
        if current_status in {"complete", "partial"}:
            return {"ok": False, "message": f"Handoff already {current_status}", "handoff": None}
        
        # Update STATUS and NEXT OWNER
        updated_lines = []
        for line in lines:
            if line.startswith("STATUS:"):
                updated_lines.append("STATUS: claimed")
            elif line.startswith("NEXT OWNER:"):
                updated_lines.append(f"NEXT OWNER: {claimant}")
            else:
                updated_lines.append(line)
        
        path.write_text("\n".join(updated_lines), encoding="utf-8")
        
        return {
            "ok": True,
            "message": f"Handoff {handoff_id} claimed by {claimant}",
            "handoff": {"id": handoff_id, "status": "claimed", "next_owner": claimant}
        }
    except (OSError, UnicodeDecodeError) as err:
        return {"ok": False, "message": f"Failed to claim: {err}", "handoff": None}


def handoff_summary(project_id: str | None) -> str:
    """Generate a brief summary of open handoffs for job packets.
    
    Format: 'N open handoffs: [id: task → next_owner], ...'
    """
    handoffs = load_open_handoffs(project_id, limit=10)
    if not handoffs:
        return ""
    
    parts = [f"{len(handoffs)} open handoff{'s' if len(handoffs) != 1 else ''}:"]
    for h in handoffs[:5]:
        task_brief = h["task"][:60].replace("\n", " ")
        parts.append(f"  {h['id']}: {task_brief} → {h['next_owner']}")
    
    if len(handoffs) > 5:
        parts.append(f"  ... and {len(handoffs) - 5} more")
    
    return "\n".join(parts)


def log_approval(job: dict, accepted: bool, force: bool = False, action: str = "decide") -> None:
    log_entry = {
        "at": now_iso(),
        "id": job.get("id"),
        "bot": job.get("worker_id") or job.get("project_id") or "staff",
        "engine": job.get("engine"),
        "preset": job.get("preset"),
        "trigger": "diff-card" if action == "decide" else "revert-card",
        "status": "accepted" if accepted else ("rejected" if action == "decide" else "reverted"),
        "gate": "approval",
        "files": job.get("handoff_path") or "diff",
        "external": "none",
        "approval": str(job.get("approval_id") or "received" if accepted else "denied"),
    }
    if force:
        log_entry["force_accepted"] = True
        if job.get("validation_error"):
            log_entry["validation_bypassed"] = job.get("validation_error")[:200]  # Cap for logs
    append_action_log(log_entry)


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
        seed_file_contract(folder / "INDEX.md", "support" if folder.name == "support" else "ceo")
        ensure_bus(folder.name)
        workers = folder / "workers"
        if not workers.is_dir():
            continue
        for worker in workers.iterdir():
            seed_file_contract(worker / "BRAIN.md", "worker")


def should_park_irreversible(preset: str, message: str) -> bool:
    """True when the job must stop for a Needs-you card before external IO."""
    if preset in {"cos", "ask", "think", "research"}:
        return False
    text = message or ""
    if DRAFT_OK.search(text):
        return False
    if preset == "builder":
        return bool(
            re.search(
                r"\b(push(?:ed|ing)?(?:\s+to)?\s+(?:origin|remote|prod)|publish|deploy|production)\b",
                text,
                re.I,
            )
        )
    return bool(IRREVERSIBLE.search(text))


def approvals_dir() -> Path:
    path = ORG / "approvals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def drafts_dir(project_id: str | None, lane: str = "drafts") -> Path:
    root = ensure_bus(project_id)
    path = root / lane
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_draft(
    *,
    kind: str,
    body: str,
    project_id: str | None,
    ticket_id: str = "",
    title: str = "",
) -> dict:
    draft_id = f"draft-{uuid.uuid4().hex[:8]}"
    path = drafts_dir(project_id, "drafts") / f"{draft_id}.md"
    payload = (
        f"# {title or kind}\n\n"
        f"ID: {draft_id}\n"
        f"KIND: {kind}\n"
        f"STATUS: draft\n"
        f"TICKET: {ticket_id or '—'}\n"
        f"AT: {now_iso()}\n\n"
        f"{redact(body)}\n"
    )
    path.write_text(payload, encoding="utf-8")
    return {
        "id": draft_id,
        "kind": kind,
        "status": "draft",
        "ticket_id": ticket_id,
        "project_id": project_id,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "title": title or kind,
        "body": body,
    }


def _parse_draft(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fields = {"id": path.stem, "path": str(path.relative_to(ROOT)).replace("\\", "/"), "body": text}
    for line in text.splitlines()[:12]:
        if line.startswith("ID:"):
            fields["id"] = line[3:].strip()
        elif line.startswith("KIND:"):
            fields["kind"] = line[5:].strip()
        elif line.startswith("STATUS:"):
            fields["status"] = line[7:].strip()
        elif line.startswith("TICKET:"):
            fields["ticket_id"] = line[7:].strip()
        elif line.startswith("# "):
            fields["title"] = line[2:].strip()
    return fields


def list_drafts(project_id: str | None, lane: str = "drafts", limit: int = 20) -> list[dict]:
    folder = drafts_dir(project_id, lane)
    rows = []
    for path in sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            rows.append(_parse_draft(path))
        except (OSError, UnicodeDecodeError):
            continue
    return rows


def move_draft(draft_id: str, project_id: str | None, dest_lane: str) -> dict:
    if dest_lane not in {"drafts", "reviews", "approved", "archive"}:
        raise ValueError("invalid lane")
    found = None
    for lane in ("drafts", "reviews", "approved", "archive"):
        path = drafts_dir(project_id, lane) / f"{draft_id}.md"
        if path.is_file():
            found = path
            break
    if found is None:
        raise ValueError("draft not found")
    dest = drafts_dir(project_id, dest_lane) / found.name
    text = found.read_text(encoding="utf-8")
    text = re.sub(r"^STATUS:.*$", f"STATUS: {dest_lane}", text, count=1, flags=re.M)
    dest.write_text(text, encoding="utf-8")
    if dest.resolve() != found.resolve():
        found.unlink()
    return _parse_draft(dest)


def write_evidence_record(
    job_id: str,
    *,
    project_id: str | None,
    produced_by: str,
    claims: list[dict] | None = None,
    source: str = "",
    result: str = "",
) -> str:
    root = ensure_bus(project_id)
    path = root / "evidence" / f"{job_id}.md"
    rows = claims or []
    if not rows and (source or result):
        rows = [
            {
                "claim": redact(result)[:400] or "research result",
                "source": source or "—",
                "read_at": now_iso(),
                "produced_by": produced_by,
            }
        ]
    lines = [f"# Evidence {job_id}", "", f"PRODUCED_BY: {produced_by}", f"AT: {now_iso()}", ""]
    missing = False
    for row in rows:
        src = str(row.get("source") or "").strip()
        read_at = str(row.get("read_at") or now_iso())
        claim = str(row.get("claim") or "").strip()
        if not src or src in {"—", "-", "MISSING"}:
            missing = True
            src = ""
        lines.append(f"CLAIM: {redact(claim)}")
        lines.append(f"SOURCE: {redact(src) or 'MISSING'}")
        lines.append(f"READ_AT: {read_at}")
        lines.append("")
    if missing:
        lines.append("STATUS: bounce — unsourced claim")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def evidence_has_source(text: str) -> bool:
    blob = text or ""
    if "SOURCE: MISSING" in blob or re.search(r"^SOURCE:\s+[—\-]?$", blob, re.M):
        return False
    return bool(re.search(r"^SOURCE:\s+\S+", blob, re.M))


def _iso_to_dt(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def create_gate_approval(
    *,
    job_id: str,
    project_id: str | None,
    kind: str,
    message: str,
    ttl_min: int = APPROVAL_TTL_MIN,
) -> dict:
    approval_id = f"apr-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(5, int(ttl_min)))
    row = {
        "id": approval_id,
        "kind": kind,
        "status": "pending",
        "job_id": job_id,
        "project_id": project_id or "",
        "message": redact(message)[:800],
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "decided_at": "",
        "actor": "",
    }
    path = approvals_dir() / f"{approval_id}.json"
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def expire_approvals() -> list[dict]:
    expired = []
    now = datetime.now(timezone.utc)
    for path in approvals_dir().glob("apr-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(row.get("status") or "") != "pending":
            continue
        exp = _iso_to_dt(str(row.get("expires_at") or ""))
        if exp and exp < now:
            row["status"] = "expired"
            path.write_text(json.dumps(row, indent=2), encoding="utf-8")
            append_action_log(
                {
                    "id": row.get("job_id") or row.get("id"),
                    "bot": row.get("project_id") or "staff",
                    "engine": "board",
                    "preset": "ops",
                    "trigger": "approval-expiry",
                    "status": "expired",
                    "gate": "approval",
                    "approval": row.get("id"),
                    "external": "none",
                }
            )
            expired.append(row)
    return expired


def list_approvals(status: str | None = "pending") -> list[dict]:
    expire_approvals()
    rows = []
    for path in approvals_dir().glob("apr-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if status and str(row.get("status") or "") != status:
            continue
        rows.append(row)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def decide_approval(approval_id: str, accept: bool, actor: str = "owner") -> dict:
    path = approvals_dir() / f"{approval_id}.json"
    if not path.is_file():
        raise ValueError("approval not found")
    row = json.loads(path.read_text(encoding="utf-8"))
    if str(row.get("status") or "") == "expired":
        raise ValueError("approval expired")
    if str(row.get("status") or "") != "pending":
        raise ValueError("approval not pending")
    row["status"] = "approved" if accept else "denied"
    row["decided_at"] = now_iso()
    row["actor"] = actor
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    append_action_log(
        {
            "id": row.get("job_id") or approval_id,
            "bot": row.get("project_id") or "staff",
            "engine": "board",
            "preset": "ops",
            "trigger": "needs-you",
            "status": row["status"],
            "gate": "approval",
            "approval": approval_id,
            "external": "none",
        }
    )
    return row


def connector_mode(name: str, tools: dict | None, project_id: str | None = None) -> str:
    """allow | ask | deny. Support never gets FUB/CRM keys."""
    key = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    if str(project_id or "") == "support" and any(bad.replace("-", "") in key or bad in (name or "").lower() for bad in DENIED_MCP):
        return "deny"
    if any(bad.replace("-", "") == key or bad == (name or "").lower() for bad in DENIED_MCP):
        if str(project_id or "") == "support":
            return "deny"
    blob = tools or {}
    connectors = blob.get("connectors") if isinstance(blob.get("connectors"), dict) else {}
    mcp = connectors.get("mcp") if isinstance(connectors.get("mcp"), dict) else {}
    row = mcp.get(name) or mcp.get(key) or {}
    if isinstance(row, dict) and row.get("mode") in {"allow", "ask", "deny"}:
        return str(row.get("mode"))
    return "ask" if IRREVERSIBLE.search(name or "") else "allow"


def eval_chip() -> dict:
    expire_approvals()
    pending = list_approvals("pending")
    expired = list_approvals("expired")
    return {
        "pending_approvals": len(pending),
        "expired_approvals": len(expired[:12]),
        "expired": expired[:8],
        "pending": pending[:8],
    }
