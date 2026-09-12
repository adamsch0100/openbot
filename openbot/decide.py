"""CEO proposals: why, review of last labor, discussion. Files, not chat."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .bus import ensure_bus
from .org import _slug, horizon_week, patch_scope, pulse_headline, read_project_index
from .store import clean_memory_text, list_jobs, now_iso

HEARTBEAT_MARK = "HEARTBEAT_TASK"
EVIDENCE_OK = frozenset({"verified", "inferred", "unknown"})
REVIEW_OK = frozenset({"implemented", "drifted", "failed", "none"})
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


def last_labor_review(project_id: str | None) -> dict:
    """Board-side audit of the last proposal vs jobs that followed. Not live GSC."""
    if not project_id:
        return {"review": "none", "note": "No CEO aimed."}
    pid = _slug(project_id)
    prop = load_last_proposal(pid)
    if not prop:
        return {"review": "none", "note": "No prior proposal to audit."}
    stamp = str(prop.get("at") or "")
    lane = _norm_lane(prop.get("lane"))
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    later = [
        job
        for job in jobs
        if str(job.get("project_id") or "") == pid
        and str(job.get("at") or "") >= stamp
        and str(job.get("preset") or "") not in {"cos", "ask", "think"}
        and HEARTBEAT_MARK not in str(job.get("message") or "")
        and str(job.get("id") or "") != str(prop.get("job_id") or "")
        and not job.get("talk")
    ]
    if not later:
        return {
            "review": "none",
            "note": "Proposal is open; no labor ran after it.",
            "proposal_next": str(prop.get("next") or ""),
        }
    failed = [
        job
        for job in later
        if job.get("blocker") or re.search(r"fail|error", str(job.get("status") or ""), re.I)
    ]
    if failed:
        why = str(failed[0].get("blocker") or failed[0].get("text") or "failed")[:160]
        return {"review": "failed", "note": why, "proposal_next": str(prop.get("next") or "")}
    preset = LANE_TO_PRESET.get(lane)
    matched = [job for job in later if str(job.get("preset") or "") == preset] if preset else []
    if lane in LANE_TO_PRESET and matched:
        return {
            "review": "implemented",
            "note": f"{lane} ran after the proposal.",
            "proposal_next": str(prop.get("next") or ""),
        }
    if later:
        return {
            "review": "drifted",
            "note": "Work ran after the proposal, but not the named lane.",
            "proposal_next": str(prop.get("next") or ""),
        }
    return {"review": "none", "note": "Waiting on labor.", "proposal_next": str(prop.get("next") or "")}


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
    """financial | code | research | ops | none. Pay and price are the same class: financial."""
    blob = prop if isinstance(prop, dict) else {}
    nxt = str(blob.get("next") or "")
    text = " ".join(str(blob.get(key) or "") for key in ("next", "why", "lane"))
    if FINANCIAL.search(text) or FINANCIAL.search(nxt):
        return "financial"
    lane = _norm_lane(blob.get("lane"))
    if lane in {"code", "research", "ops"}:
        return lane
    return "none"


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
    if _norm_evidence(prop.get("evidence")) == "unknown":
        return False, "evidence UNKNOWN — re-open the source"
    if _norm_review(prop.get("review")) in {"drifted", "failed"}:
        return False, "last labor did not implement the decision"
    if not _norm_auto(prop.get("auto")):
        return False, "proposal marked Auto: no"
    kind = classify_proposal(prop)
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
    prop = load_open_proposal(project_id)
    if prop and prop.get("status") == "open":
        lines.append("")
        lines.append("OPEN PROPOSAL (challenge this; do not ignore why):")
        lines.append(f"Why: {prop.get('why') or '—'}")
        lines.append(f"Horizon: {prop.get('horizon') or '—'}")
        lines.append(f"Evidence: {prop.get('evidence') or 'unknown'}")
        lines.append(f"Lane: {prop.get('lane') or 'none'} · Next: {prop.get('next') or '—'}")
        if prop.get("discuss"):
            lines.append(f"Discuss: {prop['discuss']}")
    try:
        from .org import project_tools

        policy = policy_for_tools(project_tools(project_id))
        bits = " ".join(f"{key}={policy[key]}" for key in POLICY_KEYS)
        lines.append("")
        lines.append(f"AUTO POLICY (operator-set, this CEO): {bits}")
        lines.append("Auto: yes only if this class is auto AND Evidence is not UNKNOWN AND Review is not drifted/failed.")
        lines.append("Financial includes pay, price, spend, and wallet. Publish, delete, and sign stay Accept-gated.")
    except Exception:
        pass
    if is_heartbeat_message(message):
        lines.append("")
        lines.append(
            "HEARTBEAT LAW: Audit last labor first. Then propose one next-best-action tied to Horizons. "
            "Output Why / Horizon / Evidence / Alternatives / Review / Lane / Next / Auto / Uncertainties / Discuss. "
            "Evidence UNKNOWN or Review drifted/failed ⇒ Auto: no. "
            "Honor AUTO POLICY. Financial = pay/price/spend. Publish, delete, sign stay parked. Do not write INDEX."
        )
        week = horizon_week(read_project_index(project_id))
        if week:
            lines.append(f"This week: {week}")
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
        f"{HEARTBEAT_MARK} Audit last labor against the open proposal, then propose "
        "the next-best-action from PULSE and Horizons. Output Why/Horizon/Evidence/"
        "Alternatives/Review/Lane/Next/Auto/Uncertainties/Discuss."
    )


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
    audit = last_labor_review(project_id)
    if not parsed.get("review"):
        parsed["review"] = audit.get("review") or "none"
    parsed["job_id"] = job_id
    blob = write_proposal(project_id, parsed)
    nxt = blob.get("next") or ""
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
    return msg, preset
