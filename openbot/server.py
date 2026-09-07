"""Local board. Stdlib only. Bind loopback."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .channel import public_channel
from .config import (
    apply_env_file,
    load_config,
    load_settings,
    public_operator,
    save_settings,
    save_spend_cap,
    save_work_dir,
    verify_pin,
)
from .cronwatch import ingest_cron_runs
from .detect import detect
from .gitutil import git_status
from .hermes import (
    gateway_start,
    gateway_status,
    gateway_stop,
    mcp_catalog,
    migrate_cron_delivery,
    skills_list,
)
from .onboarding import onboarding_status, test_job_prompt
from .hermes_import import (
    add_instance,
    delete_instance,
    import_from_backup,
    import_session,
    list_sessions,
    peek_backup,
    public_instances,
)
from .keyring import (
    add_account,
    add_login,
    delete_account,
    delete_login,
    public_keyring,
    redact_chat_login,
    rename_account,
    set_fallback,
    use_login,
)
from .launch import (
    hermes_dash_status,
    open_hermes,
    opencode_web_status,
    start_hermes_dashboard,
    start_opencode_web,
    warm_engines_background,
)
from .live import finish as live_finish
from .live import start as live_start
from .live import stop as live_stop
from .models import ensure_chat_model, public_catalog, validate_seats
from .org import (
    add_project,
    add_worker,
    ensure_org,
    patch_project_tools,
    project_tools,
    remove_project,
    remove_worker,
    rename_project,
    rename_worker,
    set_project_folder,
    write_project_index,
    write_worker_brain,
)
from .engine_proxy import inject_opencode_tree
from .providers import connected_provider_ids, openrouter_models, provider_status, zen_models
from .router import decide_diff, revert_accept, handle, pending_approvals, public_job
from .share import (
    actor_stamp,
    allows_project,
    check_job_run,
    create_invite,
    filter_jobs,
    filter_org,
    get_member,
    member_can,
    member_from_session,
    member_project_id,
    owner_only_path,
    patch_member,
    pause_member,
    peek_invite,
    project_share,
    public_member,
    redeem_invite,
    remove_member,
    revoke_invite,
    set_member_secret,
    touch_member,
    unlock_member,
)
from .queueworker import active_workers, auto_create_handoffs
from .store import (
    CODE_ROOT,
    ROOT,
    list_brains,
    list_jobs,
    read_brain,
    read_index,
    read_job,
    spend_summary,
    write_brain,
    write_index,
)
from .threadstore import append_turn, read_thread, thread_key

WEB = CODE_ROOT / "web"
JOB_ACTION = re.compile(r"^/api/jobs/([a-f0-9]{6,32})/(accept|reject)$")
JOB_REVERT = re.compile(r"^/api/jobs/([a-f0-9]{6,32})/revert$")
RUN_STOP = re.compile(r"^/api/runs/([a-zA-Z0-9-]{6,40})/stop$")
BRAIN_PATH = re.compile(r"^/api/brains/(cos|builder|research|ops|think)$")
KEY_ID = re.compile(r"^/api/keys/([a-zA-Z0-9_-]{4,32})$")
LOGIN_ID = re.compile(r"^/api/logins/([a-zA-Z0-9_-]{4,32})$")
PROJECT_ID = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})$")
PROJECT_INDEX = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/index$")
WORKER_ADD = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/workers$")
ROUTINE_ID = re.compile(r"^/api/routines/([a-z0-9-]{8,32})$")
ROUTINE_EXECUTE = re.compile(r"^/api/routines/([a-z0-9-]{8,32})/execute$")
ROUTINE_RESUME = re.compile(r"^/api/routines/([a-z0-9-]{8,32})/resume$")
WORKER_DEL = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/workers/([a-z0-9-]{1,40})$")
WORKER_BRAIN = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/workers/([a-z0-9-]{1,40})/brain$")
PROJECT_CHANNEL = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/channel$")
INSTANCE_ID = re.compile(r"^/api/hermes/instances/([a-zA-Z0-9_-]{4,32})$")
INSTANCE_SESSIONS = re.compile(r"^/api/hermes/instances/([a-zA-Z0-9_-]{4,32})/sessions$")
INSTANCE_SESSION = re.compile(
    r"^/api/hermes/instances/([a-zA-Z0-9_-]{4,32})/sessions/([A-Za-z0-9._:-]{2,120})$"
)
SHARE_INVITE_TOKEN = re.compile(r"^/api/share/invite/([A-Za-z0-9_-]{8,80})$")
SHARE_INVITE_ID = re.compile(r"^/api/share/invites/([a-f0-9]{6,32})$")
SHARE_MEMBER_ID = re.compile(r"^/api/share/members/([a-f0-9]{6,32})$")
PRESET_ENGINE = {
    "cos": "board",
    "think": "Hermes Agent",
    "builder": "OpenCode",
    "research": "Hermes Agent",
    "ops": "Hermes Agent",
}

CREDIT = (
    "OpenBot uses Hermes Agent (MIT, Nous Research) "
    "and OpenCode (MIT, Anomaly). "
    "Not affiliated with, sponsored by, or endorsed by those projects."
)
_UNLOCK_TOKENS: set[str] = set()
_UNLOCK_LOCK = threading.Lock()


def _cookie_value(header: str | None, name: str) -> str:
    jar = SimpleCookie()
    try:
        jar.load(header or "")
    except (TypeError, ValueError):
        return ""
    morsel = jar.get(name)
    return morsel.value if morsel else ""


def _mint_unlock() -> str:
    token = secrets.token_hex(16)
    with _UNLOCK_LOCK:
        _UNLOCK_TOKENS.add(token)
    return token


def _has_key(keyring: dict | None = None) -> bool:
    ring = keyring if keyring is not None else public_keyring()
    return any(row.get("has_key") for row in ring.get("accounts") or [])


ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".txt", ".md", ".json", ".csv", ".xml", ".html",
    ".js", ".ts", ".py", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".sql", ".yaml", ".yml", ".toml",
    ".mp4", ".webm", ".mp3", ".wav", ".ogg"
}
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024


def _save_attachments(files: list, project_id: str | None) -> tuple[list[dict], str | None]:
    if not files:
        return [], None
    from .store import ROOT
    if project_id:
        org = ensure_org()
        match = next((row for row in org["projects"] if row.get("id") == project_id), None)
        if match:
            attach_dir = ROOT / "org" / "projects" / project_id / "attachments"
            scope = f"projects/{project_id}"
        else:
            attach_dir = ROOT / "attachments"
            scope = "staff"
    else:
        attach_dir = ROOT / "attachments"
        scope = "staff"
    attach_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for file_data in files:
        filename = file_data.get("filename", "")
        content = file_data.get("content", b"")
        if not filename:
            continue
        if len(content) > MAX_ATTACHMENT_SIZE:
            return [], f"File too large: {filename} ({len(content)} bytes, max {MAX_ATTACHMENT_SIZE})"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return [], f"File type not allowed: {filename}"
        safe_name = re.sub(r"[^\w\s.-]", "_", filename)
        base, ext_part = os.path.splitext(safe_name)
        counter = 0
        dest_name = safe_name
        dest_path = attach_dir / dest_name
        while dest_path.exists():
            counter += 1
            dest_name = f"{base}_{counter}{ext_part}"
            dest_path = attach_dir / dest_name
        try:
            dest_path.write_bytes(content)
            rel_id = f"{scope}/{dest_name}"
            saved.append({
                "filename": filename,
                "path": str(dest_path),
                "id": rel_id,
                "size": len(content)
            })
        except (OSError, IOError) as err:
            return [], f"Failed to save {filename}: {err}"
    return saved, None


def _chat_context(data: dict, files: list | None = None) -> tuple:
    message = str(data.get("message") or "").strip()
    if not message and files:
        message = "(attachment)"
    folder = data.get("folder")
    preset = data.get("preset")
    project_id = data.get("project_id")
    if isinstance(project_id, str) and project_id.strip():
        org = ensure_org()
        match = next((row for row in org["projects"] if row.get("id") == project_id), None)
        if match and match.get("folder"):
            folder = match["folder"]
    worker_raw = data.get("worker_id")
    worker_id = worker_raw.strip() if isinstance(worker_raw, str) and worker_raw.strip() else None
    pid = project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
    requested = preset if isinstance(preset, str) and preset in PRESET_ENGINE else None
    attachments, err = _save_attachments(files or [], pid)
    if err:
        raise ValueError(err)
    return message, folder, requested, pid, worker_id, attachments


def _record_job(job: dict, message: str, project_id: str | None, worker_id: str | None, quote: str = "", attachments: list | None = None, actor: dict | None = None) -> None:
    key = thread_key(project_id, worker_id)
    turn = {"role": "user", "text": redact_chat_login(message)}
    if actor:
        turn["actor"] = actor
    cleaned = redact_chat_login(str(quote or "").strip())
    cleaned = " ".join(cleaned.split())[:400]
    if cleaned:
        turn["quote"] = cleaned
    if attachments:
        turn["attachments"] = [{"filename": a["filename"], "id": a["id"], "size": a["size"]} for a in attachments]
    append_turn(key, turn)
    append_turn(key, {"role": "bot", "job": job})


_CRON_INGEST_AT = 0.0
_CRON_COOLDOWN_SEC = 60.0


def _parse_index_fields(text: str) -> dict:
    """Parse Now/Last/Next/Blocker from INDEX markdown."""
    fields = {}
    for label in ("Now", "Last", "Next", "Blocker"):
        match = re.search(rf"^{label}:\s*(.*)$", text or "", re.M)
        fields[label.lower()] = (match.group(1).strip() if match else "") or "—"
    return fields


def _search_memory(query: str, project_id: str | None = None, limit: int = 50) -> dict:
    """Search across INDEX text and recent job RESULT snippets."""
    # Always parse INDEX fields, even for empty query
    if project_id:
        from .org import read_project_index
        index_text = read_project_index(project_id)
    else:
        index_text = read_index()
    
    index_fields = _parse_index_fields(index_text)
    
    query_lower = query.lower().strip()
    if not query_lower:
        return {"results": [], "index_fields": index_fields, "query": ""}
    
    results = []
    
    # Search INDEX
    if query_lower in index_text.lower():
        results.append({
            "type": "index",
            "source": "INDEX",
            "snippet": index_text[:500],
            "match": True
        })
    
    # Search recent job results
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    if project_id:
        jobs = [job for job in jobs if job.get("project_id") == project_id]
    
    for job in jobs[:limit]:
        text_field = str(job.get("text") or "")
        if query_lower in text_field.lower():
            snippet = re.sub(r"\s+", " ", text_field)[:300]
            results.append({
                "type": "job",
                "source": f"{job.get('engine', 'unknown')} · {job.get('id', '')}",
                "snippet": snippet,
                "at": job.get("at", ""),
                "job_id": job.get("id", ""),
                "engine": job.get("engine", ""),
                "worker_id": job.get("worker_id"),
                "project_id": job.get("project_id")
            })
    
    return {
        "results": results[:30],
        "index_fields": index_fields,
        "query": query
    }


def _activity(*, ingest_cron: bool = False, project_id: str | None = None) -> dict:
    from .spend import check_cap_alerts
    
    keyring = public_keyring()
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    index = read_index()
    now_match = re.search(r"^Now:\s*(.*)$", index or "", re.M)
    cron_jobs = []
    global _CRON_INGEST_AT
    if ingest_cron:
        now = time.time()
        if now - _CRON_INGEST_AT >= _CRON_COOLDOWN_SEC:
            _CRON_INGEST_AT = now
            try:
                cron_jobs = ingest_cron_runs()
            except Exception:
                cron_jobs = []
    names = {str(row.get("id") or ""): str(row.get("name") or "") for row in (ensure_org().get("projects") or [])}
    needs = []
    for item in pending_approvals():
        row = dict(item)
        row["name"] = names.get(row.get("project_id") or "") or "Chief of Staff"
        needs.append(row)
    
    # Check for spend cap alerts
    cfg = load_config()
    settings = load_settings()
    try:
        spend_alerts = check_cap_alerts(
            float(cfg.get("spend_cap_usd", 5.0)),
            cfg.get("spend_cap_period", "week"),
            policy=settings.get("spend_policy")
        )
        cap_notices = spend_alerts.get("alerts") or []
    except Exception:
        cap_notices = []
    if project_id:
        jobs = filter_jobs(jobs, project_id)
        needs = [row for row in needs if str(row.get("project_id") or "") == str(project_id)]
        cron_jobs = [row for row in cron_jobs if str(row.get("project_id") or "") == str(project_id)]
        cap_notices = [
            row for row in cap_notices if str(row.get("ceo_id") or row.get("project_id") or "") == str(project_id)
        ]

    return {
        "now": (now_match.group(1).strip() if now_match else ""),
        "jobs": [public_job(job) for job in jobs[:30]],
        "needs_you": needs,
        "cron_jobs": cron_jobs,
        "cap_notices": cap_notices,
        "has_key": _has_key(keyring),
        "opencode_running": bool(opencode_web_status().get("running")),
        "hermes_running": bool(hermes_dash_status().get("running")),
    }


def _public_config() -> dict:
    ensure_chat_model()
    cfg = load_config()
    spend = spend_summary(cfg["spend_cap_usd"], cfg["spend_cap_period"])
    engines = detect()
    keyring = public_keyring()
    has_key = _has_key(keyring)
    operator = public_operator()
    return {
        "work_dir": cfg["work_dir"],
        "work_dir_ok": cfg["work_dir_ok"],
        "first_run_done": cfg["first_run_done"],
        "has_key": has_key,
        "setup_needed": (not cfg["first_run_done"]) or (not has_key),
        "spend_cap_usd": cfg["spend_cap_usd"],
        "spend_cap_period": cfg["spend_cap_period"],
        "spend": spend,
        "credit": CREDIT,
        "engines": engines,
        "brains": list_brains(),
        "index": read_index(),
        "preset_engines": PRESET_ENGINE,
        "opencode_web": opencode_web_status(),
        "hermes_dash": hermes_dash_status(),
        "connected_providers": connected_provider_ids(),
        "models": cfg.get("models"),
        "default_provider": cfg.get("default_provider"),
        "mcp_github": cfg.get("mcp_github"),
        "seats": cfg.get("seats"),
        "profile_account_id": cfg.get("profile_account_id") or "",
        "spend_policy": cfg.get("spend_policy"),
        "org": ensure_org(),
        "keyring": keyring,
        "activity": _activity(),
        "operator_name": operator["operator_name"],
        "has_pin": operator["has_pin"],
        "has_license": operator["has_license"],
        "needs_unlock": False,
        "hermes_instances": public_instances(),
        "actor": "owner",
        "share": None,
    }


def _member_config(member: dict) -> dict:
    payload = _public_config()
    pid = member_project_id(member)
    operator = public_operator()
    activity = _activity(project_id=pid)
    if not member_can(member, "jobs_view"):
        activity["jobs"] = []
        activity["cron_jobs"] = []
    if not member_can(member, "approve_needs_you"):
        activity["needs_you"] = []
    cfg = load_config()
    cap = cfg["spend_cap_usd"]
    project_cap = project_tools(pid).get("spend_cap_usd") if pid else None
    if project_cap is not None:
        cap = project_cap
    org = filter_org(payload.get("org") or {}, pid)
    payload.update(
        {
            "actor": "collaborator",
            "share": {
                "member": public_member(member),
                "owner_name": operator.get("operator_name") or "Owner",
                "keys_connected": bool(payload.get("has_key")),
            },
            "org": org,
            "index": org.get("index") or "",
            "activity": activity,
            "keyring": {"accounts": [], "logins": [], "blocked": []},
            "hermes_instances": [],
            "brains": {},
            "has_license": False,
            "has_pin": False,
            "operator_name": public_member(member).get("display_name") or "Collaborator",
            "work_dir": "",
            "spend": spend_summary(float(cap), cfg["spend_cap_period"], project_id=pid),
            "setup_needed": False,
        }
    )
    if not member_can(member, "engines_view"):
        payload["opencode_web"] = {"ok": False, "running": False}
        payload["hermes_dash"] = {"ok": False, "running": False}
    return payload


def _locked_payload() -> dict:
    operator = public_operator()
    return {
        "needs_unlock": True,
        "has_pin": True,
        "has_license": operator["has_license"],
        "operator_name": operator["operator_name"],
        "credit": CREDIT,
        "first_run_done": True,
        "has_key": True,
        "setup_needed": False,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[openbot] {self.address_string()} {fmt % args}")

    def _unlocked(self) -> bool:
        return self._owner_unlocked() or bool(self._member())

    def _bearer_token(self) -> str:
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            parts = auth.split(None, 1)
            if len(parts) == 2:
                return parts[1].strip()
        return ""

    def _owner_token(self) -> str:
        return self._bearer_token() or _cookie_value(self.headers.get("Cookie"), "openbot_unlock")

    def _share_token(self) -> str:
        return self._bearer_token() or _cookie_value(self.headers.get("Cookie"), "openbot_share")

    def _member(self) -> dict | None:
        return member_from_session(self._share_token())

    def _owner_unlocked(self) -> bool:
        settings = load_settings()
        if settings.get("pin_hash"):
            token = self._owner_token()
            with _UNLOCK_LOCK:
                return bool(token) and token in _UNLOCK_TOKENS
        return self._member() is None

    def _actor_row(self) -> dict | None:
        if self._owner_unlocked():
            return None
        return self._member()

    def _config_payload(self) -> dict:
        if self._owner_unlocked():
            return _public_config()
        member = self._member()
        if member:
            touch_member(str(member.get("id") or ""))
            return _member_config(member)
        return _locked_payload()

    def _lock_api(self, path: str, method: str) -> bool:
        if path.startswith("/opencode/") or path.startswith("/hermes/"):
            if self._member() and not member_can(self._member(), "engines_view"):
                return True
            return not self._unlocked()
        if not path.startswith("/api/"):
            return False
        if method == "GET" and path == "/api/health":
            return False
        if method == "GET" and SHARE_INVITE_TOKEN.match(path):
            return False
        if method == "POST" and path in {"/api/unlock", "/api/share/redeem", "/api/share/unlock"}:
            return False
        return not self._unlocked()

    def _forbid(self, error: str, code: int = 403):
        return self._json(code, {"error": error, "ok": False})

    def _require_owner(self) -> bool:
        if self._owner_unlocked():
            return False
        self._forbid("owner only")
        return True

    def _require_perm(self, permission: str, project_id: str | None = None) -> bool:
        if self._owner_unlocked():
            return False
        row = self._member()
        if row is None:
            self._json(403, _locked_payload())
            return True
        if project_id is not None and not allows_project(row, project_id):
            self._forbid("not on this CEO")
            return True
        if permission and not member_can(row, permission):
            self._forbid("not allowed on this share")
            return True
        return False

    def _share_cookie(self, token: str) -> str:
        return f"openbot_share={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000"

    def _clear_share_cookie(self) -> str:
        return "openbot_share=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"

    def _chat_guard(self, pid: str | None, requested: str | None):
        member = self._actor_row()
        if member:
            if str(member.get("seats_mode") or "") == "chat_only":
                requested = None
            err = check_job_run(member, pid, requested)
            if err:
                self._forbid(err)
                return None, None
        return requested, actor_stamp(member)

    def _json(self, code: int, payload: dict, set_cookie: str | None = None):
        raw = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            if set_cookie:
                self.send_header("Set-Cookie", set_cookie)
            self.end_headers()
            self.wfile.write(raw)
        except Exception as e:
            self.log_error(f"_json: {e}")

    def _proxy(self, host: str, port: int, target_path: str):
        """Proxy requests to localhost engines so they work from mobile."""
        import http.client
        
        try:
            # Build query string if present
            parsed = urlparse(self.path)
            full_path = target_path or "/"
            if parsed.query:
                full_path = f"{full_path}?{parsed.query}"
            
            # Read request body for POST/PUT
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Connect to backend
            conn = http.client.HTTPConnection(host, port, timeout=15)
            
            # Build headers (exclude hop-by-hop headers)
            headers = {}
            for key, value in self.headers.items():
                lower = key.lower()
                if lower not in ("host", "connection", "transfer-encoding", "upgrade"):
                    headers[key] = value
            headers["Host"] = f"{host}:{port}"
            
            # Make request
            conn.request(self.command, full_path, body=body, headers=headers)
            response = conn.getresponse()
            
            # Check for websocket upgrade (unsupported by this simple proxy)
            if response.status == 101 or "upgrade" in response.getheaders():
                conn.close()
                return self._proxy_fallback(f"http://{host}:{port}{target_path}")

            content_type = response.getheader("Content-Type") or ""
            if port == 4096 and "html" in content_type.lower():
                blob = inject_opencode_tree(response.read(), content_type)
                self.send_response(response.status)
                for header, value in response.getheaders():
                    if header.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(header, value)
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
            else:
                self.send_response(response.status)
                for header, value in response.getheaders():
                    if header.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(header, value)
                self.end_headers()
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

            conn.close()
        except Exception as e:
            self.log_error(f"_proxy: {e}")
            try:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                msg = f"Proxy error: {str(e)}\n"
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg.encode("utf-8"))
            except Exception:
                pass

    def _proxy_fallback(self, direct_url: str):
        """Fallback UI when proxy doesn't support websockets or engine is down."""
        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Engine Dashboard</title>
  <style>
    body {{
      margin: 0;
      padding: 20px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #100f0d;
      color: #f3ead8;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }}
    .card {{
      max-width: 480px;
      padding: 24px;
      background: #1c1a16;
      border: 1px solid #2c2822;
      border-radius: 12px;
      text-align: center;
    }}
    h1 {{
      margin: 0 0 16px;
      font-size: 18px;
      color: #c9a66b;
    }}
    p {{
      margin: 0 0 20px;
      font-size: 14px;
      line-height: 1.5;
      color: #8f8270;
    }}
    a {{
      display: inline-block;
      padding: 10px 20px;
      background: #c9a66b;
      color: #1a140c;
      text-decoration: none;
      border-radius: 8px;
      font-weight: 600;
      font-size: 14px;
    }}
    a:hover {{
      background: #d4b47a;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Engine Dashboard</h1>
    <p>This dashboard requires features not supported by the simple proxy. Open it directly on your machine:</p>
    <a href="{direct_url}" target="_blank" rel="noopener">Open Dashboard</a>
  </div>
</body>
</html>"""
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.log_error(f"_proxy_fallback: {e}")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def _unlock_cookie(self, token: str) -> str:
        return f"openbot_unlock={token}; HttpOnly; SameSite=Lax; Path=/"

    def _serve_attachment(self, path: str) -> None:
        from .store import ROOT
        rel_path = path.replace("/api/attachments/", "")
        if ".." in rel_path or rel_path.startswith("/"):
            return self._json(403, {"error": "invalid path"})
        parts = rel_path.split("/", 1)
        if len(parts) < 2:
            return self._json(404, {"error": "not found"})
        scope, filename = parts[0], parts[1]
        if scope == "staff":
            file_path = ROOT / "attachments" / filename
        elif scope == "projects":
            rest = filename.split("/", 1)
            if len(rest) < 2:
                return self._json(404, {"error": "not found"})
            project_id, name = rest[0], rest[1]
            file_path = ROOT / "org" / "projects" / project_id / "attachments" / name
        else:
            return self._json(404, {"error": "not found"})
        if not file_path.exists() or not file_path.is_file():
            return self._json(404, {"error": "not found"})
        try:
            content = file_path.read_bytes()
            ext = file_path.suffix.lower()
            content_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp",
                ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
                ".json": "application/json", ".html": "text/html",
                ".mp4": "video/mp4", ".webm": "video/webm"
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except (OSError, IOError):
            return self._json(500, {"error": "read failed"})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise json.JSONDecodeError("object required", "", 0)
        return data

    def _parse_multipart(self) -> tuple[dict, list]:
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return {}, []
        boundary = None
        for part in ctype.split(";"):
            if "boundary=" in part:
                boundary = part.split("=", 1)[1].strip()
                break
        if not boundary:
            return {}, []
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}, []
        body = self.rfile.read(length)
        fields = {}
        files = []
        boundary_bytes = ("--" + boundary).encode()
        parts = body.split(boundary_bytes)
        for part in parts:
            if not part or part == b"--\r\n" or part == b"--":
                continue
            if b"\r\n\r\n" not in part:
                continue
            headers_raw, content = part.split(b"\r\n\r\n", 1)
            content = content.rstrip(b"\r\n")
            headers_str = headers_raw.decode("utf-8", errors="ignore")
            disp_line = ""
            for line in headers_str.split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    disp_line = line
                    break
            if not disp_line:
                continue
            name_match = re.search(r'name="([^"]+)"', disp_line)
            if not name_match:
                continue
            field_name = name_match.group(1)
            filename_match = re.search(r'filename="([^"]+)"', disp_line)
            if filename_match:
                filename = filename_match.group(1)
                files.append({"name": field_name, "filename": filename, "content": content})
            else:
                fields[field_name] = content.decode("utf-8", errors="ignore")
        return fields, files

    def do_GET(self):
        path = urlparse(self.path).path
        
        # Proxy OpenCode web UI
        if path.startswith("/opencode/"):
            return self._proxy("127.0.0.1", 4096, path[len("/opencode"):])
        
        # Proxy Hermes dashboard
        if path.startswith("/hermes/"):
            return self._proxy("127.0.0.1", 9119, path[len("/hermes"):])
        
        if path == "/api/health":
            return self._json(200, {"ok": True, "credit": CREDIT, "engines": detect()})
        invite_peek = SHARE_INVITE_TOKEN.match(path)
        if invite_peek:
            try:
                return self._json(200, peek_invite(invite_peek.group(1)))
            except ValueError as err:
                return self._json(404, {"error": str(err), "ok": False})
        if path in {"/api/index", "/api/config"}:
            if not self._unlocked():
                return self._json(200, _locked_payload())
            return self._json(200, self._config_payload())
        if self._lock_api(path, "GET"):
            return self._json(403, _locked_payload())
        if path == "/api/share":
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            pid = (qs.get("project_id") or [""])[0].strip()
            if not pid:
                return self._json(400, {"error": "CEO required"})
            return self._json(200, project_share(pid))
        if path == "/api/share/me":
            member = self._member()
            if member is None:
                return self._forbid("not a collaborator")
            return self._json(200, {"member": public_member(member), "ok": True})
        if path == "/api/engines":
            return self._json(200, detect())
        if path == "/api/spend":
            cfg = load_config()
            qs = parse_qs(urlparse(self.path).query)
            pid = (qs.get("project_id") or [""])[0].strip() or None
            member = self._actor_row()
            if member:
                pid = member_project_id(member)
            if member and pid and not allows_project(member, pid):
                return self._forbid("not on this CEO")
            cap = cfg["spend_cap_usd"]
            if pid:
                project_cap = project_tools(pid).get("spend_cap_usd")
                if project_cap is not None:
                    cap = project_cap
            return self._json(
                200,
                spend_summary(float(cap), cfg["spend_cap_period"], project_id=pid),
            )
        if path == "/api/brains":
            if self._require_owner():
                return None
            return self._json(200, {"brains": list_brains()})
        brain = BRAIN_PATH.match(path)
        if brain:
            if self._require_owner():
                return None
            name = brain.group(1)
            return self._json(200, {"name": name, "text": read_brain(name), "engine": PRESET_ENGINE[name]})
        if path == "/api/jobs":
            jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
            member = self._actor_row()
            if member:
                jobs = filter_jobs(jobs, member_project_id(member))
                if not member_can(member, "jobs_view"):
                    jobs = []
            return self._json(200, {"jobs": [public_job(job) for job in jobs[:30]]})
        if path == "/api/activity":
            member = self._actor_row()
            pid = member_project_id(member) if member else None
            activity = _activity(ingest_cron=True, project_id=pid)
            if member and not member_can(member, "jobs_view"):
                activity["jobs"] = []
                activity["cron_jobs"] = []
            if member and not member_can(member, "approve_needs_you"):
                activity["needs_you"] = []
            return self._json(200, activity)
        if path.startswith("/api/jobs/") and path.endswith("/log"):
            if self._require_perm("jobs_view"):
                return None
            job_id = path.split("/")[3]
            job_row = read_job(job_id) or {}
            member = self._actor_row()
            if member and not allows_project(member, str(job_row.get("project_id") or "")):
                return self._forbid("not on this CEO")
            from .store import read_session_log
            log = read_session_log(job_id)
            if log is None:
                return self._json(404, {"error": "Log not found"})
            return self._json(200, {"job_id": job_id, "log": log})
        if path == "/api/onboarding/status":
            if self._require_owner():
                return None
            if not self._unlocked():
                return self._json(200, _locked_payload())
            status = onboarding_status()
            return self._json(200, status)
        if path == "/api/thread":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            worker_id = (qs.get("worker_id") or [""])[0].strip() or None
            member = self._actor_row()
            if member and not project_id:
                project_id = member_project_id(member)
            if self._require_perm("chat_read", project_id):
                return None
            key = thread_key(project_id, worker_id)
            return self._json(200, {"preset": key, "turns": read_thread(key)})
        if path == "/api/skills":
            if self._require_perm("engines_view"):
                return None
            return self._json(200, skills_list())
        if path == "/api/mcp/catalog":
            if self._require_perm("engines_view"):
                return None
            return self._json(200, mcp_catalog())
        if path == "/api/connectors/catalog":
            if self._require_owner():
                return None
            skills = skills_list()
            mcp = mcp_catalog()
            return self._json(200, {
                "skills": skills.get("skills") or [],
                "skills_ok": skills.get("ok", False),
                "popular_skills": skills.get("popular") or [],
                "mcp": mcp.get("items") or [],
                "mcp_ok": mcp.get("ok", False)
            })
        if path == "/api/engines/opencode/web":
            if self._require_perm("engines_view"):
                return None
            return self._json(200, opencode_web_status())
        if path == "/api/engines/hermes/dashboard":
            if self._require_perm("engines_view"):
                return None
            return self._json(200, hermes_dash_status())
        if path == "/api/providers":
            if self._require_owner():
                return None
            return self._json(200, provider_status())
        if path == "/api/catalog":
            if self._require_owner():
                return None
            ensure_chat_model()
            return self._json(200, public_catalog())
        if path == "/api/org":
            org = ensure_org()
            member = self._actor_row()
            if member:
                org = filter_org(org, member_project_id(member))
            return self._json(200, org)
        if path == "/api/spend/dashboard":
            if self._require_owner():
                return None
            from .spend import check_cap_alerts, per_ceo_breakdown, weekly_trend
            
            cfg = load_config()
            settings = load_settings()
            cap_usd = float(cfg.get("spend_cap_usd", 5.0))
            period = cfg.get("spend_cap_period", "week")
            policy = settings.get("spend_policy")
            
            breakdown = per_ceo_breakdown(cap_usd, period, policy=policy)
            alerts = check_cap_alerts(cap_usd, period, policy=policy)
            
            # Trend data for each CEO
            trends = {}
            for ceo in breakdown["ceos"]:
                trends[ceo["id"]] = weekly_trend(project_id=ceo["id"], policy=policy)
            
            return self._json(200, {
                "breakdown": breakdown,
                "alerts": alerts,
                "trends": trends,
                "cap_usd": cap_usd,
                "period": period,
            })
        if path == "/api/memory/search":
            qs = parse_qs(urlparse(self.path).query)
            query = (qs.get("q") or [""])[0].strip()
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            member = self._actor_row()
            if member:
                project_id = member_project_id(member)
            if self._require_perm("chat_read", project_id):
                return None
            return self._json(200, _search_memory(query, project_id))
        if path == "/api/memory/fields":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            member = self._actor_row()
            if member:
                project_id = member_project_id(member)
            if self._require_perm("chat_read", project_id):
                return None
            if project_id:
                from .org import read_project_index
                index_text = read_project_index(project_id)
            else:
                index_text = read_index()
            return self._json(200, {"index_fields": _parse_index_fields(index_text)})
        
        if path == "/api/queue/status":
            from .bus import load_open_handoffs
            org_data = ensure_org()
            member = self._actor_row()
            allowed = member_project_id(member) if member else None
            
            # Build queue status per CEO
            queue_status = []
            
            # Staff queue
            if allowed is None:
                staff_handoffs = load_open_handoffs(None, limit=100)
                staff_open = [h for h in staff_handoffs if h["status"] == "open"]
                if staff_open:
                    queue_status.append({
                        "project_id": None,
                        "name": "Chief of Staff",
                        "queued_count": len(staff_open),
                        "handoffs": staff_open[:5],
                    })
            
            # Per-CEO queues
            for project in org_data.get("projects") or []:
                pid = project.get("id")
                if not pid:
                    continue
                if allowed is not None and pid != allowed:
                    continue
                handoffs = load_open_handoffs(pid, limit=100)
                open_handoffs = [h for h in handoffs if h["status"] == "open"]
                if open_handoffs:
                    queue_status.append({
                        "project_id": pid,
                        "name": project.get("name") or pid,
                        "queued_count": len(open_handoffs),
                        "handoffs": open_handoffs[:5],
                    })
            
            # Active workers
            workers = active_workers()
            
            return self._json(200, {
                "queue_status": queue_status,
                "active_workers": workers,
                "total_queued": sum(q["queued_count"] for q in queue_status),
            })
        
        channel = PROJECT_CHANNEL.match(path)
        if channel:
            if self._require_owner():
                return None
            pid = channel.group(1)
            org = ensure_org()
            row = next((item for item in org.get("projects") or [] if item.get("id") == pid), None)
            if not row:
                return self._json(404, {"error": "CEO not found"})
            tools = row.get("tools") or {}
            return self._json(
                200,
                public_channel(tools.get("hermes_home"), tools.get("hermes_session_id")),
            )
        if path == "/api/git":
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            folder = (qs.get("folder") or [""])[0].strip()
            pid = (qs.get("project_id") or [""])[0].strip()
            if pid and not folder:
                org = ensure_org()
                match = next((row for row in org["projects"] if row.get("id") == pid), None)
                folder = str((match or {}).get("folder") or org.get("folder") or "")
            if not folder:
                folder = str(ensure_org().get("folder") or load_config().get("work_dir") or "")
            return self._json(200, git_status(folder))
        if path == "/api/keys":
            if self._require_owner():
                return None
            return self._json(200, public_keyring())
        if path == "/api/hermes/instances":
            if self._require_owner():
                return None
            return self._json(200, {"instances": public_instances()})
        instance_sessions = INSTANCE_SESSIONS.match(path)
        if instance_sessions:
            if self._require_owner():
                return None
            try:
                return self._json(200, {"sessions": list_sessions(instance_sessions.group(1))})
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path.startswith("/api/attachments/"):
            return self._serve_attachment(path)
        if path == "/api/routines":
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .routines import list_routines
            result = list_routines(project_id, include_hermes=True)
            return self._json(200, result)
        if path == "/api/routines/templates":
            if self._require_owner():
                return None
            from .routine_templates import get_routine_templates
            return self._json(200, {"templates": get_routine_templates()})
        if path == "/api/hermes/gateway/status":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            if self._require_perm("engines_view", project_id):
                return None
            from .org import project_tools
            
            tools = project_tools(project_id) if project_id else {}
            hermes_home = str(tools.get("hermes_home") or "").strip() or None
            
            status = gateway_status(hermes_home, timeout=3)
            status["project_id"] = project_id
            return self._json(200, status)
        if path == "/api/selfbuild/status":
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .selfbuild import self_build_status
            return self._json(200, self_build_status(project_id))
        routine = ROUTINE_ID.match(path)
        if routine:
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .routines import read_routine
            data = read_routine(routine.group(1), project_id)
            if not data:
                return self._json(404, {"error": "routine not found"})
            return self._json(200, data)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        
        # Proxy OpenCode web UI
        if path.startswith("/opencode/"):
            return self._proxy("127.0.0.1", 4096, path[len("/opencode"):])
        
        # Proxy Hermes dashboard
        if path.startswith("/hermes/"):
            return self._proxy("127.0.0.1", 9119, path[len("/hermes"):])
        
        if path == "/api/onboarding/test-job":
            if self._require_owner():
                return None
            if not self._unlocked():
                return self._json(403, {"error": "unlock required"})
            try:
                data = self._read_json()
                project_id = data.get("project_id") or None
                worker_id = data.get("worker_id") or None
                
                from .config import load_config
                
                prompt = test_job_prompt()
                cfg = load_config()
                
                # Resolve folder: project folder if present, else work_dir
                folder = None
                if project_id:
                    org_data = ensure_org()
                    project = next((p for p in org_data.get("projects", []) if p.get("id") == project_id), None)
                    if project and project.get("folder"):
                        project_folder = Path(project["folder"]).expanduser()
                        if project_folder.is_dir():
                            folder = str(project_folder)
                
                if not folder:
                    if cfg["work_dir_ok"]:
                        folder = cfg["work_dir"]
                    else:
                        return self._json(400, {"error": "no valid work directory configured"})
                
                job = handle(
                    message=prompt,
                    folder=folder,
                    preset="builder",
                    project_id=project_id,
                    worker_id=worker_id,
                    quote="",
                    attachments=None,
                )
                
                _record_job(job, prompt, project_id, worker_id, quote="", attachments=None)
                job["activity"] = _activity()
                
                return self._json(200, {
                    "ok": True,
                    "job": job,
                    "message": "Test job complete"
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._json(500, {"error": str(e)})
        
        ctype = self.headers.get("Content-Type", "")
        is_multipart = ctype.startswith("multipart/form-data")
        
        try:
            if is_multipart:
                data, files = self._parse_multipart()
            else:
                data = self._read_json()
                files = []
        except (json.JSONDecodeError, ValueError):
            return self._json(400, {"error": "invalid request"})

        if path == "/api/share/redeem":
            try:
                joined = redeem_invite(
                    str(data.get("token") or ""),
                    str(data.get("display_name") or ""),
                    str(data.get("secret") or ""),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err), "ok": False})
            member = member_from_session(joined["token"])
            payload = _member_config(member) if member else {}
            payload.update(joined)
            payload["ok"] = True
            return self._json(200, payload, set_cookie=self._share_cookie(joined["token"]))
        if path == "/api/share/unlock":
            try:
                joined = unlock_member(str(data.get("member_id") or ""), str(data.get("secret") or ""))
            except ValueError as err:
                return self._json(403, {"error": str(err), "needs_unlock": True})
            member = member_from_session(joined["token"])
            payload = _member_config(member) if member else {}
            payload.update(joined)
            payload["ok"] = True
            return self._json(200, payload, set_cookie=self._share_cookie(joined["token"]))

        if self._lock_api(path, "POST"):
            return self._json(403, _locked_payload())

        if path == "/api/share/invites":
            if self._require_owner():
                return None
            try:
                invite = create_invite(
                    str(data.get("project_id") or ""),
                    permissions=data.get("permissions"),
                    expires_days=data.get("expires_days"),
                    max_uses=int(data.get("max_uses") or 1),
                    spend_ceiling_usd_day=data.get("spend_ceiling_usd_day"),
                    require_approval_over_usd=data.get("require_approval_over_usd"),
                    seats_mode=str(data.get("seats_mode") or "inherit"),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            origin = str(data.get("origin") or "").strip().rstrip("/")
            token = invite.get("token") or ""
            invite["url"] = f"{origin}/?invite={token}" if origin else f"/?invite={token}"
            return self._json(200, invite)
        if path == "/api/share/me":
            member = self._member()
            if member is None:
                return self._forbid("not a collaborator")
            mid = str(member.get("id") or "")
            if data.get("leave"):
                try:
                    remove_member(mid)
                except ValueError as err:
                    return self._json(400, {"error": str(err)})
                return self._json(200, {"ok": True, "left": True}, set_cookie=self._clear_share_cookie())
            try:
                patch = {}
                if "display_name" in data:
                    patch["display_name"] = data.get("display_name")
                if patch:
                    patch_member(mid, patch)
                secret = str(data.get("secret") or "")
                if secret:
                    set_member_secret(mid, secret)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            row = get_member(mid) or member
            return self._json(200, {"ok": True, "member": public_member(row)})
        member_post = SHARE_MEMBER_ID.match(path)
        if member_post:
            if self._require_owner():
                return None
            try:
                if "pause" in data:
                    row = pause_member(member_post.group(1), bool(data.get("pause")))
                else:
                    row = patch_member(member_post.group(1), data)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            return self._json(200, {"ok": True, "member": row})

        if path == "/api/chat":
            try:
                message, folder, requested, pid, worker_id, attachments = _chat_context(data, files)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            requested, actor = self._chat_guard(pid, requested)
            if actor is None and self._actor_row() is not None:
                return None
            chain_ctx = data.get("chain_context") if isinstance(data.get("chain_context"), dict) else None
            
            # Check for multi-spawn
            from .multispawn import multi_spawn_handle
            multi_result = multi_spawn_handle(
                message, folder, pid, worker_id,
                quote=str(data.get("quote") or ""),
                attachments=attachments
            )
            
            if multi_result:
                # Multi-spawn executed
                job = multi_result
                if actor:
                    job["actor"] = actor
            else:
                # Normal single-seat routing
                job = handle(message, folder, requested, pid, worker_id, quote=str(data.get("quote") or ""), chain_context=chain_ctx, attachments=attachments, actor=actor)
            
            _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""), attachments=attachments, actor=actor)
            job["activity"] = _activity(project_id=pid if self._actor_row() else None)
            return self._json(200, job)
        if path == "/api/chat/stream":
            try:
                message, folder, requested, pid, worker_id, attachments = _chat_context(data, files)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            requested, actor = self._chat_guard(pid, requested)
            if actor is None and self._actor_row() is not None:
                return None
            run_id = uuid.uuid4().hex[:12]
            live_start(run_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(event: str, payload: dict) -> None:
                blob = json.dumps(payload, default=str)
                try:
                    self.wfile.write(f"event: {event}\ndata: {blob}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

            emit("start", {"id": run_id})

            def on_delta(chunk: str) -> None:
                text = str(chunk or "")
                if text:
                    emit("delta", {"text": text})

            def on_progress(chunk: str, lane: str | None = None) -> None:
                text = str(chunk or "").strip()
                payload = {}
                if text:
                    payload["text"] = text
                if lane:
                    payload["lane"] = lane
                if payload:
                    emit("progress", payload)

            try:
                chain_ctx = data.get("chain_context") if isinstance(data.get("chain_context"), dict) else None
                
                # Check for multi-spawn
                from .multispawn import multi_spawn_handle
                multi_result = multi_spawn_handle(
                    message, folder, pid, worker_id,
                    on_delta=on_delta,
                    on_progress=on_progress,
                    run_id=run_id,
                    quote=str(data.get("quote") or ""),
                    attachments=attachments
                )
                
                if multi_result:
                    # Multi-spawn executed
                    job = multi_result
                    if actor:
                        job["actor"] = actor
                else:
                    # Normal single-seat routing
                    job = handle(
                        message,
                        folder,
                        requested,
                        pid,
                        worker_id,
                        on_delta=on_delta,
                        on_progress=on_progress,
                        run_id=run_id,
                        quote=str(data.get("quote") or ""),
                        chain_context=chain_ctx,
                        attachments=attachments,
                        actor=actor,
                    )
                
                _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""), attachments=attachments, actor=actor)
                job["activity"] = _activity(project_id=pid if self._actor_row() else None)
                emit("done", job)
            except Exception as err:
                try:
                    emit("error", {"error": str(err)})
                    emit(
                        "done",
                        {
                            "id": run_id,
                            "text": f"That turn failed: {err}",
                            "engine": "board",
                            "preset": "cos",
                            "talk": True,
                            "keep_going": False,
                        },
                    )
                except OSError:
                    pass
            finally:
                live_finish(run_id)
            return None
        run_stop = RUN_STOP.match(path)
        if run_stop:
            ok = live_stop(run_stop.group(1))
            return self._json(200, {"ok": ok, "id": run_stop.group(1)})

        if path == "/api/unlock":
            pin = str(data.get("pin") or "")
            if not load_settings().get("pin_hash"):
                return self._json(200, self._config_payload())
            if not verify_pin(pin):
                return self._json(403, {"error": "wrong PIN", "needs_unlock": True})
            token = _mint_unlock()
            payload = _public_config()
            payload["token"] = token
            return self._json(200, payload, set_cookie=self._unlock_cookie(token))

        if path == "/api/config":
            if self._require_owner():
                return None
            try:
                if "work_dir" in data and data["work_dir"] is not None:
                    save_work_dir(str(data["work_dir"]).strip())
                if "spend_cap_usd" in data and data["spend_cap_usd"] is not None:
                    period = data.get("spend_cap_period")
                    save_spend_cap(float(data["spend_cap_usd"]), str(period) if period else None)
                settings_keys = (
                    "default_provider",
                    "mcp_github",
                    "models",
                    "seats",
                    "profile_account_id",
                    "hermes_skills",
                    "connectors",
                    "operator_name",
                    "pin",
                    "clear_pin",
                    "license_key",
                    "spend_policy",
                    "enable_self_build",
                )
                if any(key in data for key in settings_keys):
                    if isinstance(data.get("seats"), dict):
                        validate_seats(data["seats"])
                    save_settings(data)
                    # If enable_self_build changed, ensure/disable routine
                    if "enable_self_build" in data:
                        from .selfbuild import ensure_self_build_routine
                        ensure_self_build_routine(project_id=None)
                    account_id = str(data.get("profile_account_id") or "").strip()
                    if account_id:
                        from .keyring import activate_account

                        try:
                            activate_account(account_id)
                        except ValueError:
                            pass
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            cookie = None
            if isinstance(data.get("pin"), str) and data.get("pin"):
                cookie = self._unlock_cookie(_mint_unlock())
            return self._json(200, _public_config(), set_cookie=cookie)

        if path == "/api/engines/opencode/web":
            if self._require_perm("engines_view"):
                return None
            folder = str(data.get("folder") or "").strip() or None
            return self._json(200, start_opencode_web(folder))
        if path == "/api/engines/hermes/dashboard":
            if self._require_perm("engines_view"):
                return None
            home = str(data.get("hermes_home") or "").strip() or None
            result = start_hermes_dashboard(home)
            return self._json(200 if result.get("ok") else 400, result)
        if path == "/api/engines/hermes/open":
            if self._require_owner():
                return None
            result = open_hermes()
            return self._json(200 if result.get("ok") else 400, result)
        if path == "/api/org/projects":
            if self._require_owner():
                return None
            try:
                folder = str(data.get("folder") or "").strip() or None
                name = str(data.get("name") or "").strip() or None
                return self._json(200, add_project(folder, name))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        worker_add = WORKER_ADD.match(path)
        if worker_add:
            if self._require_perm("workers_manage", worker_add.group(1)):
                return None
            try:
                return self._json(200, add_worker(worker_add.group(1), str(data.get("name") or "")))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        worker_patch = WORKER_DEL.match(path)
        if worker_patch:
            if self._require_perm("workers_manage", worker_patch.group(1)):
                return None
            try:
                return self._json(
                    200,
                    rename_worker(worker_patch.group(1), worker_patch.group(2), str(data.get("name") or "")),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        
        if path == "/api/memory/fields":
            project_id = str(data.get("project_id") or "").strip() or None
            if project_id:
                if self._require_perm("index_edit", project_id):
                    return None
            elif self._require_owner():
                return None
            label = str(data.get("label") or "").strip()
            value = str(data.get("value") or "").strip()
            if label not in ("Now", "Last", "Next", "Blocker"):
                return self._json(400, {"error": "invalid label"})
            try:
                patch_scope(project_id, None, label, value)
                if project_id:
                    from .org import read_project_index
                    index_text = read_project_index(project_id)
                else:
                    index_text = read_index()
                return self._json(200, {"index_fields": _parse_index_fields(index_text)})
            except Exception as err:
                return self._json(400, {"error": str(err)})
        
        if path == "/api/handoffs":
            project_id = str(data.get("project_id") or "").strip() or None
            member = self._actor_row()
            if member:
                project_id = member_project_id(member)
            if self._require_perm("jobs_view", project_id):
                return None
            from .bus import load_open_handoffs
            handoffs = load_open_handoffs(project_id, limit=50)
            return self._json(200, {"handoffs": handoffs})
        
        if path == "/api/handoff/create":
            task = str(data.get("task") or "").strip()
            project_id = str(data.get("project_id") or "").strip() or None
            if self._require_perm("jobs_run", project_id):
                return None
            from_seat = str(data.get("from_seat") or "").strip() or "cos"
            to_seat = str(data.get("to_seat") or "").strip()
            next_owner = str(data.get("next_owner") or "").strip()
            output = str(data.get("output") or "").strip()
            if not task or not to_seat:
                return self._json(400, {"error": "task and to_seat required"})
            from .bus import create_handoff
            result = create_handoff(task, project_id, from_seat, to_seat, next_owner, output)
            return self._json(200 if result["ok"] else 400, result)
        
        if path == "/api/handoff/claim":
            handoff_id = str(data.get("handoff_id") or "").strip()
            project_id = str(data.get("project_id") or "").strip() or None
            if self._require_perm("jobs_run", project_id):
                return None
            claimant = str(data.get("claimant") or "").strip()
            if not handoff_id or not claimant:
                return self._json(400, {"error": "handoff_id and claimant required"})
            from .bus import claim_handoff
            result = claim_handoff(handoff_id, project_id, claimant)
            return self._json(200 if result["ok"] else 400, result)
        
        if path == "/api/hermes/gateway/start":
            project_id = str(data.get("project_id") or "").strip() or None
            if self._require_owner():
                return None
            wait = bool(data.get("wait", False))
            timeout = int(data.get("timeout", 30))
            
            from .hermes import gateway_start
            from .org import project_tools
            
            tools = project_tools(project_id) if project_id else {}
            hermes_home = str(tools.get("hermes_home") or "").strip() or None
            
            result = gateway_start(hermes_home, wait=wait, timeout=timeout)
            result["project_id"] = project_id
            return self._json(200 if result.get("ok") else 400, result)
        
        if path == "/api/hermes/gateway/stop":
            project_id = str(data.get("project_id") or "").strip() or None
            if self._require_owner():
                return None
            
            from .hermes import gateway_stop
            from .org import project_tools
            
            tools = project_tools(project_id) if project_id else {}
            hermes_home = str(tools.get("hermes_home") or "").strip() or None
            
            result = gateway_stop(hermes_home)
            result["project_id"] = project_id
            return self._json(200 if result.get("ok") else 400, result)
        
        if path == "/api/hermes/crons/migrate-delivery":
            project_id = str(data.get("project_id") or "").strip() or None
            if self._require_owner():
                return None
            dry_run = bool(data.get("dry_run", False))
            
            from .hermes import migrate_cron_delivery
            from .org import project_tools
            
            tools = project_tools(project_id) if project_id else {}
            hermes_home = str(tools.get("hermes_home") or "").strip() or None
            
            result = migrate_cron_delivery(hermes_home, dry_run=dry_run)
            result["project_id"] = project_id
            return self._json(200 if result.get("ok") else 400, result)
        
        if path == "/api/routines":
            if self._require_owner():
                return None
            name = str(data.get("name") or "").strip()
            schedule = str(data.get("schedule") or "").strip()
            steps = data.get("steps") or []
            project_id = str(data.get("project_id") or "").strip() or None
            enabled = bool(data.get("enabled", True))
            if not name or not schedule or not steps:
                return self._json(400, {"error": "missing name, schedule, or steps"})
            from .routines import create_routine, attach_routine_cron
            routine_id = create_routine(name, schedule, steps, project_id, enabled)
            if enabled:
                cron_result = attach_routine_cron(routine_id, project_id)
                return self._json(200, {"routine_id": routine_id, "cron": cron_result})
            return self._json(200, {"routine_id": routine_id})
        
        routine_execute = ROUTINE_EXECUTE.match(path)
        if routine_execute:
            if self._require_owner():
                return None
            routine_id = routine_execute.group(1)
            project_id = str(data.get("project_id") or "").strip() or None
            from .routines import execute_routine
            result = execute_routine(routine_id, project_id)
            return self._json(200 if result.get("ok") else 500, result)
        
        routine_resume = ROUTINE_RESUME.match(path)
        if routine_resume:
            if self._require_owner():
                return None
            routine_id = routine_resume.group(1)
            project_id = str(data.get("project_id") or "").strip() or None
            resume_step = int(data.get("resume_step", 0))
            resume_result = str(data.get("resume_result") or "").strip()
            from .routines import execute_routine
            result = execute_routine(routine_id, project_id, resume_step, resume_result)
            return self._json(200 if result.get("ok") else 500, result)
        
        project_patch = PROJECT_ID.match(path)
        if project_patch:
            pid = project_patch.group(1)
            if self._require_perm("wiring_edit", pid):
                return None
            folder = str(data.get("folder") or "").strip()
            name = str(data.get("name") or "").strip()
            try:
                result = None
                if folder:
                    result = set_project_folder(pid, folder)
                if name:
                    result = rename_project(pid, name)
                if any(
                    key in data
                    for key in (
                        "mcp_github",
                        "skills",
                        "connectors",
                        "spend_cap_usd",
                        "seats",
                        "hermes_home",
                        "account_id",
                        "fallback",
                        "site_url",
                    )
                ):
                    result = patch_project_tools(pid, data)
                if result is None:
                    return self._json(400, {"error": "folder or name required"})
                return self._json(200, result)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/keys":
            if self._require_owner():
                return None
            try:
                return self._json(
                    200,
                    add_account(
                        str(data.get("provider") or ""),
                        str(data.get("key") or ""),
                        str(data.get("label") or "") or None,
                    ),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/logins":
            if self._require_owner():
                return None
            try:
                return self._json(
                    200,
                    add_login(
                        str(data.get("label") or ""),
                        str(data.get("site") or ""),
                        str(data.get("username") or ""),
                        str(data.get("password") or ""),
                        str(data.get("project_id") or "") or None,
                        auto=bool(data.get("auto")),
                    ),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/logins/use":
            if self._require_owner():
                return None
            try:
                return self._json(
                    200,
                    use_login(
                        project_id=str(data.get("project_id") or "") or None,
                        login_id=str(data.get("login_id") or "") or None,
                        label=str(data.get("label") or ""),
                        site=str(data.get("site") or ""),
                        username=str(data.get("username") or ""),
                        password=str(data.get("password") or ""),
                        save=bool(data.get("save")),
                        auto=bool(data.get("auto")),
                    ),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if owner_only_path(path):
            if self._require_owner():
                return None
        key_row = KEY_ID.match(path)
        if key_row:
            try:
                return self._json(
                    200,
                    rename_account(key_row.group(1), str(data.get("label") or "")),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/keys/fallback":
            order = data.get("order")
            if not isinstance(order, list):
                return self._json(400, {"error": "order must be a list of account ids"})
            return self._json(200, set_fallback([str(item) for item in order]))
        if path == "/api/hermes/import/peek":
            try:
                peek = peek_backup(str(data.get("path") or ""))
                peek.pop("texts", None)
                return self._json(200, peek)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/hermes/import/backup":
            try:
                return self._json(
                    200,
                    import_from_backup(
                        str(data.get("path") or ""),
                        str(data.get("name") or "") or None,
                        str(data.get("folder") or "") or None,
                    ),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path == "/api/hermes/gateway/start":
            project_id = data.get("project_id") or None
            wait = data.get("wait", False)
            home = None
            if project_id:
                org = ensure_org()
                match = next((row for row in org["projects"] if row.get("id") == project_id), None)
                if match:
                    home = (match.get("tools") or {}).get("hermes_home")
            result = gateway_start(home, wait=bool(wait))
            return self._json(200 if result.get("ok") else 500, result)
        if path == "/api/hermes/gateway/stop":
            project_id = data.get("project_id") or None
            home = None
            if project_id:
                org = ensure_org()
                match = next((row for row in org["projects"] if row.get("id") == project_id), None)
                if match:
                    home = (match.get("tools") or {}).get("hermes_home")
            result = gateway_stop(home)
            return self._json(200 if result.get("ok") else 500, result)
        if path == "/api/hermes/crons/migrate-delivery":
            project_id = data.get("project_id") or None
            dry_run = data.get("dry_run", False)
            home = None
            if project_id:
                org = ensure_org()
                match = next((row for row in org["projects"] if row.get("id") == project_id), None)
                if match:
                    home = (match.get("tools") or {}).get("hermes_home")
            result = migrate_cron_delivery(home, dry_run=bool(dry_run))
            return self._json(200 if result.get("ok") else 500, result)
        if path == "/api/hermes/instances":
            try:
                return self._json(
                    200,
                    {
                        "instances": add_instance(
                            str(data.get("url") or ""),
                            str(data.get("key") or ""),
                            str(data.get("label") or "") or None,
                        )
                    },
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        instance_import = INSTANCE_SESSION.match(path)
        if instance_import:
            try:
                return self._json(
                    200,
                    import_session(
                        instance_import.group(1),
                        instance_import.group(2),
                        str(data.get("name") or "") or None,
                        str(data.get("folder") or "") or None,
                    ),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})

        match = JOB_ACTION.match(path)
        if match:
            job_id, action = match.group(1), match.group(2)
            job_row = read_job(job_id) or {}
            job_pid = str(job_row.get("project_id") or "").strip() or None
            if self._actor_row() and not job_pid:
                return self._forbid("not on this CEO")
            if self._require_perm("approve_needs_you", job_pid):
                return None
            force = bool(data.get("force")) if isinstance(data, dict) else False
            push_branch = bool(data.get("push_branch")) if isinstance(data, dict) else False
            branch_name = str(data.get("branch_name") or "") if isinstance(data, dict) else None
            run_tests = bool(data.get("run_tests")) if isinstance(data, dict) else False
            result = decide_diff(job_id, accept=(action == "accept"), force=force, push_branch=push_branch, branch_name=branch_name, run_tests=run_tests)
            code = 200 if result.get("ok") else 400
            # decide_diff already returns the correct INDEX (project or staff)
            if "index" not in result:
                result["index"] = read_index()
            result["spend"] = _public_config()["spend"]
            return self._json(code, result)
        
        match = JOB_REVERT.match(path)
        if match:
            job_id = match.group(1)
            job_row = read_job(job_id) or {}
            if self._require_perm("approve_needs_you", str(job_row.get("project_id") or "") or None):
                return None
            result = revert_accept(job_id)
            code = 200 if result.get("ok") else 400
            if "index" not in result:
                result["index"] = read_index()
            result["spend"] = _public_config()["spend"]
            return self._json(code, result)

        self.send_error(404)
        return None

    def do_PATCH(self):
        path = urlparse(self.path).path
        
        # Proxy OpenCode web UI
        if path.startswith("/opencode/"):
            return self._proxy("127.0.0.1", 4096, path[len("/opencode"):])
        
        # Proxy Hermes dashboard
        if path.startswith("/hermes/"):
            return self._proxy("127.0.0.1", 9119, path[len("/hermes"):])
        
        if not self._unlocked():
            return self._json(401, {"error": "locked"})
        if self._require_owner():
            return None
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 64 * 1024:
            return self._json(400, {"error": "body too large or empty"})
        data = json.loads(self.rfile.read(length))
        routine = ROUTINE_ID.match(path)
        if routine:
            routine_id = routine.group(1)
            project_id = str(data.get("project_id") or "").strip() or None
            from .routines import update_routine, attach_routine_cron, read_routine
            fields = {}
            if "name" in data:
                fields["name"] = str(data["name"]).strip()
            if "schedule" in data:
                fields["schedule"] = str(data["schedule"]).strip()
            if "steps" in data:
                fields["steps"] = data["steps"]
            if "enabled" in data:
                fields["enabled"] = bool(data["enabled"])
            ok = update_routine(routine_id, project_id, **fields)
            if not ok:
                return self._json(404, {"error": "routine not found"})
            if fields.get("enabled") or "schedule" in fields:
                routine_data = read_routine(routine_id, project_id)
                if routine_data and routine_data.get("enabled"):
                    attach_routine_cron(routine_id, project_id)
            return self._json(200, {"ok": True})
        self.send_error(404)
        return None

    def do_PUT(self):
        path = urlparse(self.path).path
        
        # Proxy OpenCode web UI
        if path.startswith("/opencode/"):
            return self._proxy("127.0.0.1", 4096, path[len("/opencode"):])
        
        # Proxy Hermes dashboard
        if path.startswith("/hermes/"):
            return self._proxy("127.0.0.1", 9119, path[len("/hermes"):])
        
        if self._lock_api(path, "PUT"):
            return self._json(403, _locked_payload())
        try:
            data = self._read_json()
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        text = str(data.get("text") or "")
        try:
            if path == "/api/index":
                if self._require_owner():
                    return None
                return self._json(200, {"index": write_index(text), "brains": list_brains()})
            org_index = PROJECT_INDEX.match(path)
            if org_index:
                if self._require_perm("index_edit", org_index.group(1)):
                    return None
                return self._json(200, {"index": write_project_index(org_index.group(1), text)})
            worker_brain = WORKER_BRAIN.match(path)
            if worker_brain:
                if self._require_perm("workers_manage", worker_brain.group(1)):
                    return None
                return self._json(
                    200,
                    {
                        "text": write_worker_brain(worker_brain.group(1), worker_brain.group(2), text),
                    },
                )
            brain = BRAIN_PATH.match(path)
            if brain:
                if self._require_owner():
                    return None
                name = brain.group(1)
                return self._json(200, {"name": name, "text": write_brain(name, text)})
        except ValueError as err:
            return self._json(400, {"error": str(err)})
        self.send_error(404)
        return None

    def do_DELETE(self):
        path = urlparse(self.path).path
        
        # Proxy OpenCode web UI
        if path.startswith("/opencode/"):
            return self._proxy("127.0.0.1", 4096, path[len("/opencode"):])
        
        # Proxy Hermes dashboard
        if path.startswith("/hermes/"):
            return self._proxy("127.0.0.1", 9119, path[len("/hermes"):])
        
        if self._lock_api(path, "DELETE"):
            return self._json(403, _locked_payload())
        invite_del = SHARE_INVITE_ID.match(path)
        if invite_del:
            if self._require_owner():
                return None
            try:
                return self._json(200, revoke_invite(invite_del.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        member_del = SHARE_MEMBER_ID.match(path)
        if member_del:
            if self._require_owner():
                return None
            try:
                return self._json(200, remove_member(member_del.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        
        match = KEY_ID.match(path)
        if match:
            if self._require_owner():
                return None
            try:
                return self._json(200, delete_account(match.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        login = LOGIN_ID.match(path)
        if login:
            if self._require_owner():
                return None
            try:
                return self._json(200, delete_login(login.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        instance = INSTANCE_ID.match(path)
        if instance:
            if self._require_owner():
                return None
            return self._json(200, {"instances": delete_instance(instance.group(1))})
        worker = WORKER_DEL.match(path)
        if worker:
            if self._require_perm("workers_manage", worker.group(1)):
                return None
            return self._json(200, remove_worker(worker.group(1), worker.group(2)))
        project = PROJECT_ID.match(path)
        if project:
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            confirm = (qs.get("confirm") or [""])[0]
            try:
                return self._json(200, remove_project(project.group(1), confirm))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        routine = ROUTINE_ID.match(path)
        if routine:
            if self._require_owner():
                return None
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .routines import delete_routine
            ok = delete_routine(routine.group(1), project_id)
            return self._json(200 if ok else 404, {"ok": ok})
        self.send_error(404)
        return None


class BoardServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        err = sys.exc_info()[1]
        if isinstance(err, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def listen_addr() -> tuple[str, int]:
    """Loopback on a laptop. 0.0.0.0 when Railway (or anyone) sets PORT."""
    port = int(os.environ.get("OPENBOT_PORT") or os.environ.get("PORT") or "8787")
    host = os.environ.get("OPENBOT_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    return host, port


def main() -> None:
    apply_env_file()
    
    # Verify data directory is writable
    ROOT.mkdir(parents=True, exist_ok=True)
    if not ROOT.is_dir():
        raise RuntimeError(f"DATA_DIR is not a directory: {ROOT}")
    test_file = ROOT / ".openbot-write-test"
    try:
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
    except OSError as err:
        raise RuntimeError(f"DATA_DIR is not writable: {ROOT} ({err})") from err
    
    host, port = listen_addr()
    WEB.mkdir(exist_ok=True)
    
    # Start autonomous queue workers for staff and all CEOs
    from .queueworker import start_queue_worker
    org_data = ensure_org()
    
    # Start staff queue worker
    start_queue_worker(None, "staff-queue-worker")
    print("Started queue worker: staff", flush=True)
    
    # Start CEO queue workers
    for project in org_data.get("projects") or []:
        pid = project.get("id")
        if pid:
            worker_name = f"{pid}-queue-worker"
            start_queue_worker(pid, worker_name)
            print(f"Started queue worker: {pid}", flush=True)
    
    httpd = BoardServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"OpenBot board {url}", flush=True)
    print(CREDIT, flush=True)
    print("Engines:", json.dumps(detect()), flush=True)
    threading.Thread(
        target=warm_engines_background,
        name="openbot-warm",
        daemon=True,
    ).start()
    threading.Thread(
        target=zen_models,
        name="zen-catalog",
        daemon=True,
    ).start()
    threading.Thread(
        target=openrouter_models,
        name="or-catalog",
        daemon=True,
    ).start()
    if os.environ.get("OPENBOT_OPEN_BROWSER", "1") != "0" and host == "127.0.0.1":
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Clean shutdown of queue workers
        from .queueworker import stop_queue_workers
        print("\nStopping queue workers...")
        stop_queue_workers()
        print("bye")


if __name__ == "__main__":
    main()
