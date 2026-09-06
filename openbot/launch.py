"""Launch official engine UIs. Do not reimplement them."""

from __future__ import annotations

import atexit
import http.client
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote

from .config import load_config
from .detect import detect, hermes_home
from .hermes import _dotenv

OPENCODE_WEB_PORT = 4096
HERMES_DASH_PORT = 9119
_opencode_proc: subprocess.Popen | None = None
_hermes_dash_proc: subprocess.Popen | None = None
_opencode_cwd: str | None = None
_hermes_dash_home: str | None = None
_oc_lock = threading.Lock()
_hermes_lock = threading.Lock()
_warmed = False
_warm_lock = threading.Lock()
_opencode_session_id: str | None = None
_opencode_sessions: dict[str, str] = {}


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _wait_port(host: str, port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.4)
    return False


def _work_dir() -> str:
    cfg = load_config()
    if cfg["work_dir_ok"]:
        return cfg["work_dir"]
    return str(Path.cwd())


def _hidden_kwargs() -> dict:
    kwargs: dict = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _hermes_cwd(home: str | Path | None = None) -> str:
    root = Path(home) if home else hermes_home()
    agent = root / "hermes-agent"
    if agent.is_dir():
        return str(agent)
    if root.is_dir():
        return str(root)
    return _work_dir()


def _d_scratch() -> Path:
    name = Path.home().name
    root = Path("D:/Users") / name
    if root.is_dir():
        return root
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")


def _hermes_env(home: str | Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    install = hermes_home()
    root = Path(home) if home else install
    env["HERMES_HOME"] = str(root)
    parts = [str(install / "bin")]
    appdata = os.environ.get("APPDATA")
    if appdata:
        parts.append(str(Path(appdata) / "npm"))
    node = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs"
    if node.is_dir():
        parts.append(str(node))
    env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
    scratch = _d_scratch()
    tmp = scratch / "tmp"
    cache = scratch / "npm-cache"
    tmp.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env["TMPDIR"] = str(tmp)
    env["npm_config_cache"] = str(cache)
    env["npm_config_engine_strict"] = "false"
    for name, value in _dotenv(install / ".env").items():
        env.setdefault(name, value)
    if root.resolve() != install.resolve():
        for name, value in _dotenv(root / ".env").items():
            env[name] = value
    return env


def _opencode_env() -> dict[str, str]:
    env = os.environ.copy()
    # `opencode web` always calls npm `open`. A non-browser BROWSER value
    # makes that fail silently so the UI stays in the OpenBot iframe.
    env["BROWSER"] = os.environ.get("OPENBOT_ENGINE_BROWSER", ":")
    return env


def _kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _kill_port(port: int) -> None:
    """Stop whatever still owns an engine port so a CEO retarget can bind."""
    kwargs = _hidden_kwargs()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            **kwargs,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return
    me = str(os.getpid())
    pids: set[str] = set()
    suffix = f":{port}"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[-2].upper() != "LISTENING":
            continue
        if not parts[1].endswith(suffix):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid not in {"0", me}:
            pids.add(pid)
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_hidden_kwargs(),
                )
            else:
                os.kill(int(pid), 15)
        except (OSError, ValueError):
            pass


def _cleanup() -> None:
    _kill(_opencode_proc)
    _kill(_hermes_dash_proc)


atexit.register(_cleanup)


def _public_engine(result: dict) -> dict:
    return {
        "ok": bool(result.get("ok")),
        "url": result.get("url"),
        "error": result.get("error"),
        "engine": result.get("engine"),
    }


def _session_id(payload: object) -> str:
    if isinstance(payload, list):
        for row in payload:
            found = _session_id(row)
            if found:
                return found
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("id", "sessionID", "session_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("info", "data", "session", "sessions"):
        nested = payload.get(key)
        if isinstance(nested, (dict, list)):
            found = _session_id(nested)
            if found:
                return found
    return ""


def _flatten_session_row(row: dict) -> dict:
    info = row.get("info") if isinstance(row.get("info"), dict) else {}
    out = dict(info)
    out.update({key: value for key, value in row.items() if key != "info"})
    return out


def _session_rows(payload: object) -> list[dict]:
    raw: list = []
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        for key in ("data", "sessions", "session"):
            nested = payload.get(key)
            if isinstance(nested, list):
                raw = nested
                break
            if isinstance(nested, dict) and (nested.get("id") or nested.get("sessionID") or nested.get("info")):
                raw = [nested]
                break
        if not raw and (payload.get("id") or payload.get("sessionID") or isinstance(payload.get("info"), dict)):
            raw = [payload]
    return [_flatten_session_row(row) for row in raw if isinstance(row, dict)]


def _session_updated(row: dict) -> int:
    stamp = row.get("time") if isinstance(row.get("time"), dict) else {}
    for key in ("updated", "completed", "created"):
        value = stamp.get(key) if isinstance(stamp, dict) else None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _folder_key(folder: str | None) -> str:
    raw = str(folder or "").strip().rstrip("/\\")
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except OSError:
        return raw.replace("\\", "/")


def _pick_session_id(payload: object, folder: str = "", prefer: str = "") -> str:
    rows = _session_rows(payload)
    target = _folder_key(folder)
    if target:
        rows = [row for row in rows if _folder_key(str(row.get("directory") or "")) == target]
    prefer = str(prefer or "").strip()
    if prefer:
        for row in rows:
            found = str(row.get("id") or row.get("sessionID") or "").strip()
            if found == prefer:
                return prefer
    if not rows:
        return ""
    if any(_session_updated(row) for row in rows):
        rows = sorted(rows, key=_session_updated, reverse=True)
    else:
        rows = list(reversed(rows))
    for row in rows:
        found = str(row.get("id") or row.get("sessionID") or "").strip()
        if found:
            return found
    return ""


def _opencode_http(method: str, path: str, body: dict | None = None, directory: str | None = None, timeout: float = 8.0):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    target = path
    if directory:
        headers["X-Opencode-Directory"] = directory
        joiner = "&" if "?" in target else "?"
        target = f"{target}{joiner}directory={quote(directory)}"
    raw = json.dumps(body).encode("utf-8") if body is not None else None
    conn = http.client.HTTPConnection("127.0.0.1", OPENCODE_WEB_PORT, timeout=timeout)
    try:
        conn.request(method, target, body=raw, headers=headers)
        resp = conn.getresponse()
        blob = resp.read()
        if resp.status >= 500:
            return None
        if not blob:
            return {}
        try:
            return json.loads(blob.decode("utf-8"))
        except json.JSONDecodeError:
            return None
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def _bound_opencode_session(folder: str) -> str:
    key = _folder_key(folder)
    found = str(_opencode_sessions.get(key) or "").strip()
    if found:
        return found
    try:
        from .org import project_id_for_folder, project_tools

        pid = project_id_for_folder(folder)
        if pid:
            found = str(project_tools(pid).get("opencode_session_id") or "").strip()
            if found:
                _opencode_sessions[key] = found
                return found
    except Exception:
        pass
    return ""


def _remember_opencode_session(folder: str, sid: str) -> None:
    global _opencode_session_id
    sid = str(sid or "").strip()
    if not sid:
        return
    _opencode_sessions[_folder_key(folder)] = sid
    _opencode_session_id = sid
    try:
        from .org import patch_project_tools, project_id_for_folder

        pid = project_id_for_folder(folder)
        if pid:
            patch_project_tools(pid, {"opencode_session_id": sid})
    except Exception:
        pass


def _open_opencode_session(folder: str, title: str) -> str:
    # One OpenCode session per CEO folder. Reopen it. Do not POST extras.
    prefer = _bound_opencode_session(folder)
    listed = _opencode_http("GET", "/session")
    scoped = _opencode_http("GET", "/session", directory=folder)
    listed_rows = _session_rows(listed)
    scoped_rows = _session_rows(scoped)
    combined = listed_rows + scoped_rows
    if prefer:
        ids = {str(row.get("id") or row.get("sessionID") or "").strip() for row in combined}
        if prefer in ids:
            _remember_opencode_session(folder, prefer)
            return prefer
    found = _pick_session_id({"data": combined}, folder, prefer)
    if found:
        _remember_opencode_session(folder, found)
        return found
    if scoped_rows:
        found = _pick_session_id({"data": scoped_rows}, "", prefer)
        if found:
            _remember_opencode_session(folder, found)
            return found
    if prefer and listed is None and scoped is None:
        _remember_opencode_session(folder, prefer)
        return prefer
    created = _opencode_http(
        "POST",
        "/session",
        body={"title": title or Path(folder).name},
        directory=folder,
    )
    found = _session_id(created)
    if found:
        _remember_opencode_session(folder, found)
    return found


def settle_opencode_session(folder: str | None = None, session_id: str | None = None) -> None:
    sid = str(session_id or _opencode_session_id or "").strip()
    directory = str(folder or _opencode_cwd or "").strip() or None
    if not sid:
        return
    _opencode_http("POST", f"/session/{sid}/abort", body={}, directory=directory, timeout=4.0)


def opencode_web_status() -> dict:
    engines = detect()
    running = _port_open("127.0.0.1", OPENCODE_WEB_PORT)
    # Same-origin relative URL so it works from any public hostname
    url = "/opencode/" if running else None
    return {
        "engine": "OpenCode",
        "present": engines["opencode"]["present"],
        "running": running,
        "url": url,
        "install": engines["opencode"]["install"],
        "embed": "iframe_or_tab",
        "folder": _opencode_cwd or _work_dir(),
        "session_id": _opencode_session_id or "",
        "note": "Official opencode web. OpenBot does not reimplement this UI.",
    }


def start_opencode_web(folder: str | None = None) -> dict:
    with _oc_lock:
        return _start_opencode_web(folder)


def _start_opencode_web(folder: str | None = None) -> dict:
    global _opencode_proc, _opencode_cwd
    engines = detect()
    path = engines["opencode"].get("path")
    if not engines["opencode"]["present"] or not path:
        return {
            "ok": False,
            "error": "OpenCode binary missing",
            "install": engines["opencode"]["install"],
            **opencode_web_status(),
        }
    target = str(Path(folder).expanduser()) if folder else _work_dir()
    try:
        target = str(Path(target).resolve())
    except OSError:
        target = folder or _work_dir()
    try:
        from .gitutil import ensure_workspace_git

        ensure_workspace_git(target)
    except Exception:
        pass
    if _port_open("127.0.0.1", OPENCODE_WEB_PORT):
        # Official OpenCode web can reuse OpenCode web across CEO folders.
        _opencode_cwd = target
        status = opencode_web_status()
        status["ok"] = True
        status["folder"] = target
        status["session_id"] = _open_opencode_session(target, Path(target).name) or _opencode_session_id
        return status
    board = os.environ.get("OPENBOT_HOST", "127.0.0.1")
    board_port = os.environ.get("OPENBOT_PORT", "8787")
    origin = f"http://{board}:{board_port}"
    cmd = [
        path,
        "web",
        "--port",
        str(OPENCODE_WEB_PORT),
        "--hostname",
        "127.0.0.1",
        "--cors",
        origin,
        "--cors",
        "http://127.0.0.1:8787",
        "--cors",
        "http://localhost:8787",
    ]
    log = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "openbot-opencode-web.log"
    log_handle = open(log, "ab")
    kwargs: dict = {
        "cwd": target if Path(target).is_dir() else _work_dir(),
        "stdout": log_handle,
        "stderr": log_handle,
        "env": _opencode_env(),
        **_hidden_kwargs(),
    }
    try:
        _opencode_proc = subprocess.Popen(cmd, **kwargs)
        _opencode_cwd = target
    except OSError as err:
        log_handle.close()
        return {"ok": False, "error": str(err), **opencode_web_status()}
    if not _wait_port("127.0.0.1", OPENCODE_WEB_PORT, 25):
        return {
            "ok": False,
            "error": f"OpenCode web did not bind :{OPENCODE_WEB_PORT}. See {log}",
            **opencode_web_status(),
        }
    if _opencode_proc.poll() is not None:
        return {
            "ok": False,
            "error": f"OpenCode web exited after bind. See {log}",
            **opencode_web_status(),
        }
    status = opencode_web_status()
    status["ok"] = True
    status["pid"] = _opencode_proc.pid
    status["folder"] = target
    status["session_id"] = _open_opencode_session(target if Path(target).is_dir() else _work_dir(), Path(target).name)
    return status


def hermes_dash_status() -> dict:
    engines = detect()
    running = _port_open("127.0.0.1", HERMES_DASH_PORT)
    # Same-origin relative URL so it works from any public hostname
    url = "/hermes/" if running else None
    return {
        "engine": "Hermes Agent",
        "present": engines["hermes"]["present"],
        "running": running,
        "url": url,
        "home": _hermes_dash_home or str(hermes_home()),
        "install": engines["hermes"]["install"],
        "install_cmd": engines["hermes"].get("install_cmd"),
        "note": "Official hermes dashboard. OpenBot does not reimplement this UI.",
    }


def prepare_hermes() -> dict:
    """Apply env/keys without the interactive setup wizard."""
    engines = detect()
    path = engines["hermes"].get("path")
    if not engines["hermes"]["present"] or not path:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing",
            "install": engines["hermes"]["install"],
        }
    home = hermes_home()
    if (home / "config.yaml").is_file():
        return {"ok": True, "skipped": True, "reason": "config present"}
    log = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "openbot-hermes-setup.log"
    log_handle = open(log, "ab")
    kwargs: dict = {
        "cwd": _hermes_cwd(),
        "stdout": log_handle,
        "stderr": log_handle,
        "env": _hermes_env(),
        "timeout": 45,
        **_hidden_kwargs(),
    }
    try:
        completed = subprocess.run([path, "setup", "--non-interactive"], **kwargs)
    except (OSError, subprocess.TimeoutExpired) as err:
        log_handle.close()
        return {"ok": False, "error": str(err), "log": str(log)}
    log_handle.close()
    return {"ok": completed.returncode == 0, "returncode": completed.returncode}


def start_hermes_dashboard(home: str | None = None) -> dict:
    with _hermes_lock:
        return _start_hermes_dashboard(home)


def _start_hermes_dashboard(home: str | None = None) -> dict:
    global _hermes_dash_proc, _hermes_dash_home
    engines = detect()
    path = engines["hermes"].get("path")
    if not engines["hermes"]["present"] or not path:
        return {
            "ok": False,
            "error": "Hermes Agent binary missing",
            "install": engines["hermes"]["install"],
            "install_cmd": engines["hermes"].get("install_cmd"),
            **hermes_dash_status(),
        }
    target = str(hermes_home())
    if home and str(home).strip():
        try:
            target = str(Path(home).expanduser().resolve())
        except OSError:
            target = str(home).strip()
    same = _hermes_dash_home and Path(_hermes_dash_home) == Path(target)
    if _port_open("127.0.0.1", HERMES_DASH_PORT) and same:
        status = hermes_dash_status()
        status["ok"] = True
        return status
    if _port_open("127.0.0.1", HERMES_DASH_PORT):
        _kill(_hermes_dash_proc)
        _hermes_dash_proc = None
        for _ in range(20):
            if not _port_open("127.0.0.1", HERMES_DASH_PORT):
                break
            time.sleep(0.2)
        if _port_open("127.0.0.1", HERMES_DASH_PORT):
            _kill_port(HERMES_DASH_PORT)
            for _ in range(20):
                if not _port_open("127.0.0.1", HERMES_DASH_PORT):
                    break
                time.sleep(0.2)
    prepare_hermes()
    cmd = [
        path,
        "dashboard",
        "--port",
        str(HERMES_DASH_PORT),
        "--host",
        "127.0.0.1",
        "--no-open",
    ]
    try:
        isolated = Path(target).resolve() != Path(hermes_home()).resolve()
    except OSError:
        isolated = bool(home)
    if isolated:
        cmd.append("--isolated")
    dist = Path(target) / "hermes-agent" / "hermes_cli" / "web_dist" / "index.html"
    if not dist.is_file():
        dist = hermes_home() / "hermes-agent" / "hermes_cli" / "web_dist" / "index.html"
    if dist.is_file():
        cmd.append("--skip-build")
    log = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "openbot-hermes-dash.log"
    log_handle = open(log, "ab")
    kwargs: dict = {
        "cwd": _hermes_cwd(target),
        "stdout": log_handle,
        "stderr": log_handle,
        "env": _hermes_env(target),
        **_hidden_kwargs(),
    }
    try:
        _hermes_dash_proc = subprocess.Popen(cmd, **kwargs)
        _hermes_dash_home = target
    except OSError as err:
        log_handle.close()
        return {"ok": False, "error": str(err), **hermes_dash_status()}
    if not _wait_port("127.0.0.1", HERMES_DASH_PORT, 180):
        hint = ""
        try:
            hint = log.read_text(encoding="utf-8", errors="replace")[-1200:]
        except OSError:
            hint = str(log)
        return {
            "ok": False,
            "error": "Hermes dashboard did not bind :9119. If extras are missing, the official install includes the web extra.",
            "log_tail": hint,
            **hermes_dash_status(),
        }
    if _hermes_dash_proc.poll() is not None:
        return {
            "ok": False,
            "error": "Hermes dashboard exited after bind. Click the CEO again.",
            **hermes_dash_status(),
        }
    status = hermes_dash_status()
    status["ok"] = True
    status["pid"] = _hermes_dash_proc.pid
    try:
        from .channel import home_summary, telegram_session_id

        status.update(home_summary(target))
        status["session_id"] = telegram_session_id(target)
    except Exception:
        pass
    return status


def open_hermes() -> dict:
    """Keep Hermes in the board window. Never spawn the interactive TUI."""
    result = start_hermes_dashboard()
    if result.get("ok"):
        result["note"] = "Hermes dashboard is running in the OpenBot window."
    return result


def warm_engines() -> dict:
    """Start OpenCode and Hermes when the board opens. Safe to call twice."""
    global _warmed
    with _warm_lock:
        if _warmed and _port_open("127.0.0.1", OPENCODE_WEB_PORT) and _port_open(
            "127.0.0.1", HERMES_DASH_PORT
        ):
            return {
                "opencode": opencode_web_status() | {"ok": True},
                "hermes": hermes_dash_status() | {"ok": True},
            }
        try:
            from .keyring import activate_for_engine

            activate_for_engine("OpenCode")
            activate_for_engine("Hermes Agent")
        except Exception as err:
            print(f"[openbot] key push skipped: {err}", flush=True)
        opencode = start_opencode_web()
        hermes = start_hermes_dashboard()
        _warmed = True
        return {"opencode": opencode, "hermes": hermes}


def warm_engines_background() -> None:
    try:
        result = warm_engines()
        print(
            "Engines warmed:",
            {
                name: _public_engine(payload)
                for name, payload in result.items()
            },
            flush=True,
        )
    except Exception as err:
        print(f"[openbot] engine warm failed: {err}", flush=True)
