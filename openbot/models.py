"""Seat catalog. Lists come from OpenCode and Hermes pickers, not a frozen dump."""

from __future__ import annotations

from .pickers import hermes_picker_models, opencode_picker_models, ranking_citation, ranking_guides
from .providers import connected_provider_ids, openrouter_models

ENGINE_DEFAULT = {
    "id": "",
    "label": "Engine default",
    "provider": "",
    "in_usd": 0.0,
    "out_usd": 0.0,
    "reasoning": True,
    "tools": True,
    "code": True,
    "engines": ("OpenCode", "Hermes Agent"),
}

MODELS = (ENGINE_DEFAULT,)

SEATS = (
    {"id": "chat", "label": "Chat", "engine": "Hermes Agent", "need": ()},
    {"id": "think", "label": "Think", "engine": "Hermes Agent", "need": ()},
    {"id": "code", "label": "Code", "engine": "OpenCode", "need": ("tools", "code")},
    {"id": "research", "label": "Research", "engine": "Hermes Agent", "need": ("tools",)},
    {"id": "ops", "label": "Ops", "engine": "Hermes Agent", "need": ("tools",)},
)

SEAT_NOTES = {
    "chat": "Everyday talk. Cheap. No tools. On Nous Portal, Hermes-4 is Chat. Status questions still read INDEX for free.",
    "think": "Hard reasoning. Use when Chat is not enough.",
    "code": "Builder. OpenCode in the project folder.",
    "research": "Fetch a URL. Snapshot only if the page is an app.",
    "ops": "Schedules. Hermes cron, not a second scheduler.",
}

_PROVIDER_ALIASES = {
    "opencode": ("opencode", "zen", "opencode-zen"),
    "openrouter": ("openrouter",),
    "anthropic": ("anthropic",),
    "openai": ("openai",),
    "google": ("google", "gemini"),
    "xai": ("xai",),
    "nous": ("nous",),
}

_PROVIDER_LABEL = {
    "": "Engine",
    "engine": "Engine",
    "board": "Board",
    "opencode": "OpenCode",
    "openrouter": "OpenRouter",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "xai": "xAI",
    "nous": "Nous",
}

_SEAT_TO_MODEL = {
    "chat": "cos",
    "think": "think",
    "code": "builder",
    "research": "research",
    "ops": "ops",
}

UNLOCKED = {"chat", "think", "code", "research", "ops"}


def model_provider(spec: str | dict | None) -> str:
    if isinstance(spec, dict):
        prov = str(spec.get("provider") or "").strip().lower()
        if prov in {"zen", "opencode-zen"}:
            return "opencode"
        if prov:
            return prov
        spec = str(spec.get("id") or "")
    raw = str(spec or "").strip()
    if "/" not in raw:
        return ""
    prefix = raw.split("/", 1)[0].lower()
    if prefix in {"zen", "opencode-zen"}:
        return "opencode"
    return prefix


def _primary_chat_provider() -> str:
    from .providers import connected_provider_ids

    if "nous" in connected_provider_ids():
        return "nous"
    from .keyring import primary_provider

    return primary_provider()


def _connected(provider: str, names: list[str]) -> bool:
    if not provider:
        return True
    aliases = _PROVIDER_ALIASES.get(provider, (provider,))
    return any(item in names for item in aliases)


def _fits(row: dict, need: tuple[str, ...]) -> bool:
    return all(bool(row.get(flag)) for flag in need)


def all_models() -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    def add(row: dict) -> None:
        item = dict(row)
        if item["id"] in seen:
            return
        merged.append(item)
        seen.add(item["id"])

    add(ENGINE_DEFAULT)
    for row in opencode_picker_models():
        add(row)
    for row in openrouter_models():
        add(row)
    for row in hermes_picker_models():
        add(row)
    return merged


def by_id(model_id: str) -> dict | None:
    for row in all_models():
        if row["id"] == model_id:
            return row
    return None


def seat_model(settings: dict, seat_id: str, project_seats: dict | None = None) -> str:
    if isinstance(project_seats, dict):
        row = project_seats.get(seat_id) if isinstance(project_seats.get(seat_id), dict) else {}
        model = str((row or {}).get("model") or "").strip()
        if model:
            return model
    seats = settings.get("seats") if isinstance(settings.get("seats"), dict) else {}
    row = seats.get(seat_id) if isinstance(seats.get(seat_id), dict) else {}
    model = str((row or {}).get("model") or "").strip()
    if model:
        return model
    if seat_id == "chat":
        return ""
    models = settings.get("models") if isinstance(settings.get("models"), dict) else {}
    alias = _SEAT_TO_MODEL.get(seat_id, seat_id)
    return str((models or {}).get(alias) or "").strip()


def ensure_chat_model() -> str:
    """Return Chat Auto (or a pin). Do not persist Auto as a pin."""
    from .auto import seated_or_auto
    from .config import load_settings

    return seated_or_auto(load_settings(), "chat")


def recommended_chat_id(models: list[dict] | None = None, provider: str | None = None) -> str:
    """Cheap Chat on Nous Portal when connected, else the first keyring provider. OpenRouter last is fallback, not default."""
    source = models if models is not None else all_models()
    rows = [
        row
        for row in source
        if row.get("id") and row.get("connected") is not False
    ]
    if provider is None and models is None:
        provider = _primary_chat_provider()
    if provider:
        matched = [row for row in rows if model_provider(row) == provider]
        if matched:
            rows = matched

    def blob(row: dict) -> str:
        return f"{row.get('id', '')} {row.get('label', '')} {row.get('author', '')}".lower()

    def price(row: dict) -> float:
        return float(row.get("in_usd") or 0) + float(row.get("out_usd") or 0)

    if provider == "nous":
        talk = [row for row in rows if "hermes-4" in blob(row) and "405" not in blob(row)]
        if talk:
            talk.sort(key=lambda row: (price(row), str(row.get("id") or "")))
            return str(talk[0]["id"])

    flash = [row for row in rows if "deepseek" in blob(row) and "flash" in blob(row)]
    if flash:
        flash.sort(key=lambda row: (price(row), str(row.get("id") or "")))
        return str(flash[0]["id"])
    if not rows:
        return ""

    def heavy(row: dict) -> int:
        text = blob(row)
        if "opus" in text:
            return 2
        if "sonnet" in text:
            return 1
        return 0

    rows.sort(key=lambda row: (heavy(row), price(row), str(row.get("id") or "")))
    return str(rows[0]["id"])


def cheap_chat_for_provider(provider: str, models: list[dict] | None = None) -> str:
    return recommended_chat_id(models, provider=provider)


def allowed_for_seat(seat_id: str, model_id: str) -> bool:
    if seat_id == "chat" and model_id in {"", "INDEX"}:
        return True
    spec = next((item for item in SEATS if item["id"] == seat_id), None)
    if spec is None:
        return False
    if spec.get("locked") and model_id not in {"", "INDEX"}:
        return False
    if model_id == "":
        return True
    prefix = model_id.split("/", 1)[0].lower()
    row = by_id(model_id)
    if row is None:
        return prefix in {"opencode", "openrouter", "nous", "anthropic", "openai", "google", "xai"} and seat_id in UNLOCKED
    if seat_id != "chat" and not _fits(row, spec.get("need") or ()):
        return False
    if row.get("provider") == "opencode" or prefix == "opencode":
        return seat_id in UNLOCKED
    engines = row.get("engines") or ()
    seat_engine = spec.get("engine")
    if seat_engine == "OpenCode" and engines and "OpenCode" not in engines:
        return False
    if seat_engine == "Hermes Agent" and engines and "Hermes Agent" not in engines:
        return False
    return True


def validate_seats(seats: dict) -> None:
    connected = connected_provider_ids()
    for spec in SEATS:
        seat_id = spec["id"]
        if spec.get("locked"):
            continue
        row = seats.get(seat_id) if isinstance(seats, dict) else None
        model_id = ""
        if isinstance(row, dict):
            model_id = str(row.get("model") or "").strip()
        if not allowed_for_seat(seat_id, model_id):
            raise ValueError(f"{seat_id} cannot use {model_id or '(empty)'}")
        meta = by_id(model_id)
        if meta and meta.get("provider") and not _connected(str(meta["provider"]), connected):
            raise ValueError(f"{seat_id} needs a {meta['provider']} key")


def public_catalog() -> dict:
    connected = connected_provider_ids()
    models = []
    for row in all_models():
        models.append(
            {
                "id": row["id"],
                "label": row["label"],
                "provider": row.get("provider") or "engine",
                "provider_label": _PROVIDER_LABEL.get(row.get("provider") or "engine", row.get("provider") or "Engine"),
                "author": row.get("author") or "",
                "in_usd": float(row.get("in_usd") or 0),
                "out_usd": float(row.get("out_usd") or 0),
                "context": int(row.get("context") or 0),
                "max_out": int(row.get("max_out") or 0),
                "connected": _connected(str(row.get("provider") or ""), connected),
                "caps": [name for name in ("reasoning", "tools", "code") if row.get(name)],
                "engines": list(row.get("engines") or ()),
                "family": str(row.get("family") or row.get("provider") or ""),
                "badge": str(row.get("badge") or ""),
                "default": bool(row.get("default")),
            }
        )
    seats = []
    for spec in SEATS:
        seats.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "engine": spec["engine"],
                "locked": bool(spec.get("locked")),
                "need": list(spec.get("need") or ()),
                "note": SEAT_NOTES.get(spec["id"], ""),
            }
        )
    guides = ranking_guides()
    citation = ranking_citation()
    for row in guides.values():
        if isinstance(row, dict) and row.get("citation"):
            citation = str(row["citation"])
            break
    from .auto import public_assignments, public_auto

    auto = public_auto(models, guides)
    slim_guides = {}
    for key, row in guides.items():
        if not isinstance(row, dict):
            continue
        slim = dict(row)
        slim.pop("scores", None)
        slim_guides[key] = slim
    return {
        "seats": seats,
        "models": models,
        "guides": slim_guides,
        "ranking_citation": citation,
        "recommended_chat": (auto.get("chat") or {}).get("id") or recommended_chat_id(models, provider=_primary_chat_provider()),
        "auto": auto,
        "assignment": public_assignments(models, guides),
        "connected": connected,
        "live": True,
    }
