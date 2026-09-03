"""Import an existing Hermes Agent into an OpenBot CEO.

Wires official `hermes backup` / `hermes import`. Does not invent a third runtime.
API keys stay in the vault or the imported Hermes home — never INDEX or chat.
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .detect import which
from .hermes import import_backup as hermes_import_zip
from .keyring import SECRETS_PATH
from . import org as org_mod
from .org import add_project, patch_project_tools, project_ids, public_org, write_project_index
from .store import ROOT

HOMES = ROOT / "hermes-homes"
MEMORY_FILES = ("soul.md", "user.md", "memory.md", "agents.md")
SECRET_LINE = re.compile(
    r"(?i)^\s*(api[_-]?key|secret|password|token|bearer|authorization)\s*[:=].+"
)
KEYISH = re.compile(r"\b(?:sk-|or-v1-|go-)[A-Za-z0-9_-]{12,}")
HEADING = re.compile(r"^#\s+(.+)$", re.M)
INDEX_LINE = re.compile(r"^(Now|Last|Next|Blocker|Goals):\s*(.*)$", re.M)
MAX_MD = 8000
MAX_INDEX = 12000


def _sanitize(text: str) -> str:
    out = []
    for line in (text or "").splitlines():
        if SECRET_LINE.search(line) or KEYISH.search(line):
            out.append("[redacted]")
            continue
        out.append(line)
    return "\n".join(out).strip()


def _read_zip_text(archive: zipfile.ZipFile, name: str) -> str:
    try:
        raw = archive.read(name)
    except KeyError:
        return ""
    try:
        return raw.decode("utf-8", errors="replace")[:MAX_MD]
    except Exception:
        return ""


def peek_backup(path: str) -> dict:
    """List identity files in a `hermes backup` zip. Never returns .env contents."""
    raw = (path or "").strip().strip('"')
    zip_path = Path(raw).expanduser()
    if not zip_path.is_file():
        raise ValueError("backup zip not found")
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("not a hermes backup zip")
    found: dict[str, str] = {}
    skill_count = 0
    session_hint = 0
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            base = Path(name).name.lower()
            if base in MEMORY_FILES and base not in found:
                found[base] = _sanitize(_read_zip_text(archive, name))
            if "/skills/" in name.replace("\\", "/").lower() and name.endswith("SKILL.md"):
                skill_count += 1
            if base in {"state.db", "sessions.json"} or "/sessions/" in name.replace("\\", "/").lower():
                session_hint += 1
    soul = found.get("soul.md") or ""
    title_match = HEADING.search(soul) or HEADING.search(found.get("user.md") or "")
    title = (title_match.group(1).strip() if title_match else "") or zip_path.stem
    title = re.sub(r"^hermes-backup-\d{4}-\d{2}-\d{2}.*", "Imported Hermes", title, flags=re.I)
    if title.lower().startswith("hermes-backup"):
        title = "Imported Hermes"
    return {
        "path": str(zip_path.resolve()),
        "title": title[:80],
        "files": sorted(found.keys()),
        "soul": (soul or "")[:1200],
        "has_memory": bool(found.get("memory.md") or found.get("user.md")),
        "skill_count": skill_count,
        "session_hint": bool(session_hint),
        "texts": found,
    }


def build_index(title: str, folder: str, texts: dict[str, str], source: str) -> str:
    blob = "\n\n".join(texts.get(name) or "" for name in MEMORY_FILES)
    blob = _sanitize(blob)
    fields = {label: "" for label in ("Now", "Last", "Next", "Blocker", "Goals")}
    for match in INDEX_LINE.finditer(blob):
        fields[match.group(1)] = match.group(2).strip()
    now = fields["Now"] or "Imported from Hermes. Memory files are the source of truth."
    last = fields["Last"] or f"Imported via {source}."
    nxt = fields["Next"] or "Point this CEO at its repo folder and keep going."
    body = blob[:6000] if blob else "No SOUL.md / MEMORY.md in the backup. Sessions still live in the imported Hermes home."
    return (
        f"# {title}\n\n"
        "CEO imported from Hermes Agent. Chat is not memory.\n\n"
        f"Now: {now}\n"
        f"Last: {last}\n"
        f"Next: {nxt}\n"
        f"Blocker: {fields['Blocker'] or '—'}\n"
        f"Goals: {fields['Goals'] or '—'}\n\n"
        f"Folder: {folder}\n"
        f"Source: {source}\n\n"
        "## From Hermes\n\n"
        f"{body}\n"
    )[:MAX_INDEX]


def _new_project_id(before: set[str], org: dict) -> str:
    for row in org.get("projects") or []:
        pid = str(row.get("id") or "")
        if pid and pid not in before and not row.get("primary"):
            return pid
    raise ValueError("CEO was not created")


def _import_folder(folder: str | None) -> str:
    raw = (folder or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_dir():
            raise ValueError("folder does not exist")
        return str(path.resolve())
    dest = org_mod.HERMES_HOMES / f"workspace-{uuid.uuid4().hex[:8]}"
    dest.mkdir(parents=True, exist_ok=True)
    return str(dest)


def import_from_backup(path: str, name: str | None = None, folder: str | None = None) -> dict:
    peek = peek_backup(path)
    title = (name or "").strip() or peek["title"]
    work = _import_folder(folder)
    before = set(project_ids())
    org = add_project(work, title)
    pid = _new_project_id(before, org)
    home = org_mod.HERMES_HOMES / pid
    home.mkdir(parents=True, exist_ok=True)
    index = build_index(title, work, peek.get("texts") or {}, peek["path"])
    write_project_index(pid, index)
    imported = {"ok": False, "text": "Hermes Agent binary missing. INDEX was filled from SOUL/MEMORY only."}
    if which("hermes"):
        imported = hermes_import_zip(peek["path"], home)
        if not imported.get("ok"):
            write_project_index(
                pid,
                index.replace(
                    "Blocker: —",
                    f"Blocker: hermes import failed ({imported.get('code')})",
                    1,
                ),
            )
    patch_project_tools(pid, {"hermes_home": str(home.resolve())})
    from .channel import telegram_session_id

    sid = telegram_session_id(home)
    if sid:
        patch_project_tools(pid, {"hermes_session_id": sid})
    org_mod.stamp_ceo_wiring(pid)
    return {
        "ok": True,
        "project_id": pid,
        "hermes_home": str(home.resolve()),
        "hermes_import": {"ok": bool(imported.get("ok")), "text": str(imported.get("text") or "")[-2000:]},
        "org": public_org(),
    }


def _load_secrets() -> dict:
    if not SECRETS_PATH.is_file():
        return {}
    try:
        raw = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_instances(rows: list[dict]) -> None:
    data = _load_secrets()
    data["hermes_instances"] = rows
    SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _instances() -> list[dict]:
    rows = []
    for row in _load_secrets().get("hermes_instances") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip().rstrip("/")
        key = str(row.get("key") or "").strip()
        if not url or not key:
            continue
        rows.append(
            {
                "id": str(row.get("id") or uuid.uuid4().hex[:8]),
                "label": str(row.get("label") or url).strip(),
                "url": url,
                "key": key,
            }
        )
    return rows


def public_instances() -> list[dict]:
    return [
        {"id": row["id"], "label": row["label"], "url": row["url"], "has_key": True}
        for row in _instances()
    ]


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("instance URL required")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("instance URL must be http(s)")
    return raw.rstrip("/")


def add_instance(url: str, key: str, label: str | None = None) -> list[dict]:
    base = _normalize_url(url)
    secret = (key or "").strip()
    if not secret:
        raise ValueError("API server key required")
    rows = _instances()
    instance_id = uuid.uuid4().hex[:8]
    nice = (label or "").strip() or urlparse(base).netloc
    rows.append({"id": instance_id, "label": nice, "url": base, "key": secret})
    _save_instances(rows)
    return public_instances()


def delete_instance(instance_id: str) -> list[dict]:
    rows = [row for row in _instances() if row["id"] != instance_id]
    _save_instances(rows)
    return public_instances()


def _instance(instance_id: str) -> dict:
    row = next((item for item in _instances() if item["id"] == instance_id), None)
    if not row:
        raise ValueError("instance not found")
    return row


def _http_json(url: str, key: str) -> dict | list:
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as err:
        raise ValueError(f"remote Hermes HTTP {err.code}") from err
    except URLError as err:
        raise ValueError(f"remote Hermes unreachable: {err.reason}") from err
    except json.JSONDecodeError as err:
        raise ValueError("remote Hermes did not return JSON") from err
    if not isinstance(payload, (dict, list)):
        raise ValueError("remote Hermes returned an unexpected payload")
    return payload


def _session_rows(payload: dict | list) -> list[dict]:
    rows = payload
    if isinstance(payload, dict):
        for key in ("sessions", "items", "data"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = []
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or row.get("session_id") or "").strip()
        if not sid:
            continue
        title = str(row.get("title") or row.get("name") or sid).strip()
        out.append({"id": sid, "title": title[:120]})
    return out[:80]


def list_sessions(instance_id: str) -> list[dict]:
    row = _instance(instance_id)
    for suffix in ("/api/sessions?limit=50", "/api/sessions"):
        try:
            payload = _http_json(row["url"] + suffix, row["key"])
            return _session_rows(payload)
        except ValueError:
            continue
    raise ValueError("could not list sessions on that instance")


def _message_text(item: dict) -> str:
    for key in ("content", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = item.get("parts")
    if isinstance(parts, list):
        bits = []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                bits.append(part["text"])
        if bits:
            return "\n".join(bits).strip()
    return ""


def _session_brief(instance: dict, session_id: str) -> str:
    payload = _http_json(
        f"{instance['url']}/api/sessions/{session_id}/messages?limit=30",
        instance["key"],
    )
    messages = payload
    if isinstance(payload, dict):
        messages = payload.get("messages") or payload.get("items") or payload.get("data") or []
    bits = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "message")
        text = _sanitize(_message_text(item))
        if not text:
            continue
        bits.append(f"{role}: {text[:800]}")
    return "\n\n".join(bits[-12:])[:6000]


def import_session(instance_id: str, session_id: str, name: str | None = None, folder: str | None = None) -> dict:
    instance = _instance(instance_id)
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session id required")
    title = (name or "").strip() or sid[:40]
    work = _import_folder(folder)
    before = set(project_ids())
    org = add_project(work, title)
    pid = _new_project_id(before, org)
    brief = _session_brief(instance, sid)
    index = build_index(
        title,
        work,
        {"soul.md": brief},
        f"{instance['url']} session {sid}",
    )
    write_project_index(pid, index)
    patch_project_tools(
        pid,
        {
            "hermes_instance_id": instance_id,
            "hermes_session_id": sid,
        },
    )
    return {"ok": True, "project_id": pid, "org": public_org()}
