"""Parse OpenCode --format json events into a job receipt. No third meter."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass


@dataclass
class Usage:
    prompt_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    usd_estimate: float = 0.0
    model: str = "engine-default"
    text: str = ""
    session_id: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _walk_events(raw: str):
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            continue


HEADER_NOISE = re.compile(r"set-cookie|cf-ray|responseheaders|responsebody", re.I)
SECRET_LIVE = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|bearer|cookie|totp",
    re.I,
)
_LIVE_SKIP_TYPES = {
    "text",
    "step_finish",
    "step-finish",
    "error",
}
_LIVE_TOOL_TYPES = {
    "step_start",
    "step-start",
    "tool_use",
    "tool_start",
    "tool-start",
    "tool",
    "part_update",
    "part_updated",
}


def clip_live_detail(text: str, limit: int = 88) -> str:
    blob = re.sub(r"\s+", " ", str(text or "")).strip()
    if not blob or SECRET_LIVE.search(blob):
        return ""
    if len(blob) <= limit:
        return blob
    return blob[: limit - 1] + "…"


def short_live_path(path: str) -> str:
    raw = str(path or "").replace("\\", "/").strip()
    if not raw or SECRET_LIVE.search(raw):
        return ""
    if len(raw) <= 72:
        return raw
    return "…/" + raw.rsplit("/", 1)[-1][:60]


def _live_pick_detail(obj, depth: int = 0) -> str:
    if not isinstance(obj, dict) or depth > 4:
        return ""
    for key in (
        "filePath",
        "filepath",
        "path",
        "file",
        "filename",
        "command",
        "cmd",
        "url",
        "query",
        "pattern",
        "glob",
        "title",
        "description",
    ):
        val = obj.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        if SECRET_LIVE.search(key) or SECRET_LIVE.search(val):
            continue
        if key in {"filePath", "filepath", "path", "file", "filename"}:
            picked = short_live_path(val)
        else:
            picked = clip_live_detail(val)
        if picked:
            return picked
    for nested_key in ("input", "state", "args", "properties"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict):
            inner = nested.get("input") if isinstance(nested.get("input"), dict) else nested
            picked = _live_pick_detail(inner, depth + 1)
            if picked:
                return picked
    return ""


def opencode_progress_chip(event: dict) -> str | None:
    """One live line from an OpenCode JSON event. No tool JSON dump."""
    if not isinstance(event, dict):
        return None
    etype = str(event.get("type") or "").strip()
    if etype in _LIVE_SKIP_TYPES:
        return None
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    part_type = str(part.get("type") or "").strip()
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    status = str(state.get("status") or "").lower()
    if status in {"completed", "finished", "success"}:
        return None
    name = str(part.get("name") or part.get("tool") or event.get("tool") or "").strip()
    interesting = etype in _LIVE_TOOL_TYPES or part_type in _LIVE_TOOL_TYPES or bool(name)
    if not interesting:
        return None
    verb = name or part_type or etype
    verb = verb.replace("step-start", "").replace("step_start", "").replace("tool-start", "tool").strip()
    if not verb:
        return None
    detail = _live_pick_detail(part) or _live_pick_detail(event)
    if status == "error":
        verb = f"{verb} failed"
    if detail:
        return f"OpenCode · {verb} · {detail}"
    return f"OpenCode · {verb}"



def error_message(event: dict) -> str:
    err = event.get("error") if isinstance(event.get("error"), dict) else {}
    data = err.get("data") if isinstance(err.get("data"), dict) else {}
    for value in (data.get("message"), err.get("message"), err.get("name"), event.get("message")):
        text = str(value or "").strip()
        if text and not HEADER_NOISE.search(text):
            return text[:800]
    return "OpenCode error"


def error_message_from_raw(raw: str) -> str:
    for event in _walk_events(raw or ""):
        if event.get("type") == "error":
            return error_message(event)
    blob = str(raw or "")
    if HEADER_NOISE.search(blob):
        return "OpenCode could not complete that run. Pick a Code model that supports tools, then send it again."
    return ""


def sanitize_job_text(text) -> str:
    blob = str(text or "")
    if not blob:
        return ""
    if HEADER_NOISE.search(blob):
        cleaned = error_message_from_raw(blob)
        if cleaned:
            return cleaned
        return "OpenCode could not complete that run. Pick a Code model that supports tools, then send it again."
    return blob[-24000:]


def parse_opencode_events(raw: str) -> Usage:
    """Sum step_finish token/cost events. Concatenate assistant text parts."""
    usage = Usage()
    texts: list[str] = []
    for event in _walk_events(raw):
        event_type = event.get("type")
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event.get("sessionID") and not usage.session_id:
            usage.session_id = str(event.get("sessionID"))
        model = event.get("model") or part.get("model") or (event.get("info") or {}).get("model")
        if isinstance(model, str) and model.strip():
            usage.model = model.strip()
        if event_type == "text":
            chunk = part.get("text") or event.get("text")
            if chunk:
                texts.append(str(chunk))
        if event_type == "error":
            texts.append(error_message(event))
        if event_type in {"step_finish", "step-finish"}:
            tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            usage.prompt_tokens += _as_int(tokens.get("input"))
            usage.output_tokens += _as_int(tokens.get("output"))
            usage.cached_tokens += _as_int(cache.get("read"))
            usage.usd_estimate += _as_float(part.get("cost"))
    usage.usd_estimate = round(usage.usd_estimate, 6)
    usage.text = "\n".join(texts).strip()
    return usage
