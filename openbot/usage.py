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
