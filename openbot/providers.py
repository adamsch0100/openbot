"""Providers and OpenCode Zen/Go usage. Keys stay in OpenCode auth.json."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .detect import detect, hermes_home, which

ZEN_USAGE = "https://opencode.ai/zen/go/v1/usage"
ZEN_MODELS = "https://opencode.ai/zen/v1/models"
ZEN_AUTH = "https://opencode.ai/auth"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEYS = "https://openrouter.ai/keys"
NOUS_SUBSCRIBE = "https://portal.nousresearch.com/r/adam-schwartz"

PROVIDERS = [
    {
        "id": "nous",
        "label": "Nous Portal",
        "default": False,
        "hermes_default": True,
        "connect": NOUS_SUBSCRIBE,
        "subscribe": NOUS_SUBSCRIBE,
        "note": "Hermes native subscription. Models plus Tool Gateway. Chat can use Hermes-4; Think/Code/Research/Ops want an agentic Portal model.",
    },
    {
        "id": "opencode",
        "label": "OpenCode",
        "default": True,
        "connect": ZEN_AUTH,
        "note": "One key. Go subscription first, then Zen PAYG at /zen. Quota is /zen/go/v1/usage.",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "default": False,
        "connect": OPENROUTER_KEYS,
        "note": "One key for OpenCode and Hermes. Official /api/v1/models catalog — not rankings.",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "default": False,
        "connect": "https://console.anthropic.com/",
        "note": "Connect inside OpenCode. Keys never enter OpenBot.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "default": False,
        "connect": "https://platform.openai.com/api-keys",
        "note": "Connect inside OpenCode. Keys never enter OpenBot.",
    },
    {
        "id": "google",
        "label": "Google",
        "default": False,
        "connect": "https://aistudio.google.com/",
        "note": "Connect inside OpenCode. Keys never enter OpenBot.",
    },
    {
        "id": "xai",
        "label": "xAI",
        "default": False,
        "connect": "https://console.x.ai/",
        "note": "Grok via API key. The x.com account does not connect.",
    },
]


def _auth_paths() -> list[Path]:
    home = Path.home()
    appdata = os.environ.get("APPDATA") or ""
    local = os.environ.get("LOCALAPPDATA") or ""
    return [
        home / ".local" / "share" / "opencode" / "auth.json",
        Path(appdata) / "opencode" / "auth.json" if appdata else Path(),
        Path(local) / "opencode" / "auth.json" if local else Path(),
        home / ".config" / "opencode" / "auth.json",
    ]


def _read_auth() -> dict:
    for path in _auth_paths():
        if not path or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _secret(entry) -> str | None:
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict):
        for key in ("key", "apiKey", "api_key", "token", "access"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _env_file_has(path: Path, name: str) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    prefix = f"{name}="
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix) and stripped[len(prefix) :].strip().strip("\"'"):
            return True
    return False


def _hermes_auth_ready(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("refresh_token", "access_token", "api_key", "key", "token"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return True
    tokens = entry.get("tokens")
    if isinstance(tokens, dict) and _hermes_auth_ready(tokens):
        return True
    return bool(entry.get("type"))


def nous_portal_connected() -> bool:
    """True when Hermes already has a Portal login or NOUS_API_KEY. Never returns secrets."""
    home = hermes_home()
    if _env_file_has(home / ".env", "NOUS_API_KEY"):
        return True
    path = home / "auth.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    providers = data.get("providers")
    if isinstance(providers, dict) and _hermes_auth_ready(providers.get("nous")):
        return True
    pool = data.get("credential_pool")
    if isinstance(pool, dict) and _hermes_auth_ready(pool.get("nous")):
        return True
    return str(data.get("active_provider") or "").strip().lower() == "nous" and isinstance(
        providers, dict
    ) and "nous" in providers


def connected_provider_ids() -> list[str]:
    blob = _read_auth()
    known = {item["id"] for item in PROVIDERS} | {"zen", "opencode-zen"}
    names: list[str] = []
    for key, value in blob.items():
        if key.startswith("_") or key in {"version", "type"}:
            continue
        if str(key) not in known:
            continue
        if _secret(value) or (isinstance(value, dict) and value.get("type")):
            names.append(str(key))
    try:
        from .keyring import keyring_provider_ids

        for name in keyring_provider_ids():
            if name not in names:
                names.append(name)
    except Exception:
        pass
    if nous_portal_connected() and "nous" not in names:
        names.append("nous")
    return names


def _opencode_key() -> str | None:
    blob = _read_auth()
    for name in ("opencode", "zen", "opencode-zen"):
        secret = _secret(blob.get(name))
        if secret:
            return secret
    try:
        from .keyring import accounts_for

        rows = accounts_for("opencode")
        if rows and rows[0].get("key"):
            return str(rows[0]["key"])
    except Exception:
        pass
    return None


def _http_json(url: str, token: str | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json", "User-Agent": "openbot/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw[:2000]}
    except urllib.error.HTTPError as err:
        return err.code, {"error": str(err)}
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return 0, {"error": str(err)}


_OR_CACHE: dict = {"at": 0.0, "prices": {}, "models": []}
_OR_LOCK = threading.Lock()
_OR_FETCHING = False
_ZEN_CACHE: dict = {"at": 0.0, "models": []}
_ZEN_LOCK = threading.Lock()
_ZEN_FETCHING = False


def _openrouter_key() -> str | None:
    blob = _read_auth()
    secret = _secret(blob.get("openrouter"))
    if secret:
        return secret
    try:
        from .keyring import accounts_for

        rows = accounts_for("openrouter")
        if rows and rows[0].get("key"):
            return str(rows[0]["key"])
    except Exception:
        pass
    return None


def _or_row(row: dict) -> dict | None:
    model_id = str(row.get("id") or "").strip()
    if not model_id:
        return None
    lower = model_id.lower()
    if ":batch" in lower:
        return None
    if any(
        part in lower
        for part in (
            "embed",
            "whisper",
            "tts-",
            "/tts",
            "moderation",
            "-image",
            "image-preview",
            "content-safety",
        )
    ):
        return None
    arch = row.get("architecture") if isinstance(row.get("architecture"), dict) else {}
    outputs = [str(item).lower() for item in (arch.get("output_modalities") or [])]
    inputs = [str(item).lower() for item in (arch.get("input_modalities") or [])]
    if outputs and "text" not in outputs:
        return None
    if inputs and "text" not in inputs:
        return None
    params = {str(item).lower() for item in (row.get("supported_parameters") or [])}
    reasoning_blob = row.get("reasoning")
    tools = "tools" in params
    reasoning = bool(reasoning_blob) or "reasoning" in params or "include_reasoning" in params
    if not tools and not reasoning:
        return None
    pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
    try:
        in_usd = round(float(pricing.get("prompt") or 0) * 1_000_000, 4)
        out_usd = round(float(pricing.get("completion") or 0) * 1_000_000, 4)
    except (TypeError, ValueError):
        in_usd, out_usd = 0.0, 0.0
    try:
        context = int(row.get("context_length") or 0)
    except (TypeError, ValueError):
        context = 0
    top = row.get("top_provider") if isinstance(row.get("top_provider"), dict) else {}
    try:
        max_out = int(top.get("max_completion_tokens") or 0)
    except (TypeError, ValueError):
        max_out = 0
    label = str(row.get("name") or model_id).strip()
    author = model_id.split("/", 1)[0]
    return {
        "id": f"openrouter/{model_id}",
        "or_id": model_id,
        "label": label,
        "author": author,
        "provider": "openrouter",
        "in_usd": in_usd,
        "out_usd": out_usd,
        "reasoning": reasoning,
        "tools": tools,
        "code": tools,
        "context": context,
        "max_out": max_out,
        "badge": "OpenRouter",
        "engines": ("OpenCode", "Hermes Agent"),
        "family": "openrouter",
    }


def _refresh_openrouter_catalog() -> None:
    global _OR_FETCHING
    try:
        status, payload = _http_json(OPENROUTER_MODELS, _openrouter_key())
        prices: dict[str, tuple[float, float]] = {}
        models: list[dict] = []
        if status == 200 and isinstance(payload, dict):
            for row in payload.get("data") or []:
                if not isinstance(row, dict):
                    continue
                parsed = _or_row(row)
                if not parsed:
                    continue
                models.append(parsed)
                prices[parsed["or_id"]] = (parsed["in_usd"], parsed["out_usd"])
        with _OR_LOCK:
            _OR_CACHE["at"] = time.time()
            if models:
                _OR_CACHE["prices"] = prices
                _OR_CACHE["models"] = models
    finally:
        _OR_FETCHING = False


def _ensure_openrouter(*, wait_empty: bool = False) -> None:
    global _OR_FETCHING
    wait = False
    start = False
    with _OR_LOCK:
        age = time.time() - float(_OR_CACHE["at"] or 0)
        empty = not _OR_CACHE["models"]
        stale = empty or age > 1800
        if stale and not _OR_FETCHING:
            _OR_FETCHING = True
            if wait_empty and empty:
                wait = True
            else:
                start = True
    if wait:
        _refresh_openrouter_catalog()
        return
    if start:
        threading.Thread(target=_refresh_openrouter_catalog, name="or-catalog", daemon=True).start()


def openrouter_prices() -> dict[str, tuple[float, float]]:
    """USD per 1M tokens from official /api/v1/models. Not rankings."""
    _ensure_openrouter(wait_empty=True)
    with _OR_LOCK:
        return dict(_OR_CACHE["prices"])


def openrouter_models() -> list[dict]:
    """Live OpenRouter catalog (official models API). Not rankings."""
    _ensure_openrouter(wait_empty=True)
    with _OR_LOCK:
        return list(_OR_CACHE["models"])


def _pretty_zen_id(model_id: str) -> str:
    raw = (model_id or "").strip()
    if raw.startswith("opencode/"):
        raw = raw.split("/", 1)[1]
    return raw.replace("-", " ").replace("_", " ").strip() or raw


def _zen_row(row: dict) -> dict | None:
    model_id = str(row.get("id") or "").strip()
    if not model_id or row.get("object") not in {None, "model"}:
        return None
    lower = model_id.lower()
    if any(part in lower for part in ("embed", "whisper", "tts", "moderation")):
        return None
    cheap = any(token in lower for token in ("nano", "mini", "haiku", "lite", "flash-lite", "free"))
    in_usd, out_usd = _zen_cost(row)
    return {
        "id": f"opencode/{model_id}" if "/" not in model_id else model_id,
        "label": str(row.get("name") or "").strip() or _pretty_zen_id(model_id),
        "provider": "opencode",
        "in_usd": in_usd,
        "out_usd": out_usd,
        "reasoning": not cheap,
        "tools": True,
        "code": True,
        "badge": "OpenCode Zen",
        "engines": ("OpenCode", "Hermes Agent"),
        "family": "go",
    }


def _zen_cost(row: dict) -> tuple[float, float]:
    blob = row.get("cost") if isinstance(row.get("cost"), dict) else None
    if blob is None:
        blob = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
    def _num(*keys: str) -> float:
        for key in keys:
            try:
                return float(blob.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0.0
    inn = _num("input", "prompt", "in")
    out = _num("output", "completion", "out")
    if 0 < inn < 0.01:
        inn *= 1_000_000
    if 0 < out < 0.01:
        out *= 1_000_000
    return round(inn, 4), round(out, 4)


def _refresh_zen_models() -> None:
    global _ZEN_FETCHING
    try:
        token = _opencode_key()
        models: list[dict] = []
        if token:
            status, payload = _http_json(ZEN_MODELS, token)
            rows = []
            if status == 200 and isinstance(payload, dict):
                rows = payload.get("data") or payload.get("models") or []
            elif status == 200 and isinstance(payload, list):
                rows = payload
            for row in rows:
                if not isinstance(row, dict):
                    continue
                parsed = _zen_row(row)
                if parsed:
                    models.append(parsed)
        with _ZEN_LOCK:
            _ZEN_CACHE["at"] = time.time()
            if models:
                _ZEN_CACHE["models"] = models
    finally:
        _ZEN_FETCHING = False


def zen_models() -> list[dict]:
    """Live OpenCode Go / Zen model ids. First call waits so Auto can stay on Go."""
    global _ZEN_FETCHING
    wait = False
    start = False
    with _ZEN_LOCK:
        age = time.time() - float(_ZEN_CACHE["at"] or 0)
        empty = not _ZEN_CACHE["models"]
        stale = empty or age > 1800
        if stale and not _ZEN_FETCHING:
            _ZEN_FETCHING = True
            if empty:
                wait = True
            else:
                start = True
    if wait:
        _refresh_zen_models()
        with _ZEN_LOCK:
            return list(_ZEN_CACHE["models"])
    if start:
        threading.Thread(target=_refresh_zen_models, name="zen-models", daemon=True).start()
    with _ZEN_LOCK:
        return list(_ZEN_CACHE["models"])


def zen_usage() -> dict:
    token = _opencode_key()
    if not token:
        return {
            "connected": False,
            "source": None,
            "auth_url": ZEN_AUTH,
            "note": "Connect OpenCode Zen in the OpenCode workspace (/connect) or at opencode.ai/auth. OpenBot does not store the key.",
        }
    status, payload = _http_json(ZEN_USAGE, token)
    models_status, models = _http_json(ZEN_MODELS, token)
    return {
        "connected": True,
        "source": "zen/go",
        "http_status": status,
        "usage": payload if status == 200 else None,
        "usage_error": None if status == 200 else payload,
        "models_http": models_status,
        "models": models if models_status == 200 else None,
        "auth_url": ZEN_AUTH,
        "note": "Go/Zen usage from official API when the workspace has a Go plan. Credit wallet balance is not on the public API yet.",
    }


def local_stats() -> dict:
    binary = which("opencode")
    if not binary:
        return {"ok": False, "error": "opencode missing"}
    try:
        proc = subprocess.run(
            [binary, "stats", "--days", "7"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return {"ok": False, "error": str(err)}
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return {"ok": proc.returncode == 0, "text": out[-4000:], "code": proc.returncode}


def provider_status() -> dict:
    connected = connected_provider_ids()
    catalog = []
    for item in PROVIDERS:
        row = dict(item)
        row["connected"] = item["id"] in connected or (
            item["id"] == "opencode" and ("opencode" in connected or "zen" in connected)
        )
        catalog.append(row)
    return {
        "default_provider": "opencode",
        "providers": catalog,
        "connected": connected,
        "zen": zen_usage(),
        "local_stats": local_stats(),
        "engines": detect(),
    }
