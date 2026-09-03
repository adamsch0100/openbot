"""Telegram / Hermes session cohesion for a CEO home.

OpenBot Chat is the operator surface. Think, Research, and Ops resume the
imported Hermes Telegram session. CEO Chat gets a short Telegram slice for
context (fresh oneshot — does not --resume). Replies on the board do not
post into Telegram.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

MAX_TURNS = 40
MAX_TEXT = 1200


def _home(path: str | Path | None) -> Path | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    home = Path(raw).expanduser()
    db = home / "state.db"
    return home if db.is_file() else None


def _sid_from_routing(con: sqlite3.Connection) -> str:
    try:
        rows = con.execute(
            "SELECT session_key, entry_json FROM gateway_routing ORDER BY updated_at DESC"
        ).fetchall()
    except sqlite3.Error:
        return ""
    for key, blob in rows:
        try:
            entry = json.loads(blob or "{}")
        except json.JSONDecodeError:
            entry = {}
        hay = f"{key or ''} {blob or ''}".lower()
        if "telegram" not in hay:
            continue
        sid = str(entry.get("session_id") or "").strip()
        if sid:
            return sid
    return ""


def _sid_from_sessions(con: sqlite3.Connection) -> str:
    try:
        cols = {str(row[1]) for row in con.execute("PRAGMA table_info(sessions)")}
    except sqlite3.Error:
        return ""
    if "id" not in cols or "source" not in cols:
        return ""
    if "message_count" in cols:
        order = "message_count DESC"
    elif "started_at" in cols:
        order = "started_at DESC"
    else:
        order = "id DESC"
    try:
        row = con.execute(
            f"SELECT id FROM sessions WHERE lower(ifnull(source,'')) LIKE '%telegram%' "
            f"ORDER BY {order} LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0] or "").strip() if row else ""


def telegram_session_id(home: str | Path | None) -> str:
    root = _home(home)
    if root is None:
        return ""
    try:
        con = sqlite3.connect(f"file:{root / 'state.db'}?mode=ro", uri=True)
    except sqlite3.Error:
        return ""
    try:
        return _sid_from_routing(con) or _sid_from_sessions(con)
    finally:
        con.close()


def _message_text(raw) -> str:
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                for key in ("text", "content"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            if isinstance(payload, list):
                bits = []
                for part in payload:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        bits.append(part["text"])
                if bits:
                    return "\n".join(bits).strip()
        return text
    if isinstance(raw, dict):
        for key in ("text", "content"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def recent_turns(home: str | Path | None, session_id: str | None = None, limit: int = MAX_TURNS) -> list[dict]:
    root = _home(home)
    sid = (session_id or "").strip() or telegram_session_id(root)
    if root is None or not sid:
        return []
    cap = max(1, min(int(limit), MAX_TURNS))
    try:
        con = sqlite3.connect(f"file:{root / 'state.db'}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = ? AND lower(role) IN ('user', 'assistant') "
            "ORDER BY timestamp DESC LIMIT ?",
            (sid, cap * 3),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    newest = []
    for role, content, ts in rows:
        text = _message_text(content)
        if not text:
            continue
        newest.append(
            {
                "role": "user" if str(role).lower() == "user" else "bot",
                "text": text[:MAX_TEXT],
                "at": ts,
                "source": "telegram",
            }
        )
        if len(newest) >= cap:
            break
    newest.reverse()
    return newest


def session_hint(home: str | Path | None, session_id: str | None = None, limit: int = 6) -> str:
    """Short Telegram slice so CEO Chat knows the same brain, without replaying the archive."""
    turns = recent_turns(home, session_id, limit=max(1, min(int(limit), 8)))
    if not turns:
        return ""
    lines = []
    for turn in turns:
        who = "operator" if turn.get("role") == "user" else "this CEO"
        text = re.sub(r"\s+", " ", str(turn.get("text") or "")).strip()[:320]
        if text:
            lines.append(f"{who}: {text}")
    if not lines:
        return ""
    return (
        "RECENT TELEGRAM (same CEO — context only, answer the new board message):\n"
        + "\n".join(lines)
    )


def cron_roster(home: str | Path | None, limit: int = 16) -> str:
    """Enabled Hermes cron names from this CEO home. Files, not chat."""
    raw = str(home or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser() / "cron" / "jobs.json"
    if not path.is_file():
        return ""
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    items = blob.get("jobs") if isinstance(blob, dict) else blob
    if not isinstance(items, list):
        return ""
    names: list[str] = []
    enabled = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "").strip()
        if item.get("enabled", True):
            enabled += 1
            if name:
                names.append(name)
    if not items:
        return ""
    shown = names[: max(1, min(int(limit), 24))]
    extra = f" (+{len(names) - len(shown)} more)" if len(names) > len(shown) else ""
    return (
        f"CRON (this Hermes home): {enabled} enabled / {len(items)} — "
        + ", ".join(shown)
        + extra
        + ". These fire here, deliver to Telegram when origin is set, and land in this CEO's Ops lane."
    )


def home_summary(home: str | Path | None) -> dict:
    """Counts and the bound Telegram session for a CEO Hermes home."""
    empty = {
        "session_count": 0,
        "session_title": "",
        "session_source": "",
    }
    root = Path(home) if str(home or "").strip() else None
    if root is None or not (root / "state.db").is_file():
        return empty
    sid = telegram_session_id(root)
    count = 0
    title = ""
    source = "telegram" if sid else ""
    try:
        con = sqlite3.connect(f"file:{root / 'state.db'}?mode=ro", uri=True)
    except sqlite3.Error:
        return {**empty, "session_id": sid}
    try:
        try:
            count = int(con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] or 0)
        except sqlite3.Error:
            count = 0
        if sid:
            try:
                row = con.execute(
                    "SELECT display_name, title, source FROM sessions WHERE id = ?",
                    (sid,),
                ).fetchone()
            except sqlite3.Error:
                row = None
            if row:
                title = str(row[0] or row[1] or "").strip()
                source = str(row[2] or "telegram").strip()
    finally:
        con.close()
    return {
        "session_count": count,
        "session_title": title,
        "session_source": source,
    }


def public_channel(home: str | Path | None, session_id: str | None = None) -> dict:
    sid = (session_id or "").strip() or telegram_session_id(home)
    turns = recent_turns(home, sid)
    return {
        "hermes_session_id": sid,
        "source": "telegram" if sid else "",
        "turns": turns,
        "note": (
            "Think, Research, and Ops resume this Hermes Telegram session. "
            "CEO Chat gets a short Telegram slice for context (fresh oneshot — does not --resume). "
            "Telegram is live on this OpenBot instance. Board replies do not post into Telegram."
            if sid
            else "No Telegram session in this Hermes home yet."
        ),
    }
