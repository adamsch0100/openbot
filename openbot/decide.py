"""CEO proposals: why, review of last labor, discussion. Files, not chat."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .bus import ensure_bus
from .org import _slug, horizon_week, index_field, patch_scope, pulse_headline, read_project_index
from .store import clean_memory_text, list_jobs, now_iso

HEARTBEAT_MARK = "HEARTBEAT_TASK"
EVIDENCE_OK = frozenset({"verified", "inferred", "unknown"})
REVIEW_OK = frozenset({"implemented", "drifted", "failed", "unproven", "none"})
SCAR_REVIEWS = frozenset({"failed", "drifted", "unproven"})
LANE_OK = frozenset({"code", "builder", "research", "ops", "none"})
LANE_TO_PRESET = {"code": "builder", "builder": "builder", "research": "research", "ops": "ops"}
POLICY_KEYS = ("code", "research", "ops", "financial")
# Recommended mix — operator can change any lane including pay (financial).
DEFAULT_AUTO_POLICY = {
    "code": "auto",
    "research": "auto",
    "ops": "notify",
    "financial": "notify",
}
# Pay, price, spend, wallet — one class. The Financial toggle owns all of these.
FINANCIAL = re.compile(
    r"\b(pay|paid|payment|price|pricing|invoice|spend|budget|wallet|billing|"
    r"stripe|refund|commission|revenue|p&l|pnl|purchase|payout|"
    r"subscription|mrr|wire money|payout)\b",
    re.I,
)
# Not money. Never auto even if every toggle is on.
ACCEPT_ONLY = re.compile(
    r"\b(publish|post|tweet|email|delete|sign\b|accept terms|"
    r"push(?:ed|ing)?(?:\s+to)?\s+(?:origin|remote|prod)|production|deploy)\b",
    re.I,
)
BUSYWORK = re.compile(
    r"\b(unit tests?|lint|refactor|prettier|coverage|typecheck|format the code)\b",
    re.I,
)
CLEAR_SCAR = re.compile(r"\b(clear scar|scar cleared|forgive|ignore (the )?fail)\b", re.I)
CODEISH = re.compile(
    r"\b(form|repo|patch|handler|cta|landing page|html|css|diff|commit)\b",
    re.I,
)
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "via",
        "not",
        "can",
        "take",
        "plus",
        "then",
        "into",
        "over",
        "after",
        "before",
        "week",
        "next",
        "open",
        "still",
        "need",
        "add",
        "our",
        "vs",
        "http",
        "https",
        "www",
        "one",
        "live",
        "page",
        "proof",
        "blocks",
        "ready",
        "desk",
        "none",
        "yes",
        "are",
        "was",
        "has",
        "have",
        "been",
    }
)

_LABELS = (
    "Why",
    "Horizon",
    "Evidence",
    "Alternatives",
    "Review",
    "Lane",
    "Next",
    "Auto",
    "Uncertainties",
    "Discuss",
    "Proof",
)


def _reviews_dir(project_id: str) -> Path:
    path = ensure_bus(project_id) / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def proposal_path(project_id: str | None) -> Path | None:
    if not project_id:
        return None
    return _reviews_dir(_slug(project_id)) / "proposal.json"


def archive_path(project_id: str) -> Path:
    return _reviews_dir(_slug(project_id)) / "last-proposal.json"


def scar_path(project_id: str) -> Path:
    return _reviews_dir(_slug(project_id)) / "scar.json"


def parked_path(project_id: str) -> Path:
    return _reviews_dir(_slug(project_id)) / "parked.json"


def notifies_path(project_id: str) -> Path:
    return _reviews_dir(_slug(project_id)) / "notifies.json"


def skip_note_path(project_id: str) -> Path:
    return _reviews_dir(_slug(project_id)) / "skip-note.txt"


def load_open_proposal(project_id: str | None) -> dict:
    path = proposal_path(project_id)
    if not path or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_last_proposal(project_id: str | None) -> dict:
    open_ = load_open_proposal(project_id)
    if open_:
        return open_
    if not project_id:
        return {}
    path = archive_path(_slug(project_id))
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_scar(project_id: str | None) -> dict:
    if not project_id:
        return {}
    path = scar_path(_slug(project_id))
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_scar(project_id: str, fields: dict) -> dict:
    pid = _slug(project_id)
    blob = {
        "review": _norm_review(fields.get("review")),
        "note": clean_memory_text(str(fields.get("note") or ""))[:240],
        "lane": _norm_lane(fields.get("lane")),
        "proposal_next": clean_memory_text(str(fields.get("proposal_next") or ""))[:280],
        "at": str(fields.get("at") or now_iso()),
        "proposal_id": str(fields.get("proposal_id") or ""),
    }
    scar_path(pid).write_text(json.dumps(blob, indent=2), encoding="utf-8")
    return blob


def clear_scar(project_id: str | None) -> None:
    if not project_id:
        return
    path = scar_path(_slug(project_id))
    if path.is_file():
        path.unlink()


def load_parked(project_id: str | None) -> list:
    if not project_id:
        return []
    path = parked_path(_slug(project_id))
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def park_proposal(project_id: str, prop: dict, reason: str = "parked") -> dict:
    pid = _slug(project_id)
    items = load_parked(pid)
    blob = dict(prop) if isinstance(prop, dict) else {}
    blob["parked_at"] = now_iso()
    blob["park_reason"] = str(reason or "parked")[:40]
    items.append(blob)
    parked_path(pid).write_text(json.dumps(items[-20:], indent=2), encoding="utf-8")
    return blob


def load_notifies(project_id: str | None) -> dict:
    if not project_id:
        return {}
    path = notifies_path(_slug(project_id))
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def bump_notify(project_id: str, kind: str, nxt: str) -> dict:
    pid = _slug(project_id)
    data = load_notifies(pid)
    key = str(kind or "none")
    row = data.get(key) if isinstance(data.get(key), dict) else {}
    try:
        count = int(row.get("count") or 0) + 1
    except (TypeError, ValueError):
        count = 1
    blob = {"next": clean_memory_text(nxt)[:160], "count": count, "last_at": now_iso()}
    data[key] = blob
    notifies_path(pid).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return blob


def notify_count(project_id: str | None, kind: str) -> int:
    row = load_notifies(project_id).get(str(kind or ""))
    if not isinstance(row, dict):
        return 0
    try:
        return int(row.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def load_skip_note(project_id: str | None) -> str:
    if not project_id:
        return ""
    path = skip_note_path(_slug(project_id))
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()[:240]
    except OSError:
        return ""


def write_proposal(project_id: str, fields: dict) -> dict:
    pid = _slug(project_id)
    ensure_bus(pid)
    blob = {
        "id": str(fields.get("id") or f"prop-{pid}-{now_iso().replace(':', '')[-8:]}"),
        "project_id": pid,
        "at": str(fields.get("at") or now_iso()),
        "status": str(fields.get("status") or "open"),
        "why": clean_memory_text(str(fields.get("why") or ""))[:400],
        "horizon": clean_memory_text(str(fields.get("horizon") or ""))[:240],
        "evidence": _norm_evidence(fields.get("evidence")),
        "alternatives": clean_memory_text(str(fields.get("alternatives") or ""))[:400],
        "review": _norm_review(fields.get("review")),
        "lane": _norm_lane(fields.get("lane")),
        "next": clean_memory_text(str(fields.get("next") or ""))[:280],
        "auto": _norm_auto(fields.get("auto")),
        "uncertainties": clean_memory_text(str(fields.get("uncertainties") or ""))[:280],
        "discuss": clean_memory_text(str(fields.get("discuss") or ""))[:280],
        "proof": clean_memory_text(str(fields.get("proof") or ""))[:240],
        "job_id": str(fields.get("job_id") or ""),
    }
    existing = load_open_proposal(pid)
    if existing and existing.get("id") != blob["id"]:
        archive_path(pid).write_text(json.dumps(existing, indent=2), encoding="utf-8")
    path = proposal_path(pid)
    path.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    return blob


def close_proposal(project_id: str, status: str, note: str = "") -> dict:
    pid = _slug(project_id)
    blob = load_open_proposal(pid)
    if not blob:
        return {}
    blob["status"] = str(status or "closed")[:40]
    blob["closed_at"] = now_iso()
    if note:
        blob["close_note"] = clean_memory_text(note)[:240]
        skip_note_path(pid).write_text(blob["close_note"], encoding="utf-8")
        if CLEAR_SCAR.search(note):
            clear_scar(pid)
    archive_path(pid).write_text(json.dumps(blob, indent=2), encoding="utf-8")
    path = proposal_path(pid)
    if path and path.is_file():
        path.unlink()
    return blob


def _norm_evidence(raw) -> str:
    val = str(raw or "unknown").strip().split()[0].lower()
    return val if val in EVIDENCE_OK else "unknown"


def _norm_review(raw) -> str:
    val = str(raw or "none").strip().split()[0].lower()
    return val if val in REVIEW_OK else "none"


def _norm_lane(raw) -> str:
    val = str(raw or "none").strip().split()[0].lower()
    if val in {"code", "builder"}:
        return "code"
    return val if val in LANE_OK else "none"


def _norm_auto(raw) -> bool:
    val = str(raw or "").strip().lower()
    return val in {"yes", "true", "1", "auto"}


def parse_proposal_from_text(text: str) -> dict:
    blob = text or ""
    out = {}
    for label in _LABELS:
        match = re.search(rf"^{re.escape(label)}:\s*(.*)$", blob, re.M | re.I)
        if match:
            out[label.lower()] = match.group(1).strip()
    return out


def is_heartbeat_message(message: str) -> bool:
    return HEARTBEAT_MARK in (message or "")


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    return {word for word in words if word not in _STOP}


def week_proof_text(week: str) -> str:
    blob = str(week or "").strip()
    match = re.search(r"\bproof\b[:\s]+(.+)$", blob, re.I)
    if match:
        return match.group(1).strip()
    return blob


def week_proof_tokens(week: str) -> set[str]:
    return _tokens(week_proof_text(week))


def _covers(have: set[str], need: set[str]) -> bool:
    if not need:
        return False
    if len(need) <= 3:
        return need <= have
    return len(need & have) >= min(2, len(need))


def proof_need(project_id: str | None, prop: dict | None) -> set[str]:
    blob = prop if isinstance(prop, dict) else {}
    explicit = _tokens(str(blob.get("proof") or ""))
    if explicit:
        return explicit
    week = ""
    if project_id:
        week = horizon_week(read_project_index(project_id))
    return week_proof_tokens(week)


def proof_ok(project_id: str | None, prop: dict | None, jobs: list | None) -> bool:
    need = proof_need(project_id, prop)
    lane = _norm_lane((prop or {}).get("lane") if isinstance(prop, dict) else "")
    later = jobs if isinstance(jobs, list) else []
    blob = " ".join(
        f"{job.get('text') or ''} {job.get('blocker') or ''}" for job in later if isinstance(job, dict)
    )
    have = _tokens(blob)
    if not need:
        return lane not in {"code", "research"}
    return _covers(have, need)


def horizon_line_satisfied(index: str, key: str, goal: str) -> bool:
    """True when Last/Now echo that horizon's proof tokens. Week also needs a live URL."""
    need = week_proof_tokens(goal)
    if not need:
        return False
    blob = f"{index_field(index, 'Now')} {index_field(index, 'Last')}"
    if not _covers(_tokens(blob), need):
        return False
    if str(key or "") == "week":
        return bool(re.search(r"https?://|\blive url\b", blob, re.I))
    return True


def horizon_satisfied(index: str) -> bool:
    """Week is done when Last/Now echo week-proof tokens and a live URL pointer."""
    week = horizon_week(index)
    return horizon_line_satisfied(index, "week", week)


def active_horizon(index: str) -> tuple[str, str, str]:
    """First unproven filled horizon (week → 5 years). Empty if the board is caught up."""
    from .org import HORIZON_KEYS, horizon_filled, parse_horizons

    parsed = parse_horizons(index or "")
    for key, label in HORIZON_KEYS:
        goal = str(parsed.get(key) or "").strip()
        if not horizon_filled(goal):
            continue
        if not horizon_line_satisfied(index, key, goal):
            return str(key), goal, str(label)
    return "", "", ""


def off_horizon(nxt: str, week: str) -> bool:
    if BUSYWORK.search(nxt or ""):
        return True
    week_tok = _tokens(week)
    next_tok = _tokens(nxt)
    if not week_tok or not next_tok:
        return False
    return not bool(next_tok & week_tok)


def _later_jobs(pid: str, prop: dict) -> list:
    stamp = str(prop.get("at") or "")
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    return [
        job
        for job in jobs
        if str(job.get("project_id") or "") == pid
        and str(job.get("at") or "") >= stamp
        and str(job.get("preset") or "") not in {"cos", "ask", "think"}
        and HEARTBEAT_MARK not in str(job.get("message") or "")
        and str(job.get("id") or "") != str(prop.get("job_id") or "")
        and not job.get("talk")
    ]


def _audit_jobs(pid: str, prop: dict) -> dict:
    lane = _norm_lane(prop.get("lane"))
    later = _later_jobs(pid, prop)
    nxt = str(prop.get("next") or "")
    base = {"proposal_next": nxt, "lane": lane, "proposal_id": str(prop.get("id") or "")}
    if not later:
        return {**base, "review": "none", "note": "Proposal is open; no labor ran after it."}
    failed = [
        job
        for job in later
        if job.get("blocker") or re.search(r"fail|error", str(job.get("status") or ""), re.I)
    ]
    if failed:
        why = str(failed[0].get("blocker") or failed[0].get("text") or "failed")[:160]
        return {**base, "review": "failed", "note": why}
    preset = LANE_TO_PRESET.get(lane)
    matched = [job for job in later if str(job.get("preset") or "") == preset] if preset else []
    if lane in LANE_TO_PRESET and matched:
        if proof_ok(pid, prop, matched):
            return {**base, "review": "implemented", "note": f"{lane} ran after the proposal with proof."}
        return {
            **base,
            "review": "unproven",
            "note": "Matching lane ran, but RESULT did not echo Proof / week proof.",
        }
    if later:
        return {
            **base,
            "review": "drifted",
            "note": "Work ran after the proposal, but not the named lane.",
        }
    return {**base, "review": "none", "note": "Waiting on labor."}


def last_labor_review(project_id: str | None) -> dict:
    """Board-side audit of last labor vs proof. Scar survives a new Think. Not live GSC."""
    if not project_id:
        return {"review": "none", "note": "No CEO aimed."}
    pid = _slug(project_id)
    prop = load_last_proposal(pid)
    scar = load_scar(pid)
    if prop:
        result = _audit_jobs(pid, prop)
        if result.get("review") in SCAR_REVIEWS:
            write_scar(pid, result)
            return result
        if result.get("review") == "implemented":
            clear_scar(pid)
            return result
        if scar.get("review") in SCAR_REVIEWS:
            return {**scar, "inherited": True, "note": str(scar.get("note") or "Scar still open.")}
        return result
    if scar.get("review") in SCAR_REVIEWS:
        return {**scar, "inherited": True}
    return {"review": "none", "note": "No prior proposal to audit."}


def _mode(raw) -> str:
    val = str(raw or "").strip().lower()
    if val in {"auto", "yes", "true", "1", "on"}:
        return "auto"
    return "notify"


def normalize_auto_policy(raw, *, legacy_auto_labor: bool = False) -> dict:
    """Per-lane auto|notify. Saved policy wins. Else legacy pin, else all notify until Save."""
    out = {key: "notify" for key in POLICY_KEYS}
    if isinstance(raw, dict) and any(key in raw for key in POLICY_KEYS):
        for key in POLICY_KEYS:
            if key in raw:
                out[key] = _mode(raw.get(key))
        return out
    if legacy_auto_labor:
        out["code"] = "auto"
        out["research"] = "auto"
    return out


def recommended_auto_policy() -> dict:
    return dict(DEFAULT_AUTO_POLICY)


def policy_for_tools(tools: dict | None) -> dict:
    """Enforced policy. Unset → all notify until Save or Attach seeds a choice."""
    blob = tools if isinstance(tools, dict) else {}
    if blob.get("auto_policy_set"):
        return normalize_auto_policy(blob.get("auto_policy"), legacy_auto_labor=bool(blob.get("auto_labor")))
    return normalize_auto_policy(None, legacy_auto_labor=bool(blob.get("auto_labor")))


def classify_proposal(prop: dict | None) -> str:
    """financial | code | research | ops | none. Next first; Why only if Next is empty."""
    blob = prop if isinstance(prop, dict) else {}
    nxt = str(blob.get("next") or "")
    lane = _norm_lane(blob.get("lane"))
    if nxt.strip():
        if FINANCIAL.search(nxt):
            return "financial"
        if lane in {"code", "research", "ops"}:
            return lane
        return "none"
    why = str(blob.get("why") or "")
    if FINANCIAL.search(why):
        return "financial"
    if lane in {"code", "research", "ops"}:
        return lane
    return "none"


def proposal_conflict(prop: dict | None) -> bool:
    blob = prop if isinstance(prop, dict) else {}
    nxt = str(blob.get("next") or "")
    lane = _norm_lane(blob.get("lane"))
    if not nxt.strip() or ACCEPT_ONLY.search(nxt):
        return False
    if lane == "ops" and CODEISH.search(nxt) and not FINANCIAL.search(nxt):
        return True
    if lane in {"code", "research"} and FINANCIAL.search(nxt) is None:
        other = "research" if lane == "code" else "code"
        if other == "research" and re.search(r"\b(research note|search demand)\b", nxt, re.I) and lane == "code":
            return True
    return False


def auto_labor_allowed(project_id: str | None, proposal: dict | None = None) -> tuple[bool, str]:
    """Operator policy + intelligence gates. Publish/delete/sign never auto. Pay follows Financial."""
    if not project_id:
        return False, "no CEO"
    from .org import project_tools

    tools = project_tools(project_id)
    policy = policy_for_tools(tools)
    prop = proposal if isinstance(proposal, dict) and proposal else load_open_proposal(project_id)
    if not prop:
        return False, "no open proposal"
    nxt = str(prop.get("next") or "")
    if not nxt.strip():
        return False, "Next is empty"
    if ACCEPT_ONLY.search(nxt):
        return False, "Next is publish/delete/sign — Accept gate"
    index = read_project_index(project_id)
    key, goal, _label = active_horizon(index)
    if not key and horizon_satisfied(index):
        return False, "week already proven"
    if not goal:
        goal = horizon_week(index)
    kind = classify_proposal(prop)
    if kind in {"code", "research"} and off_horizon(nxt, goal):
        return False, "off_horizon"
    if proposal_conflict(prop):
        return False, "lane and Next disagree — notify"
    if _norm_evidence(prop.get("evidence")) == "unknown":
        return False, "evidence UNKNOWN — re-open the source"
    scar = load_scar(project_id)
    review = _norm_review(prop.get("review"))
    if scar.get("review") in SCAR_REVIEWS:
        scar_lane = _norm_lane(scar.get("lane"))
        prop_lane = _norm_lane(prop.get("lane"))
        if not scar_lane or scar_lane == prop_lane:
            return False, "last labor did not implement the decision"
    if review in SCAR_REVIEWS:
        return False, "last labor did not implement the decision"
    if not _norm_auto(prop.get("auto")):
        return False, "proposal marked Auto: no"
    if kind == "none":
        return False, "lane is not labor"
    if policy.get(kind) != "auto":
        return False, f"{kind} is set to notify"
    return True, "ok"


def prove_decision_loop(project_id: str, result: str) -> dict:
    """Compressed loop: labeled Think RESULT → proposal → auto vs notify. No engines."""
    decided = ingest_think_result(
        project_id,
        f"{HEARTBEAT_MARK} prove loop",
        result,
        job_id="prove",
    )
    prop = decided.get("proposal") or {}
    allowed, reason = auto_labor_allowed(project_id, prop)
    msg, preset = labor_prompt(project_id) if allowed else ("", "")
    from .org import project_tools

    return {
        "status": decided.get("status") or "",
        "class": classify_proposal(prop),
        "allowed": allowed,
        "reason": reason,
        "preset": preset,
        "message": msg,
        "proposal": prop,
        "policy": policy_for_tools(project_tools(project_id)),
    }


def proposal_packet_extra(project_id: str | None, message: str = "") -> str:
    if not project_id:
        return ""
    lines = []
    audit = last_labor_review(project_id)
    lines.append("LAST LABOR REVIEW (board files, not chat):")
    lines.append(f"Review: {audit.get('review') or 'none'}")
    if audit.get("note"):
        lines.append(f"Note: {audit['note']}")
    if audit.get("proposal_next"):
        lines.append(f"Prior Next: {audit['proposal_next']}")
    if audit.get("inherited"):
        lines.append("Scar inherited: a new Think does not wipe failed/drifted/unproven labor.")
    scar = load_scar(project_id)
    if scar.get("review") in SCAR_REVIEWS:
        lines.append("")
        lines.append(f"SCAR: {scar.get('review')} — {str(scar.get('note') or '')[:160]}")
        lines.append("Scar stays until matching lane echoes Proof, or Skip note clears it.")
    parked = load_parked(project_id)
    if parked:
        last = parked[-1]
        lines.append("")
        lines.append(
            f"PARKED: {len(parked)} held — last {last.get('park_reason') or 'parked'}: "
            f"{str(last.get('next') or '')[:120]}"
        )
    notes = load_notifies(project_id)
    repeats = [f"{key} x{int((row or {}).get('count') or 0)}" for key, row in notes.items() if int((row or {}).get("count") or 0) >= 2]
    if repeats:
        lines.append(f"REPEAT: {', '.join(repeats)}")
    skip = load_skip_note(project_id)
    if skip:
        lines.append(f"SKIP NOTE: {skip}")
    week = horizon_week(read_project_index(project_id))
    proof = week_proof_text(week)
    if proof:
        lines.append(f"WEEK PROOF: {proof[:160]}")
    prop = load_open_proposal(project_id)
    if prop and prop.get("status") == "open":
        lines.append("")
        lines.append("OPEN PROPOSAL (challenge this; do not ignore why):")
        lines.append(f"Why: {prop.get('why') or '—'}")
        lines.append(f"Horizon: {prop.get('horizon') or '—'}")
        lines.append(f"Evidence: {prop.get('evidence') or 'unknown'}")
        lines.append(f"Lane: {prop.get('lane') or 'none'} · Next: {prop.get('next') or '—'}")
        if prop.get("proof"):
            lines.append(f"Proof: {prop.get('proof')}")
        if prop.get("discuss"):
            lines.append(f"Discuss: {prop['discuss']}")
    try:
        from .org import project_tools

        policy = policy_for_tools(project_tools(project_id))
        bits = " ".join(f"{key}={policy[key]}" for key in POLICY_KEYS)
        lines.append("")
        lines.append(f"AUTO POLICY (operator-set, this CEO): {bits}")
        lines.append(
            "Auto: yes only if this class is auto AND Evidence is not UNKNOWN AND "
            "Review/Scar is not drifted/failed/unproven AND Next serves Horizon-week."
        )
        lines.append("Financial includes pay, price, spend, and wallet. Publish, delete, and sign stay Accept-gated.")
        lines.append("Classify from Next, not Why. Week already proven or off_horizon ⇒ Auto: no.")
    except Exception:
        pass
    if is_heartbeat_message(message):
        lines.append("")
        lines.append(
            "HEARTBEAT LAW: Audit SCAR and last labor first. Then propose one next-best-action tied to Horizons. "
            "Output Why / Horizon / Evidence / Alternatives / Review / Lane / Next / Auto / Uncertainties / Discuss / Proof. "
            "Evidence UNKNOWN or Review/Scar drifted/failed/unproven ⇒ Auto: no. "
            "If this horizon's proof is already on INDEX Last/Now, climb to the next unproven Horizon "
            "(month, then quarter, then 6 months / year / 5 years). If all are proven, Next is wait — do not invent busywork. "
            "Honor AUTO POLICY. Financial = pay/price/spend. Publish, delete, sign get parked (free the open slot). "
            "Do not write INDEX."
        )
        key, goal, label = active_horizon(read_project_index(project_id))
        if key:
            lines.append(f"Active horizon ({label}): {goal}")
        if week:
            lines.append(f"This week: {week}")
        try:
            from .org import HORIZON_KEYS, horizon_filled, parse_horizons

            parsed = parse_horizons(read_project_index(project_id))
            filled = [
                f"{label}: {parsed[item]}"
                for item, label in HORIZON_KEYS
                if horizon_filled(str(parsed.get(item) or ""))
            ]
            if filled:
                lines.append("HORIZONS: " + " · ".join(filled)[:800])
        except Exception:
            pass
        sched = ""
        try:
            sched = pulse_headline(project_id)
        except Exception:
            sched = ""
        if sched:
            lines.append(f"Schedule: {sched}")
    return "\n".join(lines).strip()


def heartbeat_step_instruction() -> str:
    """One line for the routine file. Full law lives in the skill + packet extra."""
    return (
        f"{HEARTBEAT_MARK} Audit scar and last labor against Proof, then propose "
        "the next-best-action from PULSE and Horizons. Output Why/Horizon/Evidence/"
        "Alternatives/Review/Lane/Next/Auto/Uncertainties/Discuss/Proof. "
        "Serve the first unproven Horizon (week, then month, then longer). "
        "Stop only if every filled Horizon is proven. Classify from Next."
    )


def _archive_open_if_held(project_id: str, tools: dict | None) -> None:
    existing = load_open_proposal(project_id)
    if not existing:
        return
    nxt = str(existing.get("next") or "")
    kind = classify_proposal(existing)
    policy = policy_for_tools(tools)
    if ACCEPT_ONLY.search(nxt):
        park_proposal(project_id, existing, "accept")
        close_proposal(project_id, "parked")
        return
    if kind in POLICY_KEYS and policy.get(kind) != "auto":
        park_proposal(project_id, existing, "notify")
        bump_notify(project_id, kind, nxt)
        close_proposal(project_id, "archived-notify")


def ingest_think_result(project_id: str | None, message: str, result: str, job_id: str = "") -> dict:
    """Turn a Think RESULT into an open proposal when it is a heartbeat or labeled decision."""
    if not project_id:
        return {}
    if "FOUNDING_TASK" in (message or ""):
        return {}
    parsed = parse_proposal_from_text(result or "")
    labeled = bool(parsed.get("why") and parsed.get("next"))
    if not labeled:
        return {}
    from .org import project_tools

    tools = project_tools(project_id)
    audit = last_labor_review(project_id)
    scar_lane = _norm_lane(audit.get("lane") or load_scar(project_id).get("lane"))
    new_lane = _norm_lane(parsed.get("lane"))
    if audit.get("review") in SCAR_REVIEWS and (not scar_lane or scar_lane == new_lane):
        parsed["review"] = audit.get("review")
    elif _norm_review(parsed.get("review")) in SCAR_REVIEWS and scar_lane and scar_lane != new_lane:
        parsed["review"] = "none"
    elif not parsed.get("review"):
        parsed["review"] = audit.get("review") or "none"
    parsed["job_id"] = job_id
    _archive_open_if_held(project_id, tools)
    blob = write_proposal(project_id, parsed)
    nxt = blob.get("next") or ""
    kind = classify_proposal(blob)
    policy = policy_for_tools(tools)
    if ACCEPT_ONLY.search(nxt):
        parked = park_proposal(project_id, blob, "accept")
        closed = close_proposal(project_id, "parked")
        patch_scope(project_id, None, "Next", f"Parked Accept: {nxt[:140]}")
        patch_scope(project_id, None, "Now", "Accept-gated Next parked — open slot free")
        return {"status": "parked", "proposal": closed or parked}
    if kind in POLICY_KEYS and policy.get(kind) != "auto":
        bump_notify(project_id, kind, nxt)
    if nxt:
        patch_scope(project_id, None, "Next", nxt[:160])
        patch_scope(project_id, None, "Now", "Proposal open — Do it / Ask Cos / Ask me")
    return {"status": "proposal", "proposal": blob}


def discuss_prompt(project_id: str | None, who: str = "operator") -> str:
    """A follow-up question that keeps the proposal in the next packet."""
    prop = load_open_proposal(project_id)
    if not prop:
        return ""
    why = prop.get("why") or "—"
    nxt = prop.get("next") or "—"
    ask = prop.get("discuss") or "What would make this the wrong move?"
    if who == "cos":
        return (
            f"Ask Cos: this CEO proposed Next: {nxt} because {why}. "
            f"Challenge it: {ask} Route Code/Think/Research/Ops or escalate to Adam only for "
            "keys, money, login, publish, pay, delete, sign."
        )
    return (
        f"Challenge this proposal before labor. Why: {why}. Next: {nxt}. "
        f"{ask} Keep the open proposal; do not invent a new board."
    )


def labor_prompt(project_id: str | None) -> tuple[str, str]:
    """Message + preset to execute the open proposal's lane."""
    prop = load_open_proposal(project_id)
    if not prop:
        return "", ""
    lane = _norm_lane(prop.get("lane"))
    preset = LANE_TO_PRESET.get(lane, "")
    nxt = str(prop.get("next") or "").strip()
    why = str(prop.get("why") or "").strip()
    if not preset or not nxt:
        return "", ""
    msg = f"Do the open proposal. Why: {why}. Task: {nxt}"
    proof = str(prop.get("proof") or "").strip()
    if proof:
        msg += f" Proof: {proof}"
    return msg, preset
