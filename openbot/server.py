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
from .hermes import mcp_catalog, skills_list
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
from .providers import connected_provider_ids, openrouter_models, provider_status, zen_models
from .router import decide_diff, revert_accept, handle, pending_approvals, public_job
from .queueworker import active_workers, auto_create_handoffs
from .store import (
    CODE_ROOT,
    ROOT,
    list_brains,
    list_jobs,
    read_brain,
    read_index,
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


def _record_job(job: dict, message: str, project_id: str | None, worker_id: str | None, quote: str = "", attachments: list | None = None) -> None:
    key = thread_key(project_id, worker_id)
    turn = {"role": "user", "text": redact_chat_login(message)}
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


def _activity(*, ingest_cron: bool = False) -> dict:
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
    }


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
        settings = load_settings()
        if not settings.get("pin_hash"):
            return True
        token = _cookie_value(self.headers.get("Cookie"), "openbot_unlock")
        with _UNLOCK_LOCK:
            return bool(token) and token in _UNLOCK_TOKENS

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
            
            # Connect to backend
            conn = http.client.HTTPConnection(host, port, timeout=15)
            conn.request(self.command, full_path, headers={
                "Host": f"{host}:{port}",
                "User-Agent": self.headers.get("User-Agent", ""),
                "Accept": self.headers.get("Accept", "*/*"),
            })
            
            response = conn.getresponse()
            
            # Forward response
            self.send_response(response.status)
            for header, value in response.getheaders():
                # Skip headers that might break the proxy
                if header.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(header, value)
            self.end_headers()
            
            # Stream body
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
        if path == "/api/index":
            if not self._unlocked():
                return self._json(200, _locked_payload())
            payload = {"index": read_index(), "engines": detect(), "credit": CREDIT}
            payload.update(_public_config())
            return self._json(200, payload)
        if path == "/api/engines":
            return self._json(200, detect())
        if path == "/api/config":
            if not self._unlocked():
                return self._json(200, _locked_payload())
            return self._json(200, _public_config())
        if path == "/api/spend":
            cfg = load_config()
            qs = parse_qs(urlparse(self.path).query)
            pid = (qs.get("project_id") or [""])[0].strip() or None
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
            return self._json(200, {"brains": list_brains()})
        brain = BRAIN_PATH.match(path)
        if brain:
            name = brain.group(1)
            return self._json(200, {"name": name, "text": read_brain(name), "engine": PRESET_ENGINE[name]})
        if path == "/api/jobs":
            jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
            return self._json(200, {"jobs": [public_job(job) for job in jobs[:30]]})
        if path == "/api/activity":
            return self._json(200, _activity(ingest_cron=True))
        if path.startswith("/api/jobs/") and path.endswith("/log"):
            job_id = path.split("/")[3]
            from .store import read_session_log
            log = read_session_log(job_id)
            if log is None:
                return self._json(404, {"error": "Log not found"})
            return self._json(200, {"job_id": job_id, "log": log})
        if path == "/api/onboarding/status":
            if not self._unlocked():
                return self._json(200, _locked_payload())
            status = onboarding_status()
            return self._json(200, status)
        if path == "/api/thread":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            worker_id = (qs.get("worker_id") or [""])[0].strip() or None
            key = thread_key(project_id, worker_id)
            return self._json(200, {"preset": key, "turns": read_thread(key)})
        if path == "/api/skills":
            return self._json(200, skills_list())
        if path == "/api/mcp/catalog":
            return self._json(200, mcp_catalog())
        if path == "/api/connectors/catalog":
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
            return self._json(200, opencode_web_status())
        if path == "/api/engines/hermes/dashboard":
            return self._json(200, hermes_dash_status())
        if path == "/api/providers":
            return self._json(200, provider_status())
        if path == "/api/catalog":
            ensure_chat_model()
            return self._json(200, public_catalog())
        if path == "/api/org":
            return self._json(200, ensure_org())
        if path == "/api/spend/dashboard":
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
            return self._json(200, _search_memory(query, project_id))
        if path == "/api/memory/fields":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            if project_id:
                from .org import read_project_index
                index_text = read_project_index(project_id)
            else:
                index_text = read_index()
            return self._json(200, {"index_fields": _parse_index_fields(index_text)})
        
        if path == "/api/queue/status":
            from .bus import load_open_handoffs
            org_data = ensure_org()
            
            # Build queue status per CEO
            queue_status = []
            
            # Staff queue
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
            return self._json(200, public_keyring())
        if path == "/api/hermes/instances":
            return self._json(200, {"instances": public_instances()})
        instance_sessions = INSTANCE_SESSIONS.match(path)
        if instance_sessions:
            try:
                return self._json(200, {"sessions": list_sessions(instance_sessions.group(1))})
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        if path.startswith("/api/attachments/"):
            return self._serve_attachment(path)
        if path == "/api/routines":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .routines import list_routines
            return self._json(200, {"routines": list_routines(project_id)})
        if path == "/api/routines/templates":
            from .routine_templates import get_routine_templates
            return self._json(200, {"templates": get_routine_templates()})
        if path == "/api/selfbuild/status":
            qs = parse_qs(urlparse(self.path).query)
            project_id = (qs.get("project_id") or [""])[0].strip() or None
            from .selfbuild import self_build_status
            return self._json(200, self_build_status(project_id))
        routine = ROUTINE_ID.match(path)
        if routine:
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
        
        if path == "/api/onboarding/test-job":
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

        if path == "/api/chat":
            try:
                message, folder, requested, pid, worker_id, attachments = _chat_context(data, files)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
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
            else:
                # Normal single-seat routing
                job = handle(message, folder, requested, pid, worker_id, quote=str(data.get("quote") or ""), chain_context=chain_ctx, attachments=attachments)
            
            _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""), attachments=attachments)
            job["activity"] = _activity()
            return self._json(200, job)
        if path == "/api/chat/stream":
            try:
                message, folder, requested, pid, worker_id, attachments = _chat_context(data, files)
            except ValueError as err:
                return self._json(400, {"error": str(err)})
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
                    )
                
                _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""), attachments=attachments)
                job["activity"] = _activity()
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
                return self._json(200, _public_config())
            if not verify_pin(pin):
                return self._json(403, {"error": "wrong PIN", "needs_unlock": True})
            token = _mint_unlock()
            return self._json(200, _public_config(), set_cookie=self._unlock_cookie(token))

        if path == "/api/config":
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
            folder = str(data.get("folder") or "").strip() or None
            return self._json(200, start_opencode_web(folder))
        if path == "/api/engines/hermes/dashboard":
            home = str(data.get("hermes_home") or "").strip() or None
            result = start_hermes_dashboard(home)
            return self._json(200 if result.get("ok") else 400, result)
        if path == "/api/engines/hermes/open":
            result = open_hermes()
            return self._json(200 if result.get("ok") else 400, result)
        if path == "/api/org/projects":
            try:
                folder = str(data.get("folder") or "").strip() or None
                name = str(data.get("name") or "").strip() or None
                return self._json(200, add_project(folder, name))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        worker_add = WORKER_ADD.match(path)
        if worker_add:
            try:
                return self._json(200, add_worker(worker_add.group(1), str(data.get("name") or "")))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        worker_patch = WORKER_DEL.match(path)
        if worker_patch:
            try:
                return self._json(
                    200,
                    rename_worker(worker_patch.group(1), worker_patch.group(2), str(data.get("name") or "")),
                )
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        
        if path == "/api/memory/fields":
            project_id = str(data.get("project_id") or "").strip() or None
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
            from .bus import load_open_handoffs
            handoffs = load_open_handoffs(project_id, limit=50)
            return self._json(200, {"handoffs": handoffs})
        
        if path == "/api/handoff/create":
            task = str(data.get("task") or "").strip()
            project_id = str(data.get("project_id") or "").strip() or None
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
            claimant = str(data.get("claimant") or "").strip()
            if not handoff_id or not claimant:
                return self._json(400, {"error": "handoff_id and claimant required"})
            from .bus import claim_handoff
            result = claim_handoff(handoff_id, project_id, claimant)
            return self._json(200 if result["ok"] else 400, result)
        
        if path == "/api/routines":
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
            routine_id = routine_execute.group(1)
            project_id = str(data.get("project_id") or "").strip() or None
            from .routines import execute_routine
            result = execute_routine(routine_id, project_id)
            return self._json(200 if result.get("ok") else 500, result)
        
        routine_resume = ROUTINE_RESUME.match(path)
        if routine_resume:
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
        if not self._unlocked():
            return self._json(401, {"error": "locked"})
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
        try:
            data = self._read_json()
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        text = str(data.get("text") or "")
        try:
            if path == "/api/index":
                return self._json(200, {"index": write_index(text), "brains": list_brains()})
            org_index = PROJECT_INDEX.match(path)
            if org_index:
                return self._json(200, {"index": write_project_index(org_index.group(1), text)})
            worker_brain = WORKER_BRAIN.match(path)
            if worker_brain:
                return self._json(
                    200,
                    {
                        "text": write_worker_brain(worker_brain.group(1), worker_brain.group(2), text),
                    },
                )
            brain = BRAIN_PATH.match(path)
            if brain:
                name = brain.group(1)
                return self._json(200, {"name": name, "text": write_brain(name, text)})
        except ValueError as err:
            return self._json(400, {"error": str(err)})
        self.send_error(404)
        return None

    def do_DELETE(self):
        path = urlparse(self.path).path
        match = KEY_ID.match(path)
        if match:
            try:
                return self._json(200, delete_account(match.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        login = LOGIN_ID.match(path)
        if login:
            try:
                return self._json(200, delete_login(login.group(1)))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        instance = INSTANCE_ID.match(path)
        if instance:
            return self._json(200, {"instances": delete_instance(instance.group(1))})
        worker = WORKER_DEL.match(path)
        if worker:
            return self._json(200, remove_worker(worker.group(1), worker.group(2)))
        project = PROJECT_ID.match(path)
        if project:
            qs = parse_qs(urlparse(self.path).query)
            confirm = (qs.get("confirm") or [""])[0]
            try:
                return self._json(200, remove_project(project.group(1), confirm))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
        routine = ROUTINE_ID.match(path)
        if routine:
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
