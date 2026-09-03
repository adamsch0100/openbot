"""Telegram / Hermes session cohesion for a CEO home.

OpenBot Chat is the local operator surface. Think / Ops resume the imported
Hermes session so the brain stays one conversation. Telegram on Railway stays
live until cutover — this module does not start a second gateway.
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


def telegram_session_id(home: str | Path | None) -> str:
    root = _home(home)
    if root is None:
        return ""
    try:
        con = sqlite3.connect(f"file:{root / 'state.db'}?mode=ro", uri=True)
    except sqlite3.Error:
        return ""
    try:
        rows = con.execute(
            "SELECT session_key, entry_json FROM gateway_routing ORDER BY updated_at DESC"
        ).fetchall()
    except sqlite3.Error:
        return ""
    finally:
        con.close()
    for key, blob in rows:
        if "telegram" not in str(key or "").lower():
            continue
        try:
            entry = json.loads(blob or "{}")
        except json.JSONDecodeError:
            continue
        sid = str(entry.get("session_id") or "").strip()
        if sid:
            return sid
    return ""


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
        "RECENT TELEGRAM (same Hermes brain. Railway still owns the live bot):\n"
        + "\n".join(lines)
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
            "Think, Research, and Ops resume this Hermes session. "
            "Telegram on Railway still owns the live bot until you cut over."
            if sid
            else "No Telegram session in this Hermes home yet."
        ),
    }
