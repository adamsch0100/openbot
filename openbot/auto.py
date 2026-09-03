"""Auto seat picks: quality per dollar, OpenCode Go first, OpenRouter last."""

from __future__ import annotations

from .models import SEATS, allowed_for_seat, all_models, model_provider, seat_model
from .pickers import arena_key, ranking_guides

_CHEAP = ("flash", "nano", "mini", "haiku", "lite", "small")
_HEAVY = ("opus", "405b", "ultra")
_PROVIDER_ORDER = ("nous", "opencode", "openrouter")


def blended_cost(row: dict) -> float:
    return float(row.get("in_usd") or 0) * 0.3 + float(row.get("out_usd") or 0) * 0.7


def _blob(row: dict) -> str:
    return f"{row.get('id', '')} {row.get('label', '')} {row.get('author', '')}".lower()


def _cheap_name(row: dict) -> bool:
    text = _blob(row)
    return any(token in text for token in _CHEAP)


def _heavy_name(row: dict) -> bool:
    text = _blob(row)
    return any(token in text for token in _HEAVY)


def match_arena(row: dict, scores: list[dict]) -> dict | None:
    keys = [arena_key(str(row.get("id") or "")), arena_key(str(row.get("label") or ""))]
    keys = [key for key in keys if len(key) >= 4]
    if not keys:
        return None
    best = None
    best_len = 0
    for score in scores or []:
        hay = str(score.get("key") or arena_key(str(score.get("id") or "")))
        if not hay:
            continue
        for key in keys:
            if key == hay or (len(key) >= 8 and (key in hay or hay in key)):
                if len(hay) >= best_len:
                    best = score
                    best_len = len(hay)
    return best


def _connected_rows(models: list[dict] | None) -> list[dict]:
    source = models if models is not None else all_models()
    return [row for row in source if row.get("id") and row.get("connected") is not False]


def _for_seat(seat_id: str, models: list[dict] | None) -> list[dict]:
    rows = []
    for row in _connected_rows(models):
        if not allowed_for_seat(seat_id, str(row.get("id") or "")):
            continue
        rows.append(row)
    by_provider: dict[str, list[dict]] = {}
    for row in rows:
        by_provider.setdefault(model_provider(row), []).append(row)
    for provider in _PROVIDER_ORDER:
        if by_provider.get(provider):
            return by_provider[provider]
    return rows


def _scores_for(seat_id: str, guides: dict | None) -> tuple[list[dict], str]:
    blob = (guides or ranking_guides() or {}).get(seat_id) or {}
    if seat_id == "chat" and not blob.get("scores"):
        blob = (guides or ranking_guides() or {}).get("think") or {}
    scores = list(blob.get("scores") or [])
    return scores, str(blob.get("as_of") or "")


def _annotate(row: dict, scores: list[dict]) -> dict:
    hit = match_arena(row, scores)
    item = dict(row)
    item["_cost"] = blended_cost(row)
    item["_quality"] = float((hit or {}).get("rating") or 0)
    item["_arena"] = hit
    if item["_quality"] > 0:
        item["_value"] = item["_quality"] / (1.0 + item["_cost"])
    else:
        item["_value"] = 1.0 / (1.0 + item["_cost"])
    return item


def _public_pick(row: dict, why: str, as_of: str) -> dict:
    arena = row.get("_arena") or {}
    return {
        "id": str(row.get("id") or ""),
        "label": str(row.get("label") or row.get("id") or ""),
        "provider": model_provider(row),
        "in_usd": float(row.get("in_usd") or 0),
        "out_usd": float(row.get("out_usd") or 0),
        "why": why,
        "arena_rating": row.get("_quality") or None,
        "arena_rank": arena.get("rank"),
        "as_of": as_of,
    }


def _value_pick(rows: list[dict], seat_id: str) -> dict | None:
    if not rows:
        return None
    scored = [row for row in rows if row["_quality"] > 0]
    pool = scored or rows
    if seat_id in {"think", "code", "research"} and not scored:
        mid = [row for row in pool if not _cheap_name(row) and not _heavy_name(row)]
        pool = mid or [row for row in pool if not _heavy_name(row)] or pool
        pool.sort(key=lambda row: (row["_cost"], str(row.get("id") or "")))
        return pool[0]
    if scored:
        best_q = max(row["_quality"] for row in scored)
        frontier = [row for row in scored if row["_quality"] >= best_q * 0.95]
        lean = [row for row in frontier if not _heavy_name(row)]
        if lean:
            frontier = lean
        frontier.sort(key=lambda row: (row["_cost"], -row["_quality"], str(row.get("id") or "")))
        return frontier[0]
    pool.sort(key=lambda row: (-row["_value"], row["_cost"], str(row.get("id") or "")))
    return pool[0]


def _cheap_pick(rows: list[dict], seat_id: str) -> dict | None:
    if not rows:
        return None
    pool = list(rows)
    if seat_id == "chat":
        flash = [row for row in pool if "flash" in _blob(row)]
        if flash:
            pool = flash
    if seat_id == "ops":
        pool = [row for row in pool if not _heavy_name(row)] or pool
        cheap = [row for row in pool if _cheap_name(row)]
        if cheap:
            pool = cheap
    scored = [row for row in pool if row["_quality"] > 0]
    if scored and seat_id == "chat":
        floor = max(row["_quality"] for row in scored) * 0.4
        kept = [row for row in scored if row["_quality"] >= floor]
        if kept:
            pool = kept
    pool.sort(key=lambda row: (row["_cost"], -row["_quality"], str(row.get("id") or "")))
    return pool[0]


def auto_model_for_seat(
    seat_id: str,
    models: list[dict] | None = None,
    guides: dict | None = None,
) -> dict:
    """Best Auto pick for a seat. Empty id means nothing connected."""
    spec = next((item for item in SEATS if item["id"] == seat_id), None)
    if spec is None:
        return {"id": "", "why": "unknown seat"}
    rows = [_annotate(row, _scores_for(seat_id, guides)[0]) for row in _for_seat(seat_id, models)]
    as_of = _scores_for(seat_id, guides)[1]
    if not rows:
        return {"id": "", "label": "Auto", "why": "no connected model for this seat", "as_of": as_of}
    if seat_id in {"chat", "ops"}:
        chosen = _cheap_pick(rows, seat_id)
        why = "lowest $ on OpenCode Go" if model_provider(chosen) == "opencode" else "lowest $ among connected wallets"
    else:
        chosen = _value_pick(rows, seat_id)
        if chosen and chosen.get("_quality"):
            why = "best Arena score per dollar on OpenCode Go"
        else:
            why = "mid OpenCode model until Arena maps a score"
        if chosen and model_provider(chosen) == "openrouter":
            why = why.replace("on OpenCode Go", "on OpenRouter (no OpenCode model fit)")
    if chosen is None:
        return {"id": "", "label": "Auto", "why": "no connected model for this seat", "as_of": as_of}
    if not any(token in why.lower() for token in ("opencode", "openrouter", "arena")):
        pass
    return _public_pick(chosen, why, as_of)


def seated_or_auto(
    settings: dict,
    seat_id: str,
    project_seats: dict | None = None,
    models: list[dict] | None = None,
    guides: dict | None = None,
) -> str:
    pinned = seat_model(settings, seat_id, project_seats)
    if pinned:
        return pinned
    return str(auto_model_for_seat(seat_id, models=models, guides=guides).get("id") or "")


def public_auto(models: list[dict] | None = None, guides: dict | None = None) -> dict:
    source = models if models is not None else all_models()
    board = guides if guides is not None else ranking_guides()
    out = {}
    for spec in SEATS:
        out[spec["id"]] = auto_model_for_seat(spec["id"], models=source, guides=board)
    return out


def _prefer_ids(project_id: str | None) -> list[str]:
    from .config import load_settings
    from .org import project_tools

    prefer: list[str] = []
    tools = project_tools(project_id) if project_id else {}
    account_id = str((tools or {}).get("account_id") or "").strip()
    if not account_id:
        account_id = str(load_settings().get("profile_account_id") or "").strip()
    if account_id:
        prefer.append(account_id)
    for item in (tools or {}).get("fallback") or []:
        value = str(item or "").strip()
        if value:
            prefer.append(value)
    return prefer


def resolve_assignment(
    seat_id: str,
    project_id: str | None = None,
    models: list[dict] | None = None,
    guides: dict | None = None,
) -> dict:
    from .config import load_settings
    from .keyring import ordered_accounts
    from .org import project_tools

    settings = load_settings()
    tools = project_tools(project_id) if project_id else {}
    seats = tools.get("seats") if isinstance(tools.get("seats"), dict) else {}
    auto = auto_model_for_seat(seat_id, models=models, guides=guides)
    pinned = seat_model(settings, seat_id, seats)
    model_id = pinned or str(auto.get("id") or "")
    label = str(auto.get("label") or model_id)
    if pinned:
        meta = next((row for row in (models if models is not None else all_models()) if row.get("id") == pinned), None)
        label = str((meta or {}).get("label") or pinned)
    spec = next((item for item in SEATS if item["id"] == seat_id), {})
    engine = str(spec.get("engine") or "")
    provider = model_provider(model_id) or None
    rows = ordered_accounts(prefer=_prefer_ids(project_id), engine=engine or None, provider=provider)
    if not rows:
        rows = ordered_accounts(prefer=_prefer_ids(project_id), engine=engine or None)
    primary = rows[0] if rows else {}
    return {
        "seat": seat_id,
        "engine": engine,
        "model": model_id,
        "model_label": label,
        "source": "pin" if pinned else "auto",
        "why": "pinned" if pinned else auto.get("why") or "",
        "provider": provider or str(primary.get("provider") or ""),
        "account_id": str(primary.get("id") or ""),
        "account_label": str(primary.get("label") or ""),
        "chain": [
            {"id": row["id"], "label": row["label"], "provider": row["provider"]}
            for row in ordered_accounts(prefer=_prefer_ids(project_id), engine=engine or None)
        ],
        "in_usd": auto.get("in_usd"),
        "out_usd": auto.get("out_usd"),
        "arena_rating": auto.get("arena_rating"),
        "as_of": auto.get("as_of") or "",
    }


def public_assignments(models: list[dict] | None = None, guides: dict | None = None) -> dict:
    from .org import ensure_org

    org = ensure_org()
    seats = [spec["id"] for spec in SEATS]
    staff = {seat: resolve_assignment(seat, None, models, guides) for seat in seats}
    ceos = {}
    for row in org.get("projects") or []:
        pid = str(row.get("id") or "")
        if not pid:
            continue
        ceos[pid] = {
            "name": row.get("name") or pid,
            "seats": {seat: resolve_assignment(seat, pid, models, guides) for seat in seats},
        }
    return {"staff": staff, "ceos": ceos}
