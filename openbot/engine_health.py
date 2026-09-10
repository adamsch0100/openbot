"""Per-CEO engine health for Steward clarity — honest status, not spam."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .detect import detect, hermes_home, which
from .launch import (
    HERMES_DASH_PORT,
    _homes_match,
    _live_dash_home,
    _port_open,
    hermes_dash_status,
    opencode_web_status,
    resolve_ceo_hermes_home,
)

_VERSION_CACHE: dict[str, tuple[float, str]] = {}
_VERSION_TTL = 90.0


def _run_version(binary: str) -> str:
    path = which(binary)
    if not path:
        return ""
    now = time.time()
    hit = _VERSION_CACHE.get(binary)
    if hit and now - hit[0] < _VERSION_TTL:
        return hit[1]
    try:
        out = subprocess.check_output(
            [path, "--version"],
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        out = ""
    line = (out or "").strip().splitlines()[:1]
    ver = line[0].strip() if line else ""
    # Keep short: "hermes 0.21.1" / "1.18.30"
    ver = re.sub(r"^[^0-9]*", "", ver) or ver
    ver = ver[:40]
    _VERSION_CACHE[binary] = (now, ver)
    return ver


def dockerfile_pins(root: Path | None = None) -> dict[str, str]:
    """Accept-gated pins from Dockerfile — Steward source of truth for intended bake."""
    from .store import CODE_ROOT

    path = (root or CODE_ROOT) / "Dockerfile"
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    hermes = ""
    opencode = ""
    m = re.search(r"HERMES_VERSION=(\S+)", text)
    if m:
        hermes = m.group(1).strip()
    m = re.search(r"OPENCODE_VERSION=(\S+)", text)
    if m:
        opencode = m.group(1).strip()
    return {"hermes_pin": hermes, "opencode_pin": opencode}


def engine_health(project_id: str | None = None) -> dict:
    """Compact health for one CEO (or board-wide when project_id empty)."""
    engines = detect()
    pins = dockerfile_pins()
    pid = str(project_id or "").strip()
    tools: dict = {}
    if pid:
        try:
            from .org import project_tools

            tools = project_tools(pid) or {}
        except Exception:
            tools = {}
    aimed = resolve_ceo_hermes_home(pid, str(tools.get("hermes_home") or ""))
    if not aimed and not pid:
        aimed = str(hermes_home())
    dash = hermes_dash_status()
    live_home = ""
    try:
        if _port_open("127.0.0.1", HERMES_DASH_PORT):
            live_home = str(_live_dash_home() or "")
    except Exception:
        live_home = str(dash.get("home") or "")
    dash_ok = bool(aimed) and _homes_match(live_home or dash.get("home"), aimed)
    if not aimed:
        dash_ok = bool(dash.get("running"))

    gateway = {"running": False, "ok": False}
    if aimed:
        try:
            from .hermes import gateway_status

            gateway = gateway_status(aimed, timeout=3) or {}
        except Exception as err:
            gateway = {"running": False, "ok": False, "error": str(err)[:120]}

    oc = opencode_web_status()
    hermes_ver = _run_version("hermes") if engines["hermes"]["present"] else ""
    oc_ver = _run_version("opencode") if engines["opencode"]["present"] else ""

    wire = {
        "github": bool(tools.get("mcp_github")),
        "railway": bool(tools.get("authorize_railway")),
        "site": bool(tools.get("authorize_site")),
        "github_repo": str(tools.get("github_repo") or "").strip(),
        "railway_name": str(tools.get("railway") or "").strip(),
        "site_url": str(tools.get("site_url") or "").strip(),
        "hermes_home": aimed or "",
    }

    warn = []
    if aimed and dash.get("running") and not dash_ok:
        warn.append("Hermes dash home mismatch (possible Cos /root/.hermes orphan)")
    if aimed and not gateway.get("running"):
        warn.append("Hermes gateway not running for this CEO")
    if not engines["hermes"]["present"]:
        warn.append("Hermes binary missing")
    if not engines["opencode"]["present"]:
        warn.append("OpenCode binary missing")

    return {
        "ok": not warn,
        "project_id": pid or None,
        "hermes": {
            "present": bool(engines["hermes"]["present"]),
            "version": hermes_ver,
            "pin": pins.get("hermes_pin") or "",
            "dash_running": bool(dash.get("running")),
            "dash_home": live_home or str(dash.get("home") or ""),
            "dash_home_ok": dash_ok,
            "gateway_running": bool(gateway.get("running")),
            "home": aimed or "",
        },
        "opencode": {
            "present": bool(engines["opencode"]["present"]),
            "version": oc_ver,
            "pin": pins.get("opencode_pin") or "",
            "web_running": bool(oc.get("running")),
            "folder": str(oc.get("folder") or ""),
        },
        "wire": wire,
        "steward": {
            "hermes_pin": pins.get("hermes_pin") or "",
            "opencode_pin": pins.get("opencode_pin") or "",
            "policy": "Accept-gated bumps only — never silent prod upgrade",
        },
        "warn": warn,
    }
