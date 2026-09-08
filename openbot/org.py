"""Org tree. Chief of Staff, Project (CEO), named workers the CEO spins up."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .channel import home_summary, telegram_session_id
from .config import load_config
from .detect import hermes_home, which
from .gitutil import git_status
from .bus import ensure_bus, seed_file_contract, seed_org_contracts
from .store import ROOT, clean_memory_text, now_iso, patch_index_line, read_index

SITE_BY_ID = {
    "saa-homes": "https://saahomes.com",
}

RETIRED_CEO_IDS = frozenset({
    "nadia",
    "listlogic",
    "nadia-marketing",
    "app",
    "index",
})
HOSTED_FOLDER_SLUGS = frozenset({"app", "data", "workspace"})
SUPPORT_CEO_ID = "support"
SUPPORT_WORKER_ID = SUPPORT_CEO_ID
HOST_CEO_ID = "openbot"
HOST_CEO_NAME = "OpenBot"

ORG = ROOT / "org"
PROFILE_PATH = ORG / "profile.json"
HERMES_HOMES = ROOT / "hermes-homes"
SLUG_RE = re.compile(r"[^a-z0-9]+")
PRESET_WORKER_IDS = {"think", "builder", "research", "ops", "code"}


def _slug(name: str) -> str:
    slug = SLUG_RE.sub("-", (name or "bot").lower()).strip("-")
    return slug[:40] or "bot"


def _empty_index(title: str, folder: str) -> str:
    return (
        f"# {title}\n\n"
        "CEO brief for this project.\n\n"
        "Now: Ready. Hermes home and Code folder are attached.\n"
        "Last: —\n"
        "Next: Chat, OpenCode, or Hermes — this CEO is wired.\n"
        "Blocker: —\n"
        "Goals: —\n\n"
        f"Folder: {folder}\n"
        "Git: —\n"
        "Hermes: —\n\n"
        "## Contract\n\n"
        "JOB: Own this project's outcome. Route Code to OpenCode; Think/Research/Ops to Hermes.\n"
        "SOURCES: This INDEX, the Code folder, inbox tickets, bus/handoffs.\n"
        "JUDGMENT: Done means INDEX Next is clear and a HANDOFF exists for specialist work.\n"
        "OUTPUT: Short RESULT plus a bus file. Diffs wait for Accept/Reject.\n"
        "FORBIDDEN: Do not publish, pay, delete, or push without the operator. Chat is not memory. No app-bots.\n"
    )


def _empty_brain(name: str, project: str) -> str:
    return (
        f"# {name}\n\n"
        f"Worker on {project}. Uses Think, Code, Research, and Ops as the job needs.\n\n"
        "Now: Ready.\n"
        "Last: —\n"
        "Next: —\n"
        "Blocker: —\n"
        "Goals: Help the CEO finish this project.\n\n"
        "## Contract\n\n"
        "JOB: Help this CEO using the lane the board routed.\n"
        "SOURCES: CEO INDEX, this BRAIN, the ticket, bus/handoffs.\n"
        "JUDGMENT: Hand off through a file, not a giant chat blob.\n"
        "OUTPUT: HANDOFF with TASK, STATUS, OUTPUT, NEXT OWNER.\n"
        "FORBIDDEN: Do not skip gates. Do not publish, pay, or use the operator's master accounts.\n"
    )


def _load_saved() -> dict:
    if not PROFILE_PATH.is_file():
        return {}
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    ORG.mkdir(exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _carry_tools(row: dict) -> dict:
    out = {}
    for key in (
        "mcp_github",
        "skills",
        "spend_cap_usd",
        "seats",
        "connectors",
        "hermes_home",
        "hermes_instance_id",
        "hermes_session_id",
        "account_id",
        "fallback",
        "site_url",
    ):
        if key in row:
            out[key] = row[key]
    return out


def _project_dir(project_id: str) -> Path:
    return ORG / "projects" / project_id


def _same_folder(left: str, right: str) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except OSError:
        return str(left).rstrip("\\/") == str(right).rstrip("\\/")


def _clean_workers(rows) -> list[dict]:
    out = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        wid = _slug(str(row.get("id") or row.get("name") or ""))
        if not wid or wid in PRESET_WORKER_IDS or wid in seen:
            continue
        seen.add(wid)
        out.append(
            {
                "id": wid,
                "name": str(row.get("name") or wid),
                "role": "worker",
                "session": str(row.get("session") or ""),
            }
        )
    return out


def _ensure_project_index(project_id: str, title: str, folder: str) -> Path:
    dest = _project_dir(project_id)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "INDEX.md"
    if not path.exists():
        path.write_text(_empty_index(title, folder), encoding="utf-8")
    return path


def _worker_dir(project_id: str, worker_id: str) -> Path:
    return _project_dir(project_id) / "workers" / worker_id


def _ensure_worker_brain(project_id: str, worker: dict, project_name: str) -> Path:
    path = _worker_dir(project_id, worker["id"]) / "BRAIN.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_empty_brain(worker["name"], project_name), encoding="utf-8")
    else:
        seed_file_contract(path, "worker")
    return path


def _archive_retired_index(project_id: str, title: str) -> None:
    dest = _project_dir(project_id)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "INDEX.md"
    banner = (
        f"# {title} (archived)\n\n"
        "Now: Retired from this OpenBot board. Folder kept on disk.\n"
        "Last: Removed from routing.\n"
        "Next: Re-add as a CEO only if the operator brings this product back.\n"
        "Blocker: —\n\n"
        "This CEO is not in the live org. Keep Cos, OpenBot, SAA Homes, and Support.\n\n"
    )
    if path.is_file():
        body = path.read_text(encoding="utf-8")
        if "Retired from this OpenBot board" in body:
            return
        path.write_text(banner + body, encoding="utf-8")
        return
    path.write_text(banner, encoding="utf-8")


def reattach_imported_ceos(saved: dict) -> dict:
    """Put imported CEOs back if profile.json was rewritten without them."""
    rows = [row for row in (saved.get("projects") or []) if isinstance(row, dict)]
    have = {str(row.get("id") or "") for row in rows}
    homes = HERMES_HOMES
    projects = ORG / "projects"
    if not homes.is_dir() or not projects.is_dir():
        return saved
    changed = False
    for home in homes.iterdir():
        pid = home.name
        if (
            not home.is_dir()
            or pid in have
            or pid in RETIRED_CEO_IDS
            or pid == SUPPORT_CEO_ID
            or pid in {"opencode-test", "staff"}
            or pid.startswith("test")
        ):
            continue
        index = projects / pid / "INDEX.md"
        if not index.is_file():
            continue
        text = index.read_text(encoding="utf-8")
        title = (text.splitlines()[0].lstrip("# ").strip() if text else "") or pid
        folder = ""
        for line in text.splitlines():
            if line.startswith("Folder:"):
                folder = line.split(":", 1)[1].strip()
                break
        rows.append(
            {
                "id": pid,
                "name": title,
                "role": "ceo",
                "folder": folder,
                "primary": False,
                "workers": [],
                "hermes_home": str(home.resolve()),
                "site_url": SITE_BY_ID.get(pid, ""),
            }
        )
        have.add(pid)
        changed = True
    if changed:
        saved["projects"] = rows
    return saved


def retire_archived_ceos(saved: dict) -> dict:
    """Drop Nadia ISA and ListLogic from routing. Keep folders on disk."""
    rows = list(saved.get("projects") or [])
    kept = []
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = _slug(str(row.get("id") or row.get("name") or ""))
        if pid in RETIRED_CEO_IDS:
            _archive_retired_index(pid, str(row.get("name") or pid))
            changed = True
            continue
        kept.append(row)
    if changed:
        saved["projects"] = kept
    for pid in RETIRED_CEO_IDS:
        folder = _project_dir(pid)
        if folder.is_dir():
            _archive_retired_index(pid, pid)
    return saved


def support_charter(folder: str) -> str:
    return (
        "# Support\n\n"
        "Helper on openbot. Owns help tickets and suggestions. Reports to the openbot CEO, Cos, and the operator.\n\n"
        "Now: Ready for suggestions and help tickets.\n"
        "Last: —\n"
        "Next: Triage inbox tickets. Escalate bugs/features to Chief of Staff → openbot Builder.\n"
        "Blocker: —\n"
        "Goals: File every request. Auto-handoff code work. Owner only at Accept / send / announce.\n\n"
        f"Folder: {folder}\n"
        "Git: openbot Builder owns code diffs. Support does not Accept its own work.\n\n"
        "## Owns\n\n"
        "- Ingest suggestions (Help form, chat to this helper, later X mentions).\n"
        "- Triage: FAQ / bug / feature / spam / needs-owner.\n"
        "- Status: received → triage → building → in review → shipped / won't fix.\n"
        "- Draft replies and changelog / X announces into bus/drafts.\n"
        "- Open handoffs to Cos so openbot Builder can code the fix.\n\n"
        "## Stopline\n\n"
        "- Never Accept/Reject a diff. Never git push or merge to main.\n"
        "- Never post to X, send email, or publish without a Needs-you card.\n"
        "- Never touch Follow Up Boss, Flask ISA, Nadia SaaS, or CRM keys.\n"
        "- Never silently fix production. Code waits on the operator gate.\n\n"
        "## Contract\n\n"
        "JOB: Own tickets and suggestions. Triage, schedule, tell the status story, draft replies.\n"
        "SOURCES: This BRAIN, org/projects/support/tickets, openbot INDEX, bus/handoffs.\n"
        "JUDGMENT: FAQ drafts stay in bus/drafts. Bugs/features become a handoff to Cos → openbot Builder.\n"
        "OUTPUT: Ticket phase updates, HANDOFF files, draft replies. Diffs wait for Accept/Reject.\n"
        "FORBIDDEN: No Accept, no push, no live X post, no CRM/FUB, no unsupervised send.\n"
    )


def _write_support_brain(project_id: str, project_name: str) -> None:
    worker = {"id": SUPPORT_WORKER_ID, "name": "Support"}
    path = _ensure_worker_brain(project_id, worker, project_name)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "Stopline" not in text or "CEO for help tickets" in text:
        path.write_text(support_charter(str(_project_dir(project_id) / "work")), encoding="utf-8")


def attach_support_worker(row: dict) -> dict:
    """Keep ticket files. Support itself is a CEO, not a helper chip."""
    tickets = ORG / "projects" / SUPPORT_CEO_ID / "tickets"
    tickets.mkdir(parents=True, exist_ok=True)
    return row


def ensure_support_worker(saved: dict) -> dict:
    """Back-compat alias — Support stays a CEO."""
    return ensure_support_project(saved, str(ROOT))


def ensure_support_project(saved: dict, work: str) -> dict:
    """Keep Support as its own CEO. Tickets stay under org/projects/support."""
    rows = [row for row in (saved.get("projects") or []) if isinstance(row, dict)]
    dest = _project_dir(SUPPORT_CEO_ID) / "work"
    dest.mkdir(parents=True, exist_ok=True)
    if not any(str(row.get("id") or "") == SUPPORT_CEO_ID for row in rows):
        rows.append(
            {
                "id": SUPPORT_CEO_ID,
                "name": "Support",
                "role": "ceo",
                "folder": str(dest),
                "primary": False,
                "workers": [],
            }
        )
        saved["projects"] = rows
    index = _project_dir(SUPPORT_CEO_ID) / "INDEX.md"
    text = index.read_text(encoding="utf-8") if index.is_file() else ""
    if "Stopline" not in text:
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(support_charter(str(dest)), encoding="utf-8")
    tickets = _project_dir(SUPPORT_CEO_ID) / "tickets"
    tickets.mkdir(parents=True, exist_ok=True)
    return saved


def _host_identity(work: str, saved: dict) -> tuple[str, str]:
    """Railway work_dir is /app. That folder is not a CEO."""
    folder_slug = _slug(Path(work).name or HOST_CEO_ID)
    if folder_slug in HOSTED_FOLDER_SLUGS or folder_slug in RETIRED_CEO_IDS:
        return HOST_CEO_ID, HOST_CEO_NAME
    for row in saved.get("projects") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "") == HOST_CEO_ID:
            raw = str(row.get("name") or HOST_CEO_NAME).strip()
            if raw.upper() in {"INDEX", "APP", "OPENBOT", HOST_CEO_ID.upper()}:
                return HOST_CEO_ID, HOST_CEO_NAME
            return HOST_CEO_ID, raw
    if folder_slug == HOST_CEO_ID:
        return HOST_CEO_ID, HOST_CEO_NAME
    return HOST_CEO_ID, HOST_CEO_NAME


def ensure_org() -> dict:
    cfg = load_config()
    work = cfg.get("work_dir") or str(ROOT)
    saved = retire_archived_ceos(_load_saved())
    saved = reattach_imported_ceos(saved)
    saved = ensure_support_project(saved, work)
    extras = []
    primary_workers: list[dict] = []
    primary_id, primary_name = _host_identity(work, saved)
    primary_tools: dict = {}
    for row in saved.get("projects") or []:
        if not isinstance(row, dict):
            continue
        folder = str(row.get("folder") or "")
        pid = _slug(str(row.get("id") or row.get("name") or ""))
        if not pid or pid in RETIRED_CEO_IDS:
            continue
        cleaned = _clean_workers(row.get("workers"))
        if pid == HOST_CEO_ID or (row.get("primary") and pid not in {SUPPORT_CEO_ID, "saa-homes"}):
            if pid == HOST_CEO_ID:
                primary_id = HOST_CEO_ID
                raw = str(row.get("name") or primary_name).strip()
                if raw.upper() not in {"INDEX", "APP", "OPENBOT"}:
                    primary_name = raw
                else:
                    primary_name = HOST_CEO_NAME
            primary_workers = cleaned or primary_workers
            primary_tools = {**primary_tools, **_carry_tools(row)}
            continue
        extras.append(
            {
                "id": pid,
                "name": "Support" if pid == SUPPORT_CEO_ID else (row.get("name") or pid),
                "role": "ceo",
                "folder": folder,
                "primary": False,
                "workers": cleaned,
                **_carry_tools(row),
            }
        )
    _ensure_project_index(primary_id, primary_name, work)
    primary = {
        "id": primary_id,
        "name": primary_name,
        "role": "ceo",
        "folder": work,
        "primary": True,
        "workers": primary_workers,
        **primary_tools,
    }
    data = {
        "name": primary_name,
        "title": "Chief of Staff",
        "role": "cos",
        "folder": work,
        "projects": [primary, *extras],
    }
    _save(data)
    seed_org_contracts([primary_id, *[row["id"] for row in extras]])
    return public_org(data)


def _public_worker(project_id: str, project_name: str, row: dict) -> dict:
    worker = dict(row)
    worker["session"] = worker.get("session") or f"openbot-{project_id}-{worker['id']}"
    brain_path = _ensure_worker_brain(project_id, worker, project_name)
    brain = brain_path.read_text(encoding="utf-8") if brain_path.is_file() else ""
    worker["brain"] = brain
    worker["index_now"] = _now_line(brain)
    return worker


def project_crons(project_id: str, *, results: bool = True) -> list[dict]:
    """Hermes cron list for one CEO. results=True reads last markdown only."""
    pid = str(project_id or "").strip()
    if not pid:
        return []
    from .hermes import read_home_crons

    tools = project_tools(pid)
    return read_home_crons(tools.get("hermes_home"), results=results)


def project_cron_bundle(project_id: str) -> dict:
    """Schedule rows plus a last-two-days story in plain language."""
    from .hermes import cron_digest
    from .live import snapshot

    pid = str(project_id or "").strip()
    rows = project_crons(pid, results=True)
    nxt = index_field(read_project_index(pid), "Next") if pid else ""
    live_runs = [row for row in snapshot() if str(row.get("project_id") or "") == pid]
    return {
        "project_id": pid,
        "crons": rows,
        "live_runs": live_runs,
        "digest": cron_digest(rows, next_ask=nxt, live_runs=live_runs),
    }


def list_projects() -> list[dict]:
    """Return minimal list of projects with id and name."""
    blob = _load_saved()
    if not blob:
        return []
    projects = []
    for row in blob.get("projects") or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "")
        if pid and pid not in RETIRED_CEO_IDS:
            projects.append({
                "id": pid,
                "name": str(row.get("name") or pid),
            })
    return projects


def public_org(data: dict | None = None) -> dict:
    blob = bind_telegram_sessions(data or _load_saved() or ensure_org())
    projects = []
    for row in blob.get("projects") or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "")
        folder = str(row.get("folder") or "")
        name = str(row.get("name") or pid)
        if not pid or pid in RETIRED_CEO_IDS:
            continue
        if pid == HOST_CEO_ID and name.strip().upper() in {"INDEX", "APP", "OPENBOT"}:
            name = HOST_CEO_NAME
        if pid == SUPPORT_CEO_ID:
            name = "Support"
        _ensure_project_index(pid, name, folder)
        seed_file_contract(_project_dir(pid) / "INDEX.md", "ceo")
        ensure_bus(pid)
        index_text = read_project_index(pid)
        git = git_status(folder) if folder else {}
        projects.append(
            {
                "id": pid,
                "name": name,
                "role": "ceo",
                "folder": folder,
                "folder_ok": bool(folder and Path(folder).is_dir()),
                "primary": bool(row.get("primary")),
                "workers": [_public_worker(pid, name, item) for item in _clean_workers(row.get("workers"))],
                "index": index_text,
                "index_now": _now_line(index_text),
                "index_next": index_field(index_text, "Next"),
                "index_blocker": index_field(index_text, "Blocker"),
                "schedules": read_schedules(pid),
                "crons": project_crons(pid, results=False),
                "site_url": str(row.get("site_url") or "").strip(),
                "git": {
                    "is_repo": bool(git.get("is_repo")),
                    "remote": str(git.get("remote") or ""),
                    "branch": str(git.get("branch") or ""),
                    "github": bool(git.get("github")),
                },
                "tools": _public_tools(row),
            }
        )
    return {
        "name": blob.get("name") or "OPENBOT",
        "title": "Chief of Staff",
        "role": "cos",
        "folder": blob.get("folder") or str(ROOT),
        "hermes_home": "",
        "index": read_index(),
        "index_now": _now_line(read_index()),
        "staff": staff_briefing(),
        "projects": projects,
        "workers": [],
    }


def bind_telegram_sessions(data: dict | None = None) -> dict:
    """Attach imported Telegram session ids so Think/Ops resume that brain."""
    blob = data if isinstance(data, dict) else _load_saved()
    changed = False
    for row in blob.get("projects") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("hermes_session_id") or "").strip():
            continue
        sid = telegram_session_id(row.get("hermes_home"))
        if sid:
            row["hermes_session_id"] = sid
            changed = True
    if changed:
        _save(blob)
    return blob


def _now_line(text: str) -> str:
    match = re.search(r"^Now:\s*(.*)$", text or "", re.M)
    return clean_memory_text(match.group(1).strip() if match else "") or "source of truth"


def index_field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", text or "", re.M)
    return clean_memory_text(match.group(1).strip() if match else "") or ""


def _public_tools(row: dict) -> dict:
    seats = row.get("seats") if isinstance(row.get("seats"), dict) else {}
    cap = row.get("spend_cap_usd")
    try:
        cap_val = float(cap) if cap is not None and cap != "" else None
    except (TypeError, ValueError):
        cap_val = None
    summary = home_summary(row.get("hermes_home"))
    connectors = row.get("connectors") if isinstance(row.get("connectors"), dict) else {}
    return {
        "mcp_github": bool(row.get("mcp_github")),
        "skills": str(row.get("skills") or ""),
        "spend_cap_usd": cap_val,
        "hermes_home": str(row.get("hermes_home") or ""),
        "hermes_instance_id": str(row.get("hermes_instance_id") or ""),
        "hermes_session_id": str(row.get("hermes_session_id") or ""),
        "opencode_session_id": str(row.get("opencode_session_id") or ""),
        "session_count": int(summary.get("session_count") or 0),
        "session_title": str(summary.get("session_title") or ""),
        "session_source": str(summary.get("session_source") or ""),
        "account_id": str(row.get("account_id") or ""),
        "fallback": [str(item) for item in (row.get("fallback") or []) if str(item).strip()],
        "site_url": str(row.get("site_url") or "").strip(),
        "connectors": {
            "skills": connectors.get("skills") if isinstance(connectors.get("skills"), dict) else {},
            "mcp": connectors.get("mcp") if isinstance(connectors.get("mcp"), dict) else {}
        },
        "seats": {
            key: {"model": str((seats.get(key) or {}).get("model") or "")}
            for key in ("chat", "think", "code", "research", "ops")
            if isinstance(seats.get(key), dict) or key in seats
        },
    }


def is_board_folder(folder: str | None) -> bool:
    raw = str(folder or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).expanduser().resolve() == ROOT.resolve()
    except OSError:
        return False


def project_id_for_folder(folder: str | None) -> str:
    raw = str(folder or "").strip()
    if not raw:
        return ""
    try:
        target = Path(raw).expanduser().resolve()
    except OSError:
        return ""
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        work = str(row.get("work_dir") or "").strip()
        if not work:
            continue
        try:
            if Path(work).expanduser().resolve() == target:
                return str(row.get("id") or "")
        except OSError:
            continue
    return ""


def is_primary_project(project_id: str | None) -> bool:
    if not project_id:
        return False
    pid = _slug(project_id)
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid == pid or _slug(rid) == pid:
            return bool(row.get("primary"))
    return False


def primary_project_id() -> str | None:
    rows = [row for row in (_load_saved().get("projects") or []) if isinstance(row, dict) and row.get("id")]
    for row in rows:
        if row.get("primary"):
            return str(row.get("id"))
    if rows:
        return str(rows[0].get("id"))
    return None


def work_target(project_id: str | None, preset: str) -> str | None:
    """Cos has no engines. Builder / Think / Research / Ops ride the aimed CEO, or the primary CEO."""
    if preset in {"", "cos", "ask"}:
        return _slug(project_id) if project_id else None
    if project_id:
        return _slug(project_id)
    return primary_project_id()


def ensure_ceo_engines(project_id: str) -> dict:
    """Attach Hermes home + Code folder on a CEO. Cos is never a target."""
    pid = _slug(project_id)
    title = pid
    folder = None
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        title = str(row.get("name") or pid)
        folder = str(row.get("folder") or "").strip() or None
        home = str(row.get("hermes_home") or "").strip()
        if home and Path(home).is_dir() and (not folder or Path(folder).is_dir()):
            return {
                "project_id": pid,
                "folder": folder or "",
                "hermes_home": home,
                "git": (Path(folder) / ".git").exists() if folder else False,
            }
        break
    return bootstrap_ceo_runtime(pid, title, folder)


def staff_briefing() -> str:
    """Chief of Staff memory: four-line INDEX per CEO and worker. No tools. No vault dump."""
    inst = read_index()
    lines = [
        "# Chief of Staff",
        "You report to the operator. Every CEO reports to you.",
        f"Now: {index_field(inst, 'Now') or '—'}",
        f"Last: {index_field(inst, 'Last') or '—'}",
        f"Next: {index_field(inst, 'Next') or '—'}",
        f"Blocker: {index_field(inst, 'Blocker') or '—'}",
        "",
    ]
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row.get("id"))
        name = str(row.get("name") or pid)
        text = read_project_index(pid)
        lines.append(f"## {name} CEO")
        lines.append(f"Now: {index_field(text, 'Now') or '—'}")
        lines.append(f"Last: {index_field(text, 'Last') or '—'}")
        lines.append(f"Next: {index_field(text, 'Next') or '—'}")
        lines.append(f"Blocker: {index_field(text, 'Blocker') or '—'}")
        ticket = inbox_tail(pid, 180)
        if ticket:
            lines.append("Inbox: " + re.sub(r"\s+", " ", ticket)[:180])
        for worker in _clean_workers(row.get("workers")):
            brain = read_worker_brain(pid, worker["id"])
            lines.append(f"{worker['name']}: {index_field(brain, 'Now') or 'Ready'}")
        lines.append("")
    return "\n".join(lines).strip()


def wiring_brief(project_id: str | None = None) -> str:
    """How Chat, OpenCode, and Hermes share this CEO. Shown in status and packets."""
    if not project_id:
        return (
            "You are Chief of Staff. The operator is above you. CEOs report to you. "
            "Ask, and you dispatch: Code → OpenCode in that CEO's folder; "
            "Think / Research / Ops → that CEO's Hermes home. Results come back in this chat. "
            "The operator can also open any CEO and talk to that CEO directly."
        )
    pid = _slug(project_id)
    folder = ""
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        folder = str(row.get("folder") or "").strip()
        break
    tools = project_tools(pid)
    git = git_status(folder) if folder else {}
    remote = str(git.get("remote") or "").strip() or (
        "local git, no origin" if git.get("is_repo") else "not a git folder"
    )
    lines = [
        f"{node_label(pid)} CEO — reports to Chief of Staff. The operator is in this chat with you.",
        f"Code: OpenCode in {folder or '—'} ({remote})",
        f"Hermes: {tools.get('hermes_home') or 'not attached'}",
        f"Bus: org/projects/{pid}/bus/handoffs — files, not chat.",
    ]
    if tools.get("hermes_session_id"):
        lines.append(
            "Telegram: Railway still owns the live bot. Think/Ops resume that session. Chat here does not post there."
        )
    else:
        lines.append("Telegram: no imported session yet. Chat is still the operator surface.")
    return "\n".join(lines)


def staff_status_reply() -> str:
    """Status from files across the org. Cos has no Hermes home."""
    inst = read_index()
    lines: list[str] = []
    now = index_field(inst, "Now")
    if now:
        lines.append(now)
    nxt = index_field(inst, "Next")
    if nxt and nxt != "—":
        lines.append(f"Next: {nxt}")
    blocker = index_field(inst, "Blocker")
    if blocker and blocker != "—":
        lines.append(f"Blocked: {blocker}")
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row.get("id"))
        name = str(row.get("name") or pid)
        text = read_project_index(pid)
        bit = f"{name}: {index_field(text, 'Now') or '—'}"
        stuck = index_field(text, "Blocker")
        if stuck and stuck != "—":
            bit += f" · blocked {stuck}"
        lines.append(bit)
    lines.append(wiring_brief(None))
    return "\n".join(lines).strip()


def ensure_project_workspace(project_id: str) -> str:
    """Secondary CEOs get their own folder. Do not write into the OpenBot repo."""
    ensure_org()
    pid = _slug(project_id)
    dest = ORG / "projects" / pid / "work"
    dest.mkdir(parents=True, exist_ok=True)
    resolved = str(dest.resolve())
    data = _load_saved()
    for row in data.get("projects") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        if row.get("primary"):
            work = str(row.get("folder") or load_config().get("work_dir") or ROOT)
            return str(Path(work).expanduser())
        title = str(row.get("name") or pid)
        current = str(row.get("folder") or "")
        if current and not is_board_folder(current) and Path(current).is_dir():
            folder = str(Path(current).expanduser().resolve())
            bootstrap_ceo_runtime(pid, title, folder)
            return folder
        row["folder"] = resolved
        _save(data)
        _ensure_project_index(pid, title, resolved)
        bootstrap_ceo_runtime(pid, title, resolved)
        return resolved
    return resolved


def _copy_if_missing(src: Path, dest: Path) -> None:
    if not src.is_file() or dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _seed_work_readme(folder: Path, title: str) -> None:
    readme = folder / "README.md"
    if readme.exists():
        return
    extras = [item for item in folder.iterdir() if item.name != ".git"]
    if extras:
        return
    readme.write_text(
        f"# {title}\n\n"
        "Code folder for this CEO. OpenCode runs here. Chat is not memory — INDEX is.\n",
        encoding="utf-8",
    )


def _init_git(folder: Path) -> bool:
    if (folder / ".git").exists():
        return True
    git = which("git")
    if not git:
        return False
    kwargs: dict = {
        "cwd": str(folder),
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 20,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        ran = subprocess.run([git, "init"], **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return ran.returncode == 0


def bootstrap_ceo_runtime(project_id: str, title: str | None = None, folder: str | None = None) -> dict:
    """Attach a Hermes home and a Code folder. Keys stay in the vault. Idempotent."""
    pid = _slug(project_id)
    if folder:
        work = Path(folder).expanduser()
    else:
        work = ORG / "projects" / pid / "work"
        data = _load_saved()
        for row in data.get("projects") or []:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id") or "")
            if rid != pid and _slug(rid) != pid:
                continue
            current = str(row.get("folder") or "").strip()
            if current:
                work = Path(current).expanduser()
            break
    work.mkdir(parents=True, exist_ok=True)
    home = HERMES_HOMES / pid
    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir(exist_ok=True)
    machine = hermes_home()
    _copy_if_missing(machine / "config.yaml", home / "config.yaml")
    _copy_if_missing(machine / "auth.json", home / "auth.json")
    _seed_work_readme(work, (title or pid).strip() or pid)
    git_ok = _init_git(work)
    patch_project_tools(pid, {"hermes_home": str(home.resolve())}, create_if_missing=True)
    stamp_ceo_wiring(pid)
    try:
        from .playskills import seed_dogfood_skills, sync_skills_to_hermes_home

        seed_dogfood_skills()
        sync_skills_to_hermes_home(str(home.resolve()))
    except Exception:
        pass
    return {
        "project_id": pid,
        "folder": str(work.resolve()),
        "hermes_home": str(home.resolve()),
        "git": git_ok,
    }


def stamp_ceo_wiring(project_id: str) -> None:
    """Write Folder / Git / Hermes onto INDEX so the board shows the real links."""
    pid = _slug(project_id)
    folder = ""
    home = ""
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        folder = str(row.get("folder") or "").strip()
        home = str(row.get("hermes_home") or "").strip()
        site = str(row.get("site_url") or "").strip() or SITE_BY_ID.get(pid, "")
        if site and not str(row.get("site_url") or "").strip():
            patch_project_tools(pid, {"site_url": site})
        break
    if folder:
        patch_scope(pid, None, "Folder", folder)
        git = git_status(folder)
        if git.get("remote"):
            branch = str(git.get("branch") or "").strip()
            label = f"{branch} · {git['remote']}" if branch else str(git["remote"])
            patch_scope(pid, None, "Git", label)
        elif git.get("is_repo"):
            patch_scope(pid, None, "Git", "local repo, no origin")
        else:
            patch_scope(pid, None, "Git", "not a git folder")
        nxt = index_field(read_project_index(pid), "Next")
        if "point this ceo at its repo folder" in nxt.lower():
            patch_scope(pid, None, "Next", "Ask Chat what's going on, or Code / Think from this CEO.")
    if home:
        patch_scope(pid, None, "Hermes", home)
    sid = telegram_session_id(home) if home else ""
    if sid:
        patch_project_tools(pid, {"hermes_session_id": sid})
        patch_scope(pid, None, "Telegram", "Railway still live · Think/Ops resume this session")


def project_ids() -> list[str]:
    data = _load_saved()
    out = []
    for row in data.get("projects") or []:
        if isinstance(row, dict) and row.get("id"):
            out.append(str(row.get("id")))
    return out


def project_tools(project_id: str | None) -> dict:
    if not project_id:
        return _public_tools({})
    pid = _slug(project_id)
    for row in (_load_saved().get("projects") or []):
        if isinstance(row, dict) and str(row.get("id") or "") == pid:
            return _public_tools(row)
    return _public_tools({})


def node_label(project_id: str | None = None, worker_id: str | None = None) -> str:
    if not project_id:
        return "OpenBot"
    pid = _slug(project_id)
    for row in (_load_saved().get("projects") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        if worker_id:
            wid = _slug(worker_id)
            for item in _clean_workers(row.get("workers")):
                if str(item.get("id") or "") == wid:
                    return str(item.get("name") or wid)
            return worker_id
        return str(row.get("name") or rid or pid)
    return project_id


def patch_project_tools(project_id: str, patch: dict, create_if_missing: bool = False) -> dict:
    data = _load_saved()
    pid = _slug(project_id)
    found = False
    for row in data.get("projects") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if rid != pid and _slug(rid) != pid:
            continue
        found = True
        if "mcp_github" in patch:
            row["mcp_github"] = bool(patch.get("mcp_github"))
        if "skills" in patch:
            row["skills"] = str(patch.get("skills") or "").strip()
        if "connectors" in patch and isinstance(patch.get("connectors"), dict):
            if "connectors" not in row:
                row["connectors"] = {}
            connectors = patch["connectors"]
            if isinstance(connectors.get("skills"), dict):
                row["connectors"]["skills"] = connectors["skills"]
            if isinstance(connectors.get("mcp"), dict):
                row["connectors"]["mcp"] = connectors["mcp"]
        if "spend_cap_usd" in patch:
            raw = patch.get("spend_cap_usd")
            if raw in (None, ""):
                row.pop("spend_cap_usd", None)
            else:
                row["spend_cap_usd"] = float(raw)
        seats = patch.get("seats")
        if isinstance(seats, dict):
            current = row.get("seats") if isinstance(row.get("seats"), dict) else {}
            for key in ("think", "code", "research", "ops"):
                item = seats.get(key)
                if not isinstance(item, dict):
                    continue
                current[key] = {"model": str(item.get("model") or "").strip()}
            row["seats"] = current
        for key in ("hermes_home", "hermes_instance_id", "hermes_session_id", "opencode_session_id", "account_id", "site_url"):
            if key not in patch:
                continue
            value = str(patch.get(key) or "").strip()
            if value:
                row[key] = value
            else:
                row.pop(key, None)
        if "fallback" in patch:
            raw = patch.get("fallback")
            if not isinstance(raw, list):
                raw = []
            row["fallback"] = [str(item).strip() for item in raw if str(item).strip()]
        break
    if not found:
        if create_if_missing:
            cfg = load_config()
            work_dir = str(cfg.get("work_dir") or ROOT)
            new_project = {
                "id": pid,
                "name": pid,
                "role": "ceo",
                "folder": work_dir,
                "primary": len(data.get("projects") or []) == 0,
                "workers": [],
            }
            for key in ("hermes_home", "hermes_instance_id", "hermes_session_id", "opencode_session_id", "account_id", "site_url"):
                if key in patch:
                    value = str(patch.get(key) or "").strip()
                    if value:
                        new_project[key] = value
            if "projects" not in data:
                data["projects"] = []
            data["projects"].append(new_project)
            _ensure_project_index(pid, pid, work_dir)
        else:
            raise ValueError("project not found")
    _save(data)
    return public_org(data)


def read_project_index(project_id: str | None) -> str:
    if not project_id:
        return read_index()
    path = _project_dir(project_id) / "INDEX.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def read_worker_brain(project_id: str | None, worker_id: str | None) -> str:
    if not project_id or not worker_id:
        return ""
    path = _worker_dir(project_id, worker_id) / "BRAIN.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def patch_file_index(path: Path, label: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    pattern = rf"^{re.escape(label)}:.*$"
    repl = f"{label}: {clean_memory_text(value)}"
    if re.search(pattern, text, flags=re.M):
        text = re.sub(pattern, lambda _match: repl, text, count=1, flags=re.M)
    else:
        text = text.rstrip() + f"\n{repl}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def patch_scope(project_id: str | None, worker_id: str | None, label: str, value: str) -> None:
    if worker_id and project_id:
        patch_file_index(_worker_dir(project_id, worker_id) / "BRAIN.md", label, value)
        patch_file_index(_project_dir(project_id) / "INDEX.md", label, value)
        return
    if project_id:
        patch_file_index(_project_dir(project_id) / "INDEX.md", label, value)
        return
    patch_index_line(label, value)


def rollup_staff(project_id: str | None, worker_id: str | None, result: str) -> None:
    if not project_id:
        return
    name = project_id
    for row in (_load_saved().get("projects") or []):
        if isinstance(row, dict) and str(row.get("id") or "") == project_id:
            name = str(row.get("name") or project_id)
            break
    who = worker_id or "CEO"
    snippet = re.sub(r"\s+", " ", clean_memory_text(result or "").strip())[:160] or "—"
    patch_index_line("Last", f"{name} · {who}: {snippet}")
    patch_index_line("Now", f"{name} just reported")
    patch_index_line("Next", f"Open {name} or keep going from Chief of Staff")


def write_project_inbox(project_id: str, message: str) -> Path:
    path = _project_dir(project_id) / "inbox.md"
    snippet = re.sub(r"\s+", " ", (message or "").strip())[:400]
    block = (
        f"## {now_iso()}\n"
        "Now: queued\n"
        f"Last: {snippet}\n"
        "Next: run the next ticket in this inbox, not a new session\n"
        "Blocker: —\n\n"
    )
    prev = path.read_text(encoding="utf-8") if path.is_file() else "# Inbox\n\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prev + block, encoding="utf-8")
    patch_file_index(_project_dir(project_id) / "INDEX.md", "Next", "Continue the work")
    return path


def inbox_tail(project_id: str | None, limit: int = 400) -> str:
    if not project_id:
        return ""
    path = _project_dir(project_id) / "inbox.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    return text[-limit:] if text else ""


def set_project_folder(project_id: str, folder: str) -> dict:
    path = Path(folder).expanduser()
    if not path.exists() or not path.is_dir():
        raise ValueError("folder does not exist")
    resolved = str(path.resolve())
    data = _load_saved()
    pid = _slug(project_id)
    if not any(isinstance(row, dict) and str(row.get("id") or "") == pid for row in (data.get("projects") or [])):
        ensure_org()
        data = _load_saved()
    primary = False
    found = False
    for row in data.get("projects") or []:
        if not isinstance(row, dict) or str(row.get("id") or "") != pid:
            continue
        found = True
        row["folder"] = resolved
        primary = bool(row.get("primary"))
        if not primary:
            row["name"] = path.name
        patch_file_index(_project_dir(pid) / "INDEX.md", "Folder", resolved)
        break
    if not found:
        raise ValueError("project not found")
    _save(data)
    if not primary:
        bootstrap_ceo_runtime(pid, path.name, resolved)
        return public_org(_load_saved())
    if primary:
        from .config import save_work_dir

        save_work_dir(resolved)
        data = _load_saved()
        for row in data.get("projects") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == pid:
                row["folder"] = resolved
                break
        data["folder"] = resolved
        _save(data)
    return public_org(_load_saved())


def rename_project(project_id: str, name: str) -> dict:
    title = (name or "").strip()
    if not title:
        raise ValueError("name required")
    data = _load_saved()
    pid = _slug(project_id)
    found = False
    for row in data.get("projects") or []:
        if not isinstance(row, dict) or str(row.get("id") or "") != pid:
            continue
        found = True
        row["name"] = title
        break
    if not found:
        raise ValueError("project not found")
    _save(data)
    return public_org(data)


def rename_worker(project_id: str, worker_id: str, name: str) -> dict:
    title = (name or "").strip()
    if not title:
        raise ValueError("name required")
    data = _load_saved()
    pid = _slug(project_id)
    wid = _slug(worker_id)
    found = False
    for row in data.get("projects") or []:
        if not isinstance(row, dict) or str(row.get("id") or "") != pid:
            continue
        workers = _clean_workers(row.get("workers"))
        for item in workers:
            if item["id"] != wid:
                continue
            item["name"] = title
            found = True
            path = _worker_dir(pid, wid) / "BRAIN.md"
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                text = re.sub(r"^# .*$", f"# {title}", text, count=1, flags=re.M)
                path.write_text(text, encoding="utf-8")
            break
        row["workers"] = workers
        break
    if not found:
        raise ValueError("worker not found")
    _save(data)
    return public_org(data)


def write_project_index(project_id: str, text: str) -> str:
    pid = _slug(project_id)
    path = _project_dir(pid) / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean_memory_text(text), encoding="utf-8")
    return path.read_text(encoding="utf-8")


def write_worker_brain(project_id: str, worker_id: str, text: str) -> str:
    pid = _slug(project_id)
    wid = _slug(worker_id)
    path = _worker_dir(pid, wid) / "BRAIN.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _schedules_path(project_id: str) -> Path:
    return _project_dir(project_id) / "schedules.json"


def add_schedule(project_id: str | None, schedule: str, message: str, job_id: str, worker_id: str | None = None) -> list[dict]:
    if not project_id:
        return []
    path = _schedules_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                rows = [row for row in loaded if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            rows = []
    snippet = re.sub(r"\s+", " ", (message or "").strip())[:160]
    rows.insert(
        0,
        {
            "id": job_id,
            "at": now_iso(),
            "schedule": schedule,
            "text": snippet,
            "worker_id": worker_id or "",
        },
    )
    path.write_text(json.dumps(rows[:20], indent=2), encoding="utf-8")
    return rows[:20]


def read_schedules(project_id: str | None) -> list[dict]:
    if not project_id:
        return []
    path = _schedules_path(project_id)
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [row for row in loaded if isinstance(row, dict)][:20]


def session_name(project_id: str | None, worker_id: str | None) -> str | None:
    if worker_id and project_id:
        return f"openbot-{project_id}-{worker_id}"
    if project_id:
        return f"openbot-{project_id}-ceo"
    return None


def add_project(folder: str | None = None, name: str | None = None) -> dict:
    ensure_org()
    data = _load_saved()
    work = str(data.get("folder") or load_config().get("work_dir") or "")
    raw_folder = str(folder or "").strip()
    resolved = ""
    if raw_folder:
        path = Path(raw_folder).expanduser()
        if not path.exists() or not path.is_dir():
            raise ValueError("folder does not exist")
        resolved = str(path.resolve())
    title = (name or "").strip()
    if resolved:
        title = title or Path(resolved).name
    else:
        title = title or "CEO"
        resolved = work
    if not resolved:
        raise ValueError("set a default folder first, or pass a project folder")
    slug = _slug(title)
    if slug == SUPPORT_WORKER_ID:
        raise ValueError("Support is a helper on openbot, not a CEO")
    if slug in RETIRED_CEO_IDS:
        raise ValueError(f"{slug} is retired from this board")
    existing = {str(row.get("id")) for row in (data.get("projects") or []) if isinstance(row, dict)}
    if slug in existing:
        n = 2
        while f"{slug}-{n}" in existing:
            n += 1
        slug = f"{slug}-{n}"
    if not raw_folder:
        dest = ORG / "projects" / slug / "work"
        dest.mkdir(parents=True, exist_ok=True)
        resolved = str(dest.resolve())
    if not resolved:
        raise ValueError("set a default folder first, or pass a project folder")
    _ensure_project_index(slug, title, resolved)
    projects = list(data.get("projects") or [])
    projects.append(
        {
            "id": slug,
            "name": title,
            "role": "ceo",
            "folder": resolved,
            "primary": False,
            "workers": [],
        }
    )
    data["projects"] = projects
    _save(data)
    info = bootstrap_ceo_runtime(slug, title, resolved)
    org = public_org(_load_saved())
    org["project_id"] = slug
    org["hermes_home"] = info["hermes_home"]
    return org


def remove_project(project_id: str, confirm: str = "") -> dict:
    ensure_org()
    data = _load_saved()
    pid = _slug(project_id)
    target = next(
        (
            row
            for row in (data.get("projects") or [])
            if isinstance(row, dict) and str(row.get("id") or "") == pid
        ),
        None,
    )
    if not target:
        raise ValueError("CEO not found")
    name = str(target.get("name") or pid).strip()
    typed = (confirm or "").strip()
    if typed.casefold() not in {name.casefold(), pid.casefold()}:
        raise ValueError(f"type {name} to delete")
    was_primary = bool(target.get("primary"))
    data["projects"] = [
        row
        for row in (data.get("projects") or [])
        if not (isinstance(row, dict) and str(row.get("id") or "") == pid)
    ]
    if was_primary:
        for row in data["projects"]:
            if isinstance(row, dict):
                row["primary"] = True
                break
    _save(data)
    return public_org(data)


def add_worker(project_id: str, name: str) -> dict:
    title = (name or "").strip()
    if not title:
        raise ValueError("name required")
    ensure_org()
    data = _load_saved()
    pid = _slug(project_id)
    slug = _slug(title)
    found = False
    for row in data.get("projects") or []:
        if not isinstance(row, dict) or str(row.get("id") or "") != pid:
            continue
        found = True
        workers = _clean_workers(row.get("workers"))
        existing = {item["id"] for item in workers}
        wid = slug
        n = 2
        while wid in existing:
            wid = f"{slug}-{n}"
            n += 1
        worker = {
            "id": wid,
            "name": title,
            "role": "worker",
            "session": f"openbot-{pid}-{wid}",
        }
        _ensure_worker_brain(pid, worker, str(row.get("name") or pid))
        workers.append(worker)
        row["workers"] = workers
        break
    if not found:
        raise ValueError("project not found")
    _save(data)
    ensure_ceo_engines(pid)
    return public_org(_load_saved())


def remove_worker(project_id: str, worker_id: str) -> dict:
    ensure_org()
    data = _load_saved()
    pid = _slug(project_id)
    wid = _slug(worker_id)
    for row in data.get("projects") or []:
        if not isinstance(row, dict) or str(row.get("id") or "") != pid:
            continue
        row["workers"] = [item for item in _clean_workers(row.get("workers")) if item["id"] != wid]
        break
    _save(data)
    return public_org(data)
