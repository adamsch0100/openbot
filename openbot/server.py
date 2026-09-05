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
from .router import decide_diff, handle, pending_approvals, public_job
from .store import (
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

WEB = ROOT / "web"
JOB_ACTION = re.compile(r"^/api/jobs/([a-f0-9]{6,32})/(accept|reject)$")
RUN_STOP = re.compile(r"^/api/runs/([a-zA-Z0-9-]{6,40})/stop$")
BRAIN_PATH = re.compile(r"^/api/brains/(cos|builder|research|ops|think)$")
KEY_ID = re.compile(r"^/api/keys/([a-zA-Z0-9_-]{4,32})$")
LOGIN_ID = re.compile(r"^/api/logins/([a-zA-Z0-9_-]{4,32})$")
PROJECT_ID = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})$")
PROJECT_INDEX = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/index$")
WORKER_ADD = re.compile(r"^/api/org/projects/([a-z0-9-]{1,40})/workers$")
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


def _chat_context(data: dict) -> tuple:
    message = str(data.get("message") or "").strip()
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
    return message, folder, requested, pid, worker_id


def _record_job(job: dict, message: str, project_id: str | None, worker_id: str | None, quote: str = "") -> None:
    key = thread_key(project_id, worker_id)
    turn = {"role": "user", "text": redact_chat_login(message)}
    cleaned = redact_chat_login(str(quote or "").strip())
    cleaned = " ".join(cleaned.split())[:400]
    if cleaned:
        turn["quote"] = cleaned
    append_turn(key, turn)
    append_turn(key, {"role": "bot", "job": job})


_CRON_INGEST_AT = 0.0
_CRON_COOLDOWN_SEC = 60.0


def _activity(*, ingest_cron: bool = False) -> dict:
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
    return {
        "now": (now_match.group(1).strip() if now_match else ""),
        "jobs": [public_job(job) for job in jobs[:30]],
        "needs_you": needs,
        "cron_jobs": cron_jobs,
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
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def _unlock_cookie(self, token: str) -> str:
        return f"openbot_unlock={token}; HttpOnly; SameSite=Lax; Path=/"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise json.JSONDecodeError("object required", "", 0)
        return data

    def do_GET(self):
        path = urlparse(self.path).path
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
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})

        if path == "/api/chat":
            message, folder, requested, pid, worker_id = _chat_context(data)
            if not message:
                return self._json(400, {"error": "empty message"})
            chain_ctx = data.get("chain_context") if isinstance(data.get("chain_context"), dict) else None
            job = handle(message, folder, requested, pid, worker_id, quote=str(data.get("quote") or ""), chain_context=chain_ctx)
            _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""))
            job["activity"] = _activity()
            return self._json(200, job)
        if path == "/api/chat/stream":
            message, folder, requested, pid, worker_id = _chat_context(data)
            if not message:
                return self._json(400, {"error": "empty message"})
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
                )
                _record_job(job, message, pid, worker_id, quote=str(data.get("quote") or ""))
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
                    "operator_name",
                    "pin",
                    "clear_pin",
                    "license_key",
                    "spend_policy",
                )
                if any(key in data for key in settings_keys):
                    if isinstance(data.get("seats"), dict):
                        validate_seats(data["seats"])
                    save_settings(data)
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
            result = decide_diff(job_id, accept=(action == "accept"))
            code = 200 if result.get("ok") else 400
            # decide_diff already returns the correct INDEX (project or staff)
            if "index" not in result:
                result["index"] = read_index()
            result["spend"] = _public_config()["spend"]
            return self._json(code, result)

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
    host, port = listen_addr()
    WEB.mkdir(exist_ok=True)
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
        print("\nbye")


if __name__ == "__main__":
    main()
