"""Operator profile, decisions log, memory audit. Files, not chat.

Horizons stay the Goal source. This module does not invent a second board.
"""

from __future__ import annotations

import re
from pathlib import Path

from .store import clean_memory_text, now_iso

INDEX_PRUNE_CHARS = 10000
OPERATOR_BODY = (
    "# Operator\n\n"
    "Who: Adam. Operator of this OttoBot instance. Cos chairs. CEOs run companies. "
    "No extra C-suite bots.\n"
    "Tone: Direct. Files stay. Chat dies. Name the engine.\n"
    "Standards: Folder → change → diff card → INDEX. Labor serves Horizons, not chat.\n"
    "Hard nos: Never publish, pay, delete, sign, or push without Accept. "
    "Never treat chat as memory. Never invent Horizons — operator Accepts founding or Save Goals. "
    "Never mass-retry.\n"
)

SEED_DECISIONS = {
    "": (
        "Do not Accept parked restore cards · why: restore cards stay parked until the operator says otherwise",
        "Do not mass-retry failed jobs · why: stampede retries hide the real blocker",
        "OttoBot chat is the inbox · why: Telegram is not required; if connected later it must be the same thread",
    ),
    "saa-homes": (
        "Do not Restart imported SAA Hermes. Do not kill or redeploy live SAA Hermes · why: live Railway owns the scheduler until pause",
    ),
    "listlogic": (
        "ListLogic live box is Offline — ask before redeploy · why: Adam gate; do not invent a replica",
    ),
}

_SLUG = re.compile(r"[^a-z0-9]+")
_BLOCKER = re.compile(r"^Blocker:\s*(.*)$")
_DASH = frozenset({"", "—", "-", "–"})


def _org() -> Path:
    from .org import ORG

    return ORG


def _slug(project_id: str | None) -> str:
    raw = _SLUG.sub("-", (project_id or "").lower()).strip("-")
    return raw[:40]


def operator_path() -> Path:
    return _org() / "OPERATOR.md"


def decisions_path(project_id: str | None = None) -> Path:
    pid = _slug(project_id)
    if pid:
        return _org() / "projects" / pid / "DECISIONS.md"
    return _org() / "DECISIONS.md"


def ensure_memory_files() -> None:
    """Seed operator + decisions once. Never overwrite a file the operator already has."""
    org = _org()
    org.mkdir(parents=True, exist_ok=True)
    path = operator_path()
    if not path.is_file():
        path.write_text(OPERATOR_BODY, encoding="utf-8")
    _seed_decisions(None)
    try:
        from .org import list_projects

        ids = [str(row.get("id") or "") for row in (list_projects() or [])]
    except Exception:
        ids = []
    for pid in ids:
        if pid:
            _seed_decisions(pid)


def _seed_decisions(project_id: str | None) -> None:
    path = decisions_path(project_id)
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    who = _slug(project_id) or "instance"
    lines = [
        "# Decisions\n",
        "Settled calls. Read before acting. Do not reopen without flagging the operator.\n",
        "Labor serves Horizons on this CEO INDEX. A decision that fights a Horizon needs the operator.\n",
    ]
    seeds = SEED_DECISIONS.get(who if project_id else "", ())
    if not seeds and project_id:
        lines.append("\n")
        path.write_text("".join(lines), encoding="utf-8")
        return
    for note in seeds:
        lines.append(f"- {now_iso()} · {who} · {note}\n")
    path.write_text("".join(lines) + ("\n" if not lines[-1].endswith("\n") else ""), encoding="utf-8")


def read_operator() -> str:
    path = operator_path()
    if not path.is_file():
        return OPERATOR_BODY.strip()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return OPERATOR_BODY.strip()


def operator_packet(project_id: str | None = None) -> str:
    """Who the operator is, plus live Horizons as the Goal. Do not copy Horizon lines here."""
    from .org import horizon_week, read_project_index

    body = read_operator()[:1200]
    aimed = ""
    if project_id:
        aimed = horizon_week(read_project_index(project_id))
    instance = horizon_week(read_project_index("openbot"))
    lines = ["OPERATOR:", body]
    if project_id:
        if aimed:
            lines.append(f"Aimed this week: {aimed}")
        else:
            lines.append("Aimed this week: Goals empty — operator Accepts founding or Save Goals.")
    if instance and instance != aimed:
        lines.append(f"Instance this week: {instance}")
    lines.append("Labor serves Horizons in this packet. Do not substitute a different board.")
    return "\n".join(lines)


def append_decision(project_id: str | None, what: str, why: str = "") -> str:
    ensure_memory_files()
    path = decisions_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        _seed_decisions(project_id)
    who = _slug(project_id) or "instance"
    note = clean_memory_text(what or "").strip()[:400]
    reason = clean_memory_text(why or "").strip()[:240]
    if not note:
        return ""
    line = f"- {now_iso()} · {who} · {note}"
    if reason:
        line += f" · why: {reason}"
    line += "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return line.strip()


def decisions_excerpt(project_id: str | None = None, limit: int = 1200) -> str:
    chunks: list[str] = []
    for pid in (None, project_id):
        path = decisions_path(pid)
        if pid and decisions_path(None) == path:
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rows = [line for line in text.splitlines() if line.startswith("- ")]
        if rows:
            label = _slug(pid) if pid else "instance"
            chunks.append(f"{label}:\n" + "\n".join(rows[-8:]))
    blob = "\n\n".join(chunks).strip()
    return blob[:limit]


def memory_packet_extra(project_id: str | None = None) -> str:
    bits = [operator_packet(project_id)]
    decided = decisions_excerpt(project_id)
    if decided:
        bits.append("DECISIONS (settled; do not reopen without flagging the operator):\n" + decided)
    return "\n\n".join(bits)


def teach_from_reject(
    project_id: str | None,
    job_id: str,
    message: str = "",
    reason: str = "",
) -> str:
    """Reject is training data. Save always/never so the CEO does not repeat it."""
    from .bus import append_rule

    snippet = clean_memory_text(message or "").strip()[:160] or "this change"
    why = clean_memory_text(reason or "").strip()[:240]
    rule = f"always wait for a new ticket; never silently re-apply rejected job {job_id}: {snippet}"
    if why:
        rule += f" — because {why}"
    saved = append_rule(rule)
    append_decision(
        project_id,
        f"rejected diff {job_id}: {snippet}",
        why or "operator Rejected the diff; restore stands",
    )
    return saved


def teach_from_founding(project_id: str, *, accepted: bool, reason: str = "", week: str = "") -> str:
    pid = _slug(project_id)
    if not pid:
        return ""
    if accepted:
        note = f"accepted founding Horizons"
        if week:
            note += f": {week[:160]}"
        return append_decision(pid, note, "operator Accept; labor serves these Goals")
    return append_decision(
        pid,
        "rejected founding Horizons draft",
        reason or "operator Rejected; founding stays needed",
    )


def teach_from_horizons(project_id: str, week: str = "") -> str:
    pid = _slug(project_id)
    if not pid:
        return ""
    note = "Horizons saved"
    if week:
        note += f": {week[:160]}"
    return append_decision(pid, note, "Goals board; labor serves this week")


def collapse_blockers(text: str) -> str:
    """Keep one Blocker line. Prefer a real never over empty dashes."""
    lines = (text or "").splitlines()
    hits = [(i, line) for i, line in enumerate(lines) if _BLOCKER.match(line)]
    if len(hits) <= 1:
        return text
    values: list[str] = []
    for _, line in hits:
        match = _BLOCKER.match(line)
        val = (match.group(1).strip() if match else "").strip()
        if val not in _DASH:
            values.append(val)
    keep = values[0] if values else "—"
    first = hits[0][0]
    drop = {i for i, _ in hits[1:]}
    out: list[str] = []
    for i, line in enumerate(lines):
        if i == first:
            out.append(f"Blocker: {keep}")
        elif i in drop:
            continue
        else:
            out.append(line)
    blob = "\n".join(out)
    if (text or "").endswith("\n"):
        blob += "\n"
    return blob


def apply_safe_prune(project_id: str | None) -> bool:
    """Safe only: collapse duplicate Blocker lines. Never delete doctrine or dumps."""
    pid = _slug(project_id)
    if not pid:
        return False
    path = _org() / "projects" / pid / "INDEX.md"
    if not path.is_file():
        return False
    try:
        old = path.read_text(encoding="utf-8")
    except OSError:
        return False
    new = collapse_blockers(old)
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def prune_candidates(project_id: str | None = None) -> list[str]:
    from .org import list_projects, read_project_index

    rows = []
    wanted = _slug(project_id)
    projects = list_projects() if not wanted else [{"id": wanted, "name": wanted}]
    for row in projects:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "")
        if not pid:
            continue
        text = read_project_index(pid)
        name = str(row.get("name") or pid)
        rows.extend(_flags_for(pid, name, text))
    return rows


def _flags_for(pid: str, name: str, text: str) -> list[str]:
    from .org import horizon_week

    flags: list[str] = []
    label = f"{pid} ({name})"
    blob = text or ""
    if len(blob) > INDEX_PRUNE_CHARS:
        flags.append(f"{label}: INDEX {len(blob)} chars — prune stale dump, keep Horizons + Law")
    if len(re.findall(r"^Blocker:", blob, re.M)) > 1:
        flags.append(f"{label}: more than one Blocker line")
    if not horizon_week(text):
        flags.append(f"{label}: Goals empty — operator Accepts founding or Save Goals")
    if re.search(r"^## From Hermes", blob, re.M):
        flags.append(f"{label}: imported Hermes dump still in INDEX — promote doctrine, drop the rest")
    decided = decisions_excerpt(pid, limit=4000)
    for match in re.finditer(r"^Blocker:\s*(.+)$", blob, re.M):
        val = match.group(1).strip()
        if val in _DASH:
            continue
        if "do not" in val.lower() or "never" in val.lower():
            if val[:40].lower() not in decided.lower():
                flags.append(f"{label}: Blocker looks settled — promote to DECISIONS so INDEX can forget it")
    return flags


def memory_audit_text(project_id: str | None = None) -> str:
    ensure_memory_files()
    from .org import horizon_week, list_projects, read_project_index

    lines = ["Memory audit (files, not chat):"]
    op = operator_path()
    lines.append("Operator: " + ("present" if op.is_file() else "missing — seeded on next ensure"))
    wanted = _slug(project_id)
    projects = list_projects() if not wanted else [row for row in list_projects() if str(row.get("id") or "") == wanted]
    if not projects and wanted:
        projects = [{"id": wanted, "name": wanted}]
    for row in projects:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row.get("id"))
        name = str(row.get("name") or pid)
        text = read_project_index(pid)
        week = horizon_week(text) or "Goals empty"
        size = len(text or "")
        decided = len([line for line in (decisions_path(pid).read_text(encoding="utf-8").splitlines() if decisions_path(pid).is_file() else []) if line.startswith("- ")])
        lines.append(f"- {pid}: {name} · this week: {week[:120]} · INDEX {size} chars · {decided} decisions")
        for flag in _flags_for(pid, name, text):
            lines.append(f"  flag: {flag}")
    rest = prune_candidates(project_id)
    if not any("flag:" in line for line in lines) and not rest:
        lines.append("No prune flags. Small current INDEX beats a giant stale one.")
    else:
        lines.append("Say prune memory to collapse duplicate Blockers. Dumps wait for a yes.")
    return "\n".join(lines)


def prune_reply(project_id: str | None = None) -> str:
    ensure_memory_files()
    from .org import list_projects

    fixed: list[str] = []
    wanted = _slug(project_id)
    ids = [wanted] if wanted else [str(row.get("id") or "") for row in (list_projects() or []) if row.get("id")]
    for pid in ids:
        if pid and apply_safe_prune(pid):
            fixed.append(pid)
    bits = ["Weekly prune (board). Engine: board."]
    if fixed:
        bits.append("Safe fix: collapsed duplicate Blocker lines on " + ", ".join(fixed) + ".")
    else:
        bits.append("No duplicate Blocker lines to collapse.")
    flags = prune_candidates(project_id)
    if flags:
        bits.append("Still needs a yes before delete:")
        bits.extend(f"- {item}" for item in flags[:12])
        bits.append("Dumps and doctrine stay until you say what to drop.")
    else:
        bits.append("Nothing else looks stale.")
    bits.append("Metric: how often a bot repeats something you already corrected. If that is not dropping, prune is not running.")
    return "\n".join(bits)
