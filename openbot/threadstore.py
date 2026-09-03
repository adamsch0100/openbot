"""Thread JSON is UI only. Never send it as the model prompt."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .store import ROOT

THREADS = ROOT / "threads"
PRESETS = {"cos", "builder", "research", "ops", "think"}
MAX_TURNS = 200
ORG_THREAD = re.compile(r"^org:([a-z0-9-]{1,40}):([a-z0-9-]{1,40})$")
EARLIER = re.compile(
    r"\b(as i (said|mentioned|asked|told you)|earlier you said|remember when|like i said)\b",
    re.I,
)


def thread_key(project_id: str | None, worker_id: str | None) -> str:
    if worker_id and project_id:
        return f"org:{project_id}:{worker_id}"
    if project_id:
        return f"org:{project_id}:ceo"
    return "cos"


def _path(key: str) -> Path | None:
    if key in PRESETS:
        return THREADS / f"{key}.json"
    match = ORG_THREAD.match(key or "")
    if not match:
        return None
    dest = THREADS / "org"
    dest.mkdir(parents=True, exist_ok=True)
    return dest / f"{match.group(1)}--{match.group(2)}.json"


def read_thread(key: str) -> list[dict]:
    path = _path(key)
    if path is None or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data[-MAX_TURNS:]
    return []


def write_thread(key: str, turns: list[dict]) -> list[dict]:
    path = _path(key)
    if path is None:
        raise ValueError("unknown thread")
    THREADS.mkdir(exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = turns[-MAX_TURNS:]
    path.write_text(json.dumps(clipped, indent=2), encoding="utf-8")
    return clipped


def append_turn(key: str, turn: dict) -> list[dict]:
    turns = read_thread(key)
    turns.append(turn)
    return write_thread(key, turns)


def _turn_text(turn: dict) -> str:
    if turn.get("text"):
        return str(turn.get("text") or "")
    job = turn.get("job") if isinstance(turn.get("job"), dict) else {}
    return str(job.get("text") or "")


def search_quote(key: str, message: str, limit: int = 400) -> str:
    turns = read_thread(key)
    if not turns:
        return ""
    cleaned = EARLIER.sub(" ", message or "")
    words = [word.lower() for word in re.findall(r"[a-zA-Z0-9]{4,}", cleaned)]
    needles = words[-8:]
    best = ""
    best_score = 0
    for turn in reversed(turns):
        text = re.sub(r"\s+", " ", _turn_text(turn)).strip()
        if len(text) < 12:
            continue
        lower = text.lower()
        score = sum(1 for word in needles if word in lower) if needles else 1
        if score > best_score:
            best_score = score
            best = text
            if score >= 3:
                break
    if not best:
        return ""
    return best[:limit]


def wants_quote(message: str) -> bool:
    return bool(EARLIER.search(message or ""))
