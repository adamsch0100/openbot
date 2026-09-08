"""Support tickets: suggestions, status, handoff to Builder. Files, not chat."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .bus import create_handoff, write_draft
from .store import ROOT, now_iso

ORG = ROOT / "org"
SUPPORT_ID = "support"
FIX_PROJECT_ID = "openbot"
PHASES = ("received", "triage", "building", "in_review", "shipped", "wontfix")
OPEN_PHASES = ("received", "triage", "building", "in_review")
FAQ = re.compile(r"\b(how do i|how to|where is|what is|help me|onboarding)\b", re.I)
BUG = re.compile(r"\b(bug|broken|error|crash|fix|fail(?:ed|ing)?|regression)\b", re.I)
FEATURE = re.compile(r"\b(add|feature|wish|could you|would be nice|enhancement|suggest)\b", re.I)
SPAM = re.compile(r"\b(crypto airdrop|buy followers|seo backlinks cheap)\b", re.I)


def tickets_dir() -> Path:
    path = ORG / "projects" / SUPPORT_ID / "tickets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ticket_path(ticket_id: str) -> Path:
    return tickets_dir() / f"{ticket_id}.json"


def classify_kind(text: str) -> str:
    blob = text or ""
    if SPAM.search(blob):
        return "spam"
    if FAQ.search(blob):
        return "faq"
    if BUG.search(blob):
        return "bug"
    if FEATURE.search(blob):
        return "feature"
    return "triage"


def _write(ticket: dict) -> dict:
    ticket["updated_at"] = now_iso()
    path = ticket_path(str(ticket["id"]))
    path.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
    _sync_support_index()
    return ticket


def read_ticket(ticket_id: str) -> dict | None:
    path = ticket_path(ticket_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_tickets(*, phases: tuple[str, ...] | None = None, limit: int = 40) -> list[dict]:
    rows = []
    for path in tickets_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("id"):
            continue
        if phases and str(data.get("phase") or "") not in phases:
            continue
        rows.append(data)
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return rows[:limit]


def create_ticket(
    title: str,
    body: str,
    *,
    source: str = "suggest",
    author: str = "",
    url: str = "",
    auto_route: bool = True,
) -> dict:
    title = (title or "").strip()[:200] or (body or "").strip()[:80] or "Suggestion"
    body = (body or "").strip()[:8000]
    if not body:
        raise ValueError("body required")
    ticket_id = f"sug-{uuid.uuid4().hex[:10]}"
    kind = classify_kind(f"{title}\n{body}")
    phase = "received"
    if kind == "spam":
        phase = "wontfix"
    elif kind == "faq":
        phase = "triage"
    ticket = {
        "id": ticket_id,
        "phase": phase,
        "kind": kind,
        "source": source,
        "title": title,
        "body": body,
        "author": (author or "").strip()[:120],
        "url": (url or "").strip()[:400],
        "project_id": SUPPORT_ID,
        "fix_project_id": FIX_PROJECT_ID,
        "handoff_id": "",
        "job_id": "",
        "diff_job_id": "",
        "draft_id": "",
        "engine": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "now": f"Received · {kind}",
        "last": f"Ingested from {source}",
        "next": "Triage",
    }
    _write(ticket)
    if auto_route and kind in {"bug", "feature"}:
        route_to_builder(ticket_id)
        ticket = read_ticket(ticket_id) or ticket
    elif auto_route and kind == "faq":
        draft_faq_reply(ticket_id)
        ticket = read_ticket(ticket_id) or ticket
    return ticket


def update_ticket(ticket_id: str, **fields) -> dict:
    ticket = read_ticket(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    phase = fields.get("phase")
    if phase and phase not in PHASES:
        raise ValueError("invalid phase")
    for key, value in fields.items():
        if key == "id":
            continue
        ticket[key] = value
    if phase:
        ticket["now"] = f"{phase} · {ticket.get('kind') or 'ticket'}"
        ticket["last"] = f"Phase → {phase}"
        if phase == "building":
            ticket["next"] = "Builder diff, then In review"
        elif phase == "in_review":
            ticket["next"] = "Owner Accept / Reject"
        elif phase == "shipped":
            ticket["next"] = "Optional announce draft"
        elif phase == "wontfix":
            ticket["next"] = "—"
        elif phase == "triage":
            ticket["next"] = "Classify and schedule"
    return _write(ticket)


def route_to_builder(ticket_id: str) -> dict:
    ticket = read_ticket(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    task = (
        f"Support ticket {ticket_id}: {ticket.get('title')}\n\n"
        f"{ticket.get('body')}\n\n"
        "Implement in the openbot repo. Produce a local diff. Do not push. "
        "Do not Accept. Wait for the operator gate."
    )
    result = create_handoff(
        task=task,
        project_id=FIX_PROJECT_ID,
        from_seat="support",
        to_seat="builder",
        next_owner="builder",
        output=f"ticket:{ticket_id}",
    )
    if not result.get("ok"):
        raise ValueError(result.get("message") or "handoff failed")
    return update_ticket(
        ticket_id,
        phase="building",
        handoff_id=result.get("handoff_id") or "",
        kind=ticket.get("kind") if ticket.get("kind") in {"bug", "feature"} else "bug",
        next="openbot Builder claims handoff",
    )


def draft_faq_reply(ticket_id: str) -> dict:
    ticket = read_ticket(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    body = (
        f"# Draft reply · {ticket_id}\n\n"
        f"Question: {ticket.get('title')}\n\n"
        f"{ticket.get('body')}\n\n"
        "---\n\n"
        "Proposed reply (unsent):\n"
        "Thanks for writing. Support triaged this as a how-to. "
        "A human still approves anything that leaves the board.\n"
    )
    draft = write_draft(
        kind="reply",
        body=body,
        project_id=SUPPORT_ID,
        ticket_id=ticket_id,
        title=f"Reply · {ticket.get('title')}",
    )
    return update_ticket(
        ticket_id,
        phase="triage",
        draft_id=str(draft.get("id") or ""),
        next="Owner approves the reply draft",
    )


def draft_announce(ticket_id: str) -> dict:
    ticket = read_ticket(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    body = (
        f"# Announce draft · {ticket_id}\n\n"
        f"Shipped: {ticket.get('title')}\n\n"
        "Unsent X / changelog copy:\n"
        f"OpenBot shipped a suggestion: {ticket.get('title')}. "
        "Review the diff on the board before anything posts.\n"
    )
    draft = write_draft(
        kind="announce",
        body=body,
        project_id=SUPPORT_ID,
        ticket_id=ticket_id,
        title=f"Announce · {ticket.get('title')}",
    )
    return update_ticket(ticket_id, draft_id=str(draft.get("id") or ""), next="Owner approves announce")


def on_job_linked(ticket_id: str, job: dict) -> dict | None:
    ticket = read_ticket(ticket_id)
    if not ticket:
        return None
    fields = {
        "job_id": str(job.get("id") or ticket.get("job_id") or ""),
        "engine": str(job.get("engine") or ticket.get("engine") or ""),
    }
    if job.get("diff_pending"):
        fields["phase"] = "in_review"
        fields["diff_job_id"] = str(job.get("id") or "")
    elif job.get("blocker"):
        fields["phase"] = "triage"
        fields["next"] = "Blocked — needs owner"
        fields["kind"] = "needs-owner"
    return update_ticket(ticket_id, **fields)


def on_diff_decided(job: dict, accepted: bool) -> dict | None:
    job_id = str(job.get("id") or "")
    ticket = None
    for row in list_tickets(limit=80):
        if str(row.get("diff_job_id") or "") == job_id or str(row.get("job_id") or "") == job_id:
            ticket = row
            break
        hid = str(row.get("handoff_id") or "")
        if hid and hid in str(job.get("message") or "") + str(job.get("handoff_path") or ""):
            ticket = row
            break
    if not ticket:
        return None
    if accepted:
        updated = update_ticket(ticket["id"], phase="shipped", last=f"Accepted {job_id}")
        try:
            draft_announce(ticket["id"])
            updated = read_ticket(ticket["id"]) or updated
        except ValueError:
            pass
        return updated
    return update_ticket(ticket["id"], phase="wontfix", last=f"Rejected {job_id}")


def find_ticket_for_handoff(handoff_id: str) -> dict | None:
    for row in list_tickets(limit=80):
        if str(row.get("handoff_id") or "") == handoff_id:
            return row
    return None


def working_on(limit: int = 20) -> dict:
    open_rows = list_tickets(phases=OPEN_PHASES, limit=limit)
    recent = list_tickets(limit=limit)
    expired = []
    try:
        from .bus import list_approvals

        expired = [row for row in list_approvals(status="expired")[:8]]
    except Exception:
        expired = []
    return {
        "open": open_rows,
        "recent": recent,
        "expired_approvals": expired,
        "counts": {
            phase: sum(1 for row in recent if row.get("phase") == phase)
            for phase in PHASES
        },
    }


def _sync_support_index() -> None:
    from .org import write_project_index, index_field, read_project_index

    open_rows = list_tickets(phases=OPEN_PHASES, limit=8)
    if not open_rows:
        now = "Ready for suggestions and help tickets."
        nxt = "Triage inbox tickets."
    else:
        top = open_rows[0]
        now = f"{top.get('id')} · {top.get('phase')} · {top.get('title')}"
        nxt = str(top.get("next") or "Continue ticket")
    text = read_project_index(SUPPORT_ID)
    if not text:
        return
    write_project_index(
        SUPPORT_ID,
        _patch_four(text, Now=now[:200], Next=nxt[:200], Last=index_field(text, "Last") or "—"),
    )


def _patch_four(text: str, **fields: str) -> str:
    out = text
    for label, value in fields.items():
        pattern = re.compile(rf"^{label}:\s*.*$", re.M)
        if pattern.search(out):
            out = pattern.sub(f"{label}: {value}", out, count=1)
        else:
            out = f"{label}: {value}\n" + out
    return out


def _x_token() -> str:
    for name in ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN", "X_API_BEARER"):
        val = str(os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def ingest_x_mentions(*, username: str = "") -> dict:
    """Pull X mentions into tickets. Fail closed if credentials or API are missing."""
    from .config import load_settings

    settings = load_settings()
    if not settings.get("x_intake_enabled"):
        return {"ok": False, "reason": "x intake off", "created": []}
    token = _x_token()
    if not token:
        return {"ok": False, "reason": "x credentials missing", "created": []}
    user = (username or str(settings.get("x_username") or "")).strip().lstrip("@")
    if not user:
        return {"ok": False, "reason": "x username missing", "created": []}
    try:
        user_req = Request(
            f"https://api.twitter.com/2/users/by/username/{user}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(user_req, timeout=12) as res:
            user_payload = json.loads(res.read().decode("utf-8"))
        user_id = str((user_payload.get("data") or {}).get("id") or "")
        if not user_id:
            return {"ok": False, "reason": "x user not found", "created": []}
        mention_req = Request(
            f"https://api.twitter.com/2/users/{user_id}/mentions?max_results=10&tweet.fields=author_id,created_at,text",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(mention_req, timeout=12) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as err:
        return {"ok": False, "reason": f"x fetch failed: {err}", "created": []}
    created = []
    seen = {str(row.get("url") or "") for row in list_tickets(limit=80)}
    for tweet in payload.get("data") or []:
        if not isinstance(tweet, dict):
            continue
        tid = str(tweet.get("id") or "")
        text = str(tweet.get("text") or "").strip()
        url = f"https://x.com/i/status/{tid}" if tid else ""
        if not text or (url and url in seen):
            continue
        ticket = create_ticket(
            title=text[:80],
            body=text,
            source="x",
            author=str(tweet.get("author_id") or ""),
            url=url,
            auto_route=True,
        )
        created.append(ticket["id"])
        seen.add(url)
    return {"ok": True, "reason": "", "created": created}


def public_ticket(row: dict | None) -> dict:
    if not row:
        return {}
    return {
        "id": row.get("id"),
        "phase": row.get("phase"),
        "kind": row.get("kind"),
        "source": row.get("source"),
        "title": row.get("title"),
        "body": row.get("body"),
        "author": row.get("author"),
        "url": row.get("url"),
        "handoff_id": row.get("handoff_id"),
        "job_id": row.get("job_id"),
        "diff_job_id": row.get("diff_job_id"),
        "draft_id": row.get("draft_id"),
        "engine": row.get("engine"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "now": row.get("now"),
        "last": row.get("last"),
        "next": row.get("next"),
    }
