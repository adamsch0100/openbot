"""Process control law: verifier, stores, retry≠round, single writer, effect keys.

Inspired by outer-loop / inner-worker control systems. OttoBot stays a thin board:
files are memory, engines are rented, chat is never the database.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

from .store import ROOT, clean_memory_text, now_iso

_WRITE_LOCK = threading.RLock()

PULSE_LABELS = ("Now", "Last", "Next", "Blocker")
MAX_ROUNDS = 3

VERIFY_RE = re.compile(
    r"^VERIFY:\s*(pass|fail|pending)\b(?:\s*[—\-:]\s*(.*))?$",
    re.I | re.M,
)
PROOF_RE = re.compile(r"^PROOF:\s*(.+)$", re.I | re.M)
ACCEPTANCE_RE = re.compile(r"^ACCEPTANCE:\s*(.+)$", re.I | re.M)
TRANSIENT_HINT = re.compile(
    r"\b(timeout|timed out|rate limit|429|502|503|504|connection|network|"
    r"unreachable|temporarily unavailable|gateway)\b",
    re.I,
)

PROCESS_LAW = (
    "PROCESS LAW (board control — not a third engine):\n"
    "1. LOOP: owner (Cos/board) → worker (OpenCode/Hermes) → verifier → stop rule. "
    f"Cap {MAX_ROUNDS} rounds unless the operator extends.\n"
    "2. VERIFY before done: end RESULT with VERIFY: pass|fail|pending — reason "
    "and PROOF: <check or URL>. Builder diffs wait for human Accept as verifier.\n"
    "3. STORES stay split: pulse (Now/Last/Next/Blocker) ≠ doctrine (law/Horizons) "
    "≠ run_state (attempts/readiness). Do not dump chat into INDEX.\n"
    "4. RETRY ≠ ROUND: transport/rate-limit retries keep the same round_key. "
    "A new round needs new verifier evidence or a new operator task.\n"
    "5. SINGLE WRITER: propose INDEX patches to bus/index_inbox; the board commits. "
    "Engines do not race-write authoritative INDEX.\n"
    "6. EFFECT KEYS: before pay/publish/delete/sign/push, claim an effect_key, "
    "execute once, store receipt, then mark done. On resume, reconcile claimed effects first.\n"
    "7. NESTED HARNESS GAP: Accepting a board job does not approve every inner tool call "
    "inside OpenCode/Hermes. Outer Accept + inner allowlists/MCP off-by-default still apply.\n"
    "8. START THIN: one worker loop before swarm/DAG chrome. Folder → change → diff → INDEX first."
)


def process_law_block() -> str:
    return PROCESS_LAW


def result_trailer() -> str:
    return (
        "End specialist RESULT with:\n"
        "VERIFY: pass|fail|pending — <one-line reason>\n"
        "PROOF: <check, path, or URL>\n"
        "Park pay/publish/delete/sign. Name the engine."
    )


def round_key(project_id: str | None, task: str, *, salt: str = "") -> str:
    basis = f"{project_id or 'staff'}::{clean_memory_text(task or '').strip().lower()}::{salt}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def effect_key(kind: str, project_id: str | None, payload: str) -> str:
    basis = f"{kind}::{project_id or 'staff'}::{clean_memory_text(payload or '').strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def parse_verifier(result: str) -> dict[str, Any]:
    """Extract VERIFY / PROOF / ACCEPTANCE lines from a RESULT body."""
    blob = result or ""
    verify = VERIFY_RE.search(blob)
    proof = PROOF_RE.search(blob)
    acceptance = ACCEPTANCE_RE.search(blob)
    status = (verify.group(1).lower() if verify else "") or "pending"
    reason = (verify.group(2) or "").strip() if verify else ""
    return {
        "status": status,
        "reason": clean_memory_text(reason)[:240],
        "proof": clean_memory_text(proof.group(1) if proof else "")[:400],
        "acceptance": clean_memory_text(acceptance.group(1) if acceptance else "")[:400],
        "stated": bool(verify),
    }


def is_transient_text(text: str) -> bool:
    return bool(TRANSIENT_HINT.search(text or ""))


def attempt_kind(*, transient: bool, new_evidence: bool) -> str:
    """retry keeps the round; round advances only with new verifier evidence or new task."""
    if transient and not new_evidence:
        return "retry"
    return "round"


def split_index_stores(text: str) -> dict[str, str]:
    """Pulse four-liners vs doctrine body. Run state lives in JSON, not markdown."""
    blob = text or ""
    pulse_lines: list[str] = []
    other: list[str] = []
    for line in blob.splitlines():
        if re.match(r"^(Now|Last|Next|Blocker):\s*", line):
            pulse_lines.append(line)
        else:
            other.append(line)
    return {
        "pulse": "\n".join(pulse_lines).strip(),
        "doctrine": "\n".join(other).strip(),
    }


def _project_bus(project_id: str | None) -> Path:
    from .bus import ensure_bus

    return ensure_bus(project_id)


def run_state_path(project_id: str | None) -> Path:
    return _project_bus(project_id) / "run_state.json"


def load_run_state(project_id: str | None) -> dict[str, Any]:
    path = run_state_path(project_id)
    if not path.is_file():
        return {"rounds": {}, "open_round": "", "updated_at": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"rounds": {}, "open_round": "", "updated_at": ""}
    return data if isinstance(data, dict) else {"rounds": {}, "open_round": "", "updated_at": ""}


def save_run_state(project_id: str | None, state: dict[str, Any]) -> dict[str, Any]:
    path = run_state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(state or {})
    blob["updated_at"] = now_iso()
    with _WRITE_LOCK:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        tmp.replace(path)
    return blob


def record_attempt(
    project_id: str | None,
    *,
    round_id: str,
    job_id: str,
    kind: str,
    transient: bool = False,
    verify: dict | None = None,
) -> dict[str, Any]:
    state = load_run_state(project_id)
    rounds = state.setdefault("rounds", {})
    row = rounds.get(round_id) if isinstance(rounds.get(round_id), dict) else {}
    attempts = list(row.get("attempts") or [])
    attempts.append(
        {
            "at": now_iso(),
            "job_id": job_id,
            "kind": kind if kind in {"retry", "round"} else "round",
            "transient": bool(transient),
            "verify": (verify or {}).get("status") if isinstance(verify, dict) else "",
        }
    )
    retry_count = sum(1 for item in attempts if item.get("kind") == "retry")
    round_count = sum(1 for item in attempts if item.get("kind") == "round")
    row.update(
        {
            "attempts": attempts[-20:],
            "retry_count": retry_count,
            "round_count": round_count,
            "last_job_id": job_id,
            "last_kind": kind,
        }
    )
    rounds[round_id] = row
    state["rounds"] = rounds
    state["open_round"] = round_id
    return save_run_state(project_id, state)


def rounds_exhausted(project_id: str | None, round_id: str, *, cap: int = MAX_ROUNDS) -> bool:
    state = load_run_state(project_id)
    row = (state.get("rounds") or {}).get(round_id) or {}
    try:
        count = int(row.get("round_count") or 0)
    except (TypeError, ValueError):
        count = 0
    return count >= max(1, int(cap))


def index_inbox_dir(project_id: str | None) -> Path:
    path = _project_bus(project_id) / "index_inbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def propose_index_patch(
    project_id: str | None,
    patches: dict[str, str],
    *,
    job_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Queue pulse-label patches for the board writer. Engines propose; board commits."""
    clean: dict[str, str] = {}
    for label, value in (patches or {}).items():
        if label not in PULSE_LABELS:
            continue
        clean[label] = clean_memory_text(str(value or ""))[:280]
    if not clean:
        return {}
    item = {
        "id": hashlib.sha256(
            f"{job_id}:{now_iso()}:{json.dumps(clean, sort_keys=True)}".encode()
        ).hexdigest()[:12],
        "at": now_iso(),
        "job_id": job_id,
        "note": clean_memory_text(note)[:160],
        "patches": clean,
        "status": "proposed",
    }
    path = index_inbox_dir(project_id) / f"{item['id']}.json"
    with _WRITE_LOCK:
        path.write_text(json.dumps(item, indent=2), encoding="utf-8")
    return item


def list_index_proposals(project_id: str | None, *, status: str = "proposed") -> list[dict]:
    rows: list[dict] = []
    for path in sorted(index_inbox_dir(project_id).glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict):
            continue
        if status and str(row.get("status") or "") != status:
            continue
        rows.append(row)
    return rows


def commit_index_patches(project_id: str | None, worker_id: str | None = None) -> list[dict]:
    """Single writer: apply proposed pulse patches via patch_scope."""
    from .org import patch_scope

    applied: list[dict] = []
    with _WRITE_LOCK:
        for row in list_index_proposals(project_id, status="proposed"):
            patches = row.get("patches") if isinstance(row.get("patches"), dict) else {}
            for label, value in patches.items():
                if label in PULSE_LABELS:
                    patch_scope(project_id, worker_id, label, str(value))
            row["status"] = "committed"
            row["committed_at"] = now_iso()
            path = index_inbox_dir(project_id) / f"{row['id']}.json"
            path.write_text(json.dumps(row, indent=2), encoding="utf-8")
            applied.append(row)
    return applied


def patch_pulse(
    project_id: str | None,
    worker_id: str | None,
    patches: dict[str, str],
    *,
    job_id: str = "",
    via_inbox: bool = False,
) -> None:
    """Board path: direct patch_scope, or propose+commit when via_inbox."""
    if via_inbox:
        propose_index_patch(project_id, patches, job_id=job_id)
        commit_index_patches(project_id, worker_id)
        return
    from .org import patch_scope

    with _WRITE_LOCK:
        for label, value in (patches or {}).items():
            if label in PULSE_LABELS:
                patch_scope(project_id, worker_id, label, clean_memory_text(str(value))[:280])


def effects_dir(project_id: str | None) -> Path:
    path = _project_bus(project_id) / "effects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def claim_effect(
    project_id: str | None,
    *,
    kind: str,
    payload: str,
    job_id: str = "",
) -> dict[str, Any]:
    """Claim an irreversible effect key. Returns existing claim if already held/done."""
    key = effect_key(kind, project_id, payload)
    path = effects_dir(project_id) / f"{key}.json"
    with _WRITE_LOCK:
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if isinstance(existing, dict) and existing.get("status") in {"claimed", "done"}:
                existing["duplicate"] = True
                return existing
        row = {
            "key": key,
            "kind": kind,
            "status": "claimed",
            "job_id": job_id,
            "payload": clean_memory_text(payload)[:400],
            "claimed_at": now_iso(),
            "done_at": "",
            "receipt": "",
        }
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        return row


def complete_effect(
    project_id: str | None,
    key: str,
    *,
    receipt: str = "",
    ok: bool = True,
) -> dict[str, Any]:
    path = effects_dir(project_id) / f"{key}.json"
    with _WRITE_LOCK:
        if not path.is_file():
            return {"key": key, "status": "missing"}
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"key": key, "status": "corrupt"}
        row["status"] = "done" if ok else "failed"
        row["done_at"] = now_iso()
        row["receipt"] = clean_memory_text(receipt)[:500]
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        return row


def reconcile_effects(project_id: str | None) -> list[dict]:
    """Effects still claimed need human/board reconcile before another attempt."""
    open_rows: list[dict] = []
    for path in effects_dir(project_id).glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("status") == "claimed":
            open_rows.append(row)
    return open_rows


def verifier_blocks_success(
    *,
    preset: str,
    result: str,
    diff_pending: bool = False,
    talk: bool = False,
    failed: bool = False,
) -> tuple[bool, str]:
    """Whether Last may advance as success. Human Accept covers builder diffs."""
    if talk or failed or preset in {"cos", "ask"}:
        return False, ""
    if diff_pending:
        return False, "diff pending — human Accept is the verifier"
    parsed = parse_verifier(result)
    if parsed["stated"] and parsed["status"] == "fail":
        return True, parsed["reason"] or "VERIFY: fail"
    return False, ""


def enrich_receipt(
    receipt: dict,
    *,
    result: str,
    transient: bool = False,
    new_evidence: bool = False,
) -> dict:
    """Stamp round/attempt/verify onto a job receipt and persist run_state."""
    project_id = receipt.get("project_id") if isinstance(receipt.get("project_id"), str) else None
    job_id = str(receipt.get("id") or "")
    task = str(receipt.get("message") or "")
    verify = parse_verifier(result)
    kind = attempt_kind(transient=transient, new_evidence=new_evidence or bool(verify.get("stated")))
    rid = str(receipt.get("round_key") or "") or round_key(project_id, task)
    if job_id:
        record_attempt(
            project_id,
            round_id=rid,
            job_id=job_id,
            kind=kind,
            transient=transient,
            verify=verify,
        )
    receipt["round_key"] = rid
    receipt["attempt_kind"] = kind
    receipt["verify"] = verify
    receipt["process"] = {
        "max_rounds": MAX_ROUNDS,
        "rounds_exhausted": rounds_exhausted(project_id, rid),
        "nested_harness_gap": True,
    }
    open_effects = reconcile_effects(project_id)
    if open_effects:
        receipt["open_effects"] = [
            {"key": row.get("key"), "kind": row.get("kind"), "status": row.get("status")}
            for row in open_effects[:5]
        ]
    return receipt
