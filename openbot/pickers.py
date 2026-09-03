"""Engine pickers. Keys decide which lists appear.

OpenCode key → official Zen /models (OpenCode’s curated list).
Other keys → that provider’s block in Hermes’s catalog (same JSON as `hermes model`).

Hints: Arena (arena.ai) via the public Hugging Face dump. Not a vendor score.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

from .detect import hermes_home
from .providers import _http_json, connected_provider_ids, openrouter_models, zen_models

HERMES_CATALOG_URL = "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"
HERMES_PROVIDER_KEY = {
    "nous": "nous",
    "anthropic": "anthropic",
    "openai": "openai",
    "openai-api": "openai",
    "google": "google",
    "gemini": "google",
    "xai": "xai",
    "x-ai": "xai",
    "openrouter": "openrouter",
}
SKIP_HERMES_PROVIDERS = {"opencode", "opencode-zen", "zen"}
ARENA_DATASET = "lmarena-ai/leaderboard-dataset"
ARENA_ROWS = "https://datasets-server.huggingface.co/rows"
ARENA_SEATS = {
    "chat": "text_style_control",
    "code": "webdev",
    "think": "text_style_control",
    "research": "search_style_control",
    "ops": "agent",
}
ARENA_CITE = (
    "Source: Arena (arena.ai) via Hugging Face {dataset}. Blind human votes, not a vendor score."
)

_HERMES_LOCK = threading.Lock()
_HERMES_CACHE: dict = {"at": 0.0, "models": []}
_GUIDE_LOCK = threading.Lock()
_GUIDE_CACHE: dict = {"at": 0.0, "guides": {}}
_GUIDE_FETCHING = False


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pretty(model_id: str) -> str:
    raw = (model_id or "").strip()
    if "/" in raw:
        raw = raw.split("/", 1)[1]
    return raw.replace("-", " ").replace("_", " ").replace(":", " ").strip() or model_id


def arena_key(text: str) -> str:
    """Strip provider prefixes and punctuation so Arena names can match catalog ids."""
    raw = (text or "").strip().lower()
    if "/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    raw = re.sub(r"20\d{6,}", "", raw)
    return re.sub(r"[^a-z0-9]+", "", raw)


def load_hermes_manifest() -> dict:
    """Disk cache first (what `hermes model` uses), then the live docs URL."""
    home = hermes_home()
    cached = _read_json(home / "cache" / "model_catalog.json")
    if cached and isinstance(cached.get("providers"), dict):
        return cached
    status, payload = _http_json(HERMES_CATALOG_URL)
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get("providers"), dict):
        return payload
    return {}


def parse_hermes_catalog(
    manifest: dict,
    connected: set[str] | list[str] | None = None,
    live_ids: set[str] | None = None,
) -> list[dict]:
    """Turn Hermes’s picker JSON into seat rows. OpenCode Zen is not this list."""
    providers = manifest.get("providers") if isinstance(manifest, dict) else {}
    if not isinstance(providers, dict):
        return []
    have = {str(item).lower() for item in (connected or [])}
    live = {str(item) for item in live_ids} if live_ids else None
    rows: list[dict] = []
    for provider_id, block in providers.items():
        pid = str(provider_id or "").strip().lower()
        if not pid or pid in SKIP_HERMES_PROVIDERS:
            continue
        key_id = HERMES_PROVIDER_KEY.get(pid)
        if not key_id:
            continue
        if have and key_id not in have and pid not in have:
            continue
        entries = (block or {}).get("models") if isinstance(block, dict) else None
        if not isinstance(entries, list):
            continue
        both_engines = key_id == "openrouter"
        for item in entries:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or "").strip()
            if not mid or ":batch" in mid:
                continue
            or_id = mid[len("openrouter/") :] if mid.startswith("openrouter/") else mid
            if live is not None and key_id == "openrouter" and or_id not in live and mid not in live:
                continue
            badge = str(item.get("description") or "").strip()
            row_id = mid if mid.startswith(f"{key_id}/") else f"{key_id}/{mid}"
            rows.append(
                {
                    "id": row_id,
                    "or_id": or_id if key_id == "openrouter" else "",
                    "label": _pretty(mid),
                    "author": mid.split("/", 1)[0],
                    "provider": key_id,
                    "in_usd": 0.0,
                    "out_usd": 0.0,
                    "reasoning": True,
                    "tools": True,
                    "code": True,
                    "badge": badge or ("OpenRouter" if both_engines else ""),
                    "default": bool(item.get("default")),
                    "engines": ("OpenCode", "Hermes Agent") if both_engines else ("Hermes Agent",),
                    "family": "hermes-picker" if not both_engines else "openrouter",
                }
            )
    return rows


def hermes_picker_models() -> list[dict]:
    with _HERMES_LOCK:
        age = time.time() - float(_HERMES_CACHE["at"] or 0)
        if _HERMES_CACHE["models"] and age < 1800:
            return list(_HERMES_CACHE["models"])
    connected = set(connected_provider_ids())
    live = {str(row.get("or_id") or "") for row in openrouter_models() if row.get("or_id")}
    rows = parse_hermes_catalog(load_hermes_manifest(), connected, live or None)
    with _HERMES_LOCK:
        _HERMES_CACHE["at"] = time.time()
        _HERMES_CACHE["models"] = rows
    return list(rows)


def opencode_picker_models() -> list[dict]:
    """Same list OpenCode web uses: official Zen /models. Empty until an OpenCode key exists."""
    return zen_models()


def _guides_from_arena(payload: dict) -> tuple[list[dict], str]:
    scores: list[dict] = []
    as_of = ""
    for item in payload.get("rows") or []:
        row = item.get("row") if isinstance(item, dict) else None
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "overall").strip().lower()
        if category and category not in {"overall", "aggregate"}:
            continue
        name = str(row.get("model_name") or "").strip()
        if not name:
            continue
        as_of = str(row.get("leaderboard_publish_date") or as_of)
        try:
            rating = float(row.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0.0
        scores.append(
            {
                "id": name,
                "label": _pretty(name.replace("-", " ")),
                "rank": row.get("rank"),
                "rating": rating,
                "key": arena_key(name),
            }
        )
    scores.sort(key=lambda item: (-float(item.get("rating") or 0), item.get("rank") or 999))
    return scores, as_of


def _refresh_guides() -> None:
    global _GUIDE_FETCHING
    try:
        guides = {}
        cite_date = ""
        fetched: dict[str, tuple[list[dict], str]] = {}
        for seat, config in ARENA_SEATS.items():
            if config not in fetched:
                query = urlencode(
                    {
                        "dataset": ARENA_DATASET,
                        "config": config,
                        "split": "latest",
                        "offset": 0,
                        "length": 80,
                    }
                )
                status, payload = _http_json(f"{ARENA_ROWS}?{query}")
                if status != 200 or not isinstance(payload, dict):
                    fetched[config] = ([], "")
                else:
                    fetched[config] = _guides_from_arena(payload)
            scores, as_of = fetched[config]
            if as_of:
                cite_date = as_of
            if scores:
                guides[seat] = {
                    "picks": scores[:3],
                    "scores": scores,
                    "as_of": as_of or cite_date,
                    "note": "Arena this week",
                    "citation": ARENA_CITE.format(dataset=ARENA_DATASET)
                    + (f" As of {cite_date}." if cite_date else ""),
                }
        with _GUIDE_LOCK:
            _GUIDE_CACHE["at"] = time.time()
            _GUIDE_CACHE["guides"] = guides
    finally:
        _GUIDE_FETCHING = False


def ranking_citation() -> str:
    return ARENA_CITE.format(dataset=ARENA_DATASET)


def ranking_guides() -> dict:
    """Arena leaderboard dump. No API key. First call waits; later refreshes daily in the background."""
    global _GUIDE_FETCHING
    with _GUIDE_LOCK:
        age = time.time() - float(_GUIDE_CACHE["at"] or 0)
        cached = dict(_GUIDE_CACHE["guides"])
        empty = not cached
        stale = age > 43200
        fetching = _GUIDE_FETCHING
        if (empty or stale) and not fetching:
            _GUIDE_FETCHING = True
            wait = empty
        else:
            wait = False
    if wait:
        _refresh_guides()
        with _GUIDE_LOCK:
            return dict(_GUIDE_CACHE["guides"])
    if stale and not fetching:
        threading.Thread(target=_refresh_guides, name="arena-guides", daemon=True).start()
    return cached
