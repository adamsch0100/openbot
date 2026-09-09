"""Phone pairing: reachable board URLs. No secrets."""

from __future__ import annotations

import os
import socket
import subprocess


def _add_url(urls: list[str], seen: set[str], host: str, port: int) -> None:
    raw = str(host or "").strip().strip("[]")
    if not raw or raw in {"0.0.0.0", "::", "*"}:
        return
    if raw.startswith("fe80:") or raw.startswith("169.254."):
        return
    if ":" in raw:
        url = f"http://[{raw}]:{port}"
    else:
        url = f"http://{raw}:{port}"
    key = url.lower()
    if key in seen:
        return
    seen.add(key)
    urls.append(url)


def _tailscale_hosts() -> list[str]:
    hosts: list[str] = []
    try:
        ip4 = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if ip4.returncode == 0:
            for line in (ip4.stdout or "").splitlines():
                text = line.strip()
                if text:
                    hosts.append(text)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        status = subprocess.run(
            ["tailscale", "status", "--self", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if status.returncode == 0 and status.stdout:
            import json

            data = json.loads(status.stdout)
            dns = str(data.get("DNSName") or data.get("Self", {}).get("DNSName") or "").rstrip(".")
            if dns:
                hosts.append(dns)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return hosts


def _lan_hosts() -> list[str]:
    hosts: list[str] = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("1.1.1.1", 80))
        hosts.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            hosts.append(info[4][0])
    except OSError:
        pass
    return hosts


def board_urls(port: int, bind_host: str = "") -> list[str]:
    """LAN, Tailscale, then loopback. Phone uses the first one that answers."""
    seen: set[str] = set()
    urls: list[str] = []
    bind = str(bind_host or "").strip()
    if bind and bind not in {"0.0.0.0", "::", "*"}:
        _add_url(urls, seen, bind, port)
    for host in _lan_hosts() + _tailscale_hosts():
        _add_url(urls, seen, host, port)
    _add_url(urls, seen, "127.0.0.1", port)
    return urls


def pair_payload(port: int, bind_host: str, *, pin_required: bool, name: str = "") -> dict:
    urls = board_urls(port, bind_host)
    return {
        "name": (name or "OpenBot").strip() or "OpenBot",
        "port": int(port),
        "pin_required": bool(pin_required),
        "urls": urls,
        "hint": "Same Wi-Fi or Tailscale. Paste an address on the phone. Set a PIN before you leave loopback.",
        "remote_bind": os.environ.get("OPENBOT_HOST") not in {None, "", "127.0.0.1", "::1", "localhost"}
        or bool(os.environ.get("PORT")),
    }


def people_rows(org: dict, activity: dict) -> list[dict]:
    """Cos + CEOs with a live state and last line. Not a third agent."""
    runs = activity.get("live_runs") or []
    need_ids = {
        str(row.get("project_id") or "")
        for row in (activity.get("needs_you") or [])
        if str(row.get("kind") or "") != "brief"
    }
    busy_ids = {str(row.get("project_id") or "") for row in runs if isinstance(row, dict)}
    engines_up = bool(activity.get("hermes_running") or activity.get("opencode_running"))
    out = [
        {
            "id": "",
            "name": "Chief of Staff",
            "kind": "staff",
            "state": _state("", "", need_ids, busy_ids, engines_up, ""),
            "last": str(activity.get("now") or "").strip()[:80],
        }
    ]
    for project in org.get("projects") or []:
        if not isinstance(project, dict):
            continue
        pid = str(project.get("id") or "")
        blocker = str(project.get("index_blocker") or "").strip()
        last = str(project.get("index_now") or project.get("index_last") or "").strip()
        out.append(
            {
                "id": pid,
                "name": str(project.get("name") or pid or "CEO"),
                "kind": "ceo",
                "state": _state(pid, blocker, need_ids, busy_ids, engines_up, last),
                "last": last[:80],
            }
        )
    return out


def _state(pid: str, blocker: str, need_ids: set[str], busy_ids: set[str], engines_up: bool, last: str) -> str:
    if pid in need_ids or (blocker and blocker != "—"):
        return "blocked"
    if pid in busy_ids:
        return "working"
    if not engines_up:
        return "offline"
    if last and last not in {"—", "source of truth"}:
        return "idle"
    return "idle"
