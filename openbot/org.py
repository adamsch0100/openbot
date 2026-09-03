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
from .store import ROOT, now_iso, patch_index_line, read_index

SITE_BY_ID = {
    "saa-homes": "https://saahomes.com",
    "listlogic": "https://listlogic.homes",
}

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


def ensure_org() -> dict:
    cfg = load_config()
    work = cfg.get("work_dir") or str(ROOT)
    name = Path(work).name or "OPENBOT"
    slug = _slug(name)
    saved = _load_saved()
    extras = []
    primary_workers: list[dict] = []
    primary_id = slug
    primary_name = name
    primary_tools: dict = {}
    for row in saved.get("projects") or []:
        if not isinstance(row, dict):
            continue
        folder = str(row.get("folder") or "")
        pid = _slug(str(row.get("id") or row.get("name") or ""))
        if not pid:
            continue
        cleaned = _clean_workers(row.get("workers"))
        if row.get("primary") or pid == slug:
            primary_workers = cleaned
            primary_tools = _carry_tools(row)
            if row.get("name"):
                primary_name = str(row.get("name"))
            if row.get("primary") and pid:
                primary_id = pid
            continue
        extras.append(
            {
                "id": pid,
                "name": row.get("name") or pid,
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
        "name": name,
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


def public_org(data: dict | None = None) -> dict:
    blob = bind_telegram_sessions(data or _load_saved() or ensure_org())
    projects = []
    for row in blob.get("projects") or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "")
        folder = str(row.get("folder") or "")
        name = str(row.get("name") or pid)
        if pid:
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
    return (match.group(1).strip() if match else "") or "source of truth"


def index_field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", text or "", re.M)
    return (match.group(1).strip() if match else "") or ""


def _public_tools(row: dict) -> dict:
    seats = row.get("seats") if isinstance(row.get("seats"), dict) else {}
    cap = row.get("spend_cap_usd")
    try:
        cap_val = float(cap) if cap is not None and cap != "" else None
    except (TypeError, ValueError):
        cap_val = None
    summary = home_summary(row.get("hermes_home"))
    return {
        "mcp_github": bool(row.get("mcp_github")),
        "skills": str(row.get("skills") or ""),
        "spend_cap_usd": cap_val,
        "hermes_home": str(row.get("hermes_home") or ""),
        "hermes_instance_id": str(row.get("hermes_instance_id") or ""),
        "hermes_session_id": str(row.get("hermes_session_id") or ""),
        "session_count": int(summary.get("session_count") or 0),
        "session_title": str(summary.get("session_title") or ""),
        "session_source": str(summary.get("session_source") or ""),
        "account_id": str(row.get("account_id") or ""),
        "fallback": [str(item) for item in (row.get("fallback") or []) if str(item).strip()],
        "site_url": str(row.get("site_url") or "").strip(),
        "seats": {
            key: {"model": str((seats.get(key) or {}).get("model") or "")}
            for key in ("think", "code", "research", "ops")
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
    patch_project_tools(pid, {"hermes_home": str(home.resolve())})
    stamp_ceo_wiring(pid)
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


def patch_project_tools(project_id: str, patch: dict) -> dict:
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
        for key in ("hermes_home", "hermes_instance_id", "hermes_session_id", "account_id", "site_url"):
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
    repl = f"{label}: {value}"
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
    snippet = re.sub(r"\s+", " ", (result or "").strip())[:160] or "—"
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
    path.write_text(text, encoding="utf-8")
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
