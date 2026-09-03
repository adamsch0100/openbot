"""Local keyring. Keys never go to git or back to the browser."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from .config import upsert_env
from .detect import hermes_home
from .providers import NOUS_SUBSCRIBE, _auth_paths
from .store import ROOT

SECRETS_PATH = ROOT / "secrets.local.json"
LOGIN_FILE = ".openbot-logins.json"
_EMPTY_UNTIL: dict[str, float] = {}
_EMPTY_TTL = 6 * 3600.0
PASTEABLE = (
    {
        "id": "nous",
        "label": "Nous Portal",
        "engines": ["Hermes Agent"],
        "auth_id": None,
        "env": ("NOUS_API_KEY",),
        "subscribe": NOUS_SUBSCRIBE,
        "note": "Hermes native subscription. Subscribe, then paste the Portal API key or connect in the Hermes tab with hermes portal. Hermes-4 is for Chat; work seats want an agentic Portal model.",
    },
    {
        "id": "opencode",
        "label": "OpenCode",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "opencode",
        "env": ("OPENCODE_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY"),
        "note": "Builder and Chat backup. Go subscription quota first, then Zen PAYG when Go is empty.",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "openrouter",
        "env": ("OPENROUTER_API_KEY",),
        "note": "One key, both engines. Official models API for the picker — we do not use their rankings.",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "anthropic",
        "env": ("ANTHROPIC_API_KEY",),
        "note": "Claude via API key.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "openai",
        "env": ("OPENAI_API_KEY",),
        "note": "GPT via API key.",
    },
    {
        "id": "google",
        "label": "Google",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "google",
        "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "note": "Gemini / AI Studio key.",
    },
    {
        "id": "xai",
        "label": "xAI (Grok API)",
        "engines": ["OpenCode", "Hermes Agent"],
        "auth_id": "xai",
        "env": ("XAI_API_KEY",),
        "note": "Grok API key. The x.com Grok account does not connect.",
    },
)
BLOCKED = (
    {
        "id": "cursor",
        "label": "Cursor",
        "connects": False,
        "note": "Cursor IDE login is not an inference API. It will not connect here.",
    },
    {
        "id": "grok-x",
        "label": "Grok (x.com)",
        "connects": False,
        "note": "The consumer Grok account will not connect. Use an xAI API key instead.",
    },
)
SEATS = (
    {
        "id": "chat",
        "label": "Chat",
        "preset": "cos",
        "engine": "Hermes Agent",
        "note": "Everyday talk. Cheap model, no tools. On Nous Portal, Hermes-4 is Chat. Status still reads INDEX for free.",
    },
    {
        "id": "think",
        "label": "Think",
        "preset": "think",
        "engine": "Hermes Agent",
        "note": "Hard reasoning. Use when Chat is not enough.",
    },
    {
        "id": "code",
        "label": "Code",
        "preset": "builder",
        "engine": "OpenCode",
        "note": "Builder. OpenCode run in the project folder.",
    },
    {
        "id": "research",
        "label": "Research",
        "preset": "research",
        "engine": "Hermes Agent",
        "note": "Fetch first, snapshot only if the page is an app.",
    },
    {
        "id": "ops",
        "label": "Ops",
        "preset": "ops",
        "engine": "Hermes Agent",
        "note": "Cron in Hermes. OpenBot does not invent a second scheduler.",
    },
)


_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PASS_KV = re.compile(r"(?i)\b(?:password|passwd|pwd)\s*(?:is|=|:)\s*(\S+)")
_USER_KV = re.compile(r"(?i)\b(?:user(?:name)?|login|email)\s*(?:is|=|:)\s*(\S+)")
_CHAT_SKIP = {"and", "is", "the", "login", "for", "a", "to", "on"}


def _blank() -> dict:
    return {"accounts": [], "fallback": [], "active": {}, "hermes_instances": [], "logins": []}


def _parse_logins(raw) -> list[dict]:
    out: list[dict] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "").strip()
        password = str(row.get("password") or "")
        if not username and not str(password).strip():
            continue
        out.append(
            {
                "id": str(row.get("id") or uuid.uuid4().hex[:8]),
                "label": str(row.get("label") or row.get("site") or username).strip(),
                "site": str(row.get("site") or "").strip(),
                "username": username,
                "password": password,
                "project_id": str(row.get("project_id") or "").strip(),
                "auto": bool(row.get("auto")),
            }
        )
    return out


def _public_login(row: dict) -> dict:
    return {
        "id": row.get("id") or "",
        "label": row.get("label") or "",
        "site": row.get("site") or "",
        "username": row.get("username") or "",
        "project_id": row.get("project_id") or "",
        "auto": bool(row.get("auto")),
        "has_password": bool(str(row.get("password") or "").strip()),
    }


def parse_chat_login(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    password = ""
    username = ""
    pass_match = _PASS_KV.search(raw)
    if pass_match:
        password = pass_match.group(1).strip().strip(".,;\"'")
    user_match = _USER_KV.search(raw)
    if user_match:
        username = user_match.group(1).strip().strip(".,;\"'")
    email = _EMAIL.search(raw)
    if email:
        username = username or email.group(0)
    if not password:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) == 2 and _EMAIL.search(lines[0]):
            token = lines[1]
            if " " not in token and len(token) >= 4:
                username = _EMAIL.search(lines[0]).group(0)
                password = token
        elif email:
            rest = _PASS_KV.sub(" ", _USER_KV.sub(" ", _EMAIL.sub(" ", raw)))
            tokens = [
                part
                for part in re.split(r"\s+", rest.strip())
                if part and part.lower() not in _CHAT_SKIP
            ]
            if len(tokens) == 1:
                password = tokens[0].strip(".,;\"'")
    if not username or not password or password.lower() in {"password", "passwd", "pwd"}:
        return None
    site = ""
    url = re.search(r"https?://[^\s]+", raw, re.I)
    if url:
        site = url.group(0).rstrip(").,]")
    return {"username": username, "password": password, "site": site}


def redact_chat_login(text: str) -> str:
    if parse_chat_login(text) is None:
        return text or ""
    return "Login given on the board (not stored in chat)."


def hermes_home_for_project(project_id: str | None) -> str:
    pid = str(project_id or "").strip()
    if not pid:
        return ""
    from .org import ensure_org, project_tools

    tools = project_tools(pid)
    home = str((tools or {}).get("hermes_home") or "").strip()
    if home:
        return home
    for row in ensure_org().get("projects") or []:
        if str(row.get("id") or "") != pid:
            continue
        nested = row.get("tools") if isinstance(row.get("tools"), dict) else {}
        return str(row.get("hermes_home") or nested.get("hermes_home") or "").strip()
    return ""


def logins_for_project(project_id: str | None) -> list[dict]:
    pid = str(project_id or "").strip()
    rows = []
    for row in _load().get("logins") or []:
        owner = str(row.get("project_id") or "").strip()
        if owner and owner != pid:
            continue
        rows.append(row)
    return rows


def public_logins(project_id: str | None = None) -> list[dict]:
    rows = logins_for_project(project_id) if project_id else (_load().get("logins") or [])
    return [_public_login(row) for row in rows]


def _load() -> dict:
    data = _blank()
    if not SECRETS_PATH.is_file():
        return data
    try:
        raw = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    accounts = []
    for row in raw.get("accounts") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        provider = str(row.get("provider") or "").strip()
        if not provider:
            continue
        accounts.append(
            {
                "id": str(row.get("id") or uuid.uuid4().hex[:8]),
                "provider": provider,
                "label": str(row.get("label") or provider).strip(),
                "key": key,
            }
        )
    data["accounts"] = accounts
    fallback = raw.get("fallback")
    if isinstance(fallback, list):
        data["fallback"] = [str(item) for item in fallback if str(item).strip()]
    active = raw.get("active")
    if isinstance(active, dict):
        data["active"] = {str(k): str(v) for k, v in active.items() if v}
    instances = []
    for row in raw.get("hermes_instances") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        key = str(row.get("key") or "").strip()
        if not url or not key:
            continue
        instances.append(
            {
                "id": str(row.get("id") or uuid.uuid4().hex[:8]),
                "label": str(row.get("label") or url).strip(),
                "url": url,
                "key": key,
            }
        )
    data["hermes_instances"] = instances
    data["logins"] = _parse_logins(raw.get("logins"))
    return data


def _save(data: dict) -> None:
    SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def keyring_provider_ids() -> list[str]:
    known = {item["id"] for item in PASTEABLE}
    return [
        str(row["provider"])
        for row in _load()["accounts"]
        if row.get("key") and row.get("provider") in known
    ]


def public_keyring() -> dict:
    data = _load()
    known = {item["id"] for item in PASTEABLE}
    accounts = []
    for row in data["accounts"]:
        if row.get("provider") not in known:
            continue
        accounts.append(
            {
                "id": row["id"],
                "provider": row["provider"],
                "label": row["label"],
                "has_key": bool(row.get("key")),
            }
        )
    from .providers import nous_portal_connected

    return {
        "accounts": accounts,
        "fallback": data.get("fallback") or [row["id"] for row in accounts],
        "active": data.get("active") or {},
        "catalog": list(PASTEABLE),
        "blocked": list(BLOCKED),
        "seats": list(SEATS),
        "path": str(SECRETS_PATH.name),
        "nous_portal": nous_portal_connected(),
        "subscribe": NOUS_SUBSCRIBE,
        "logins": public_logins(),
        "note": "Keys and site logins stay in secrets.local.json. Passwords are never returned to this UI or written to git. Nous Portal is the standard Hermes wallet when connected.",
    }


def add_login(
    label: str,
    site: str,
    username: str,
    password: str,
    project_id: str | None = None,
    auto: bool = False,
) -> dict:
    user = (username or "").strip()
    secret = str(password or "")
    if not user or not secret.strip():
        raise ValueError("username and password required")
    data = _load()
    data.setdefault("logins", []).append(
        {
            "id": uuid.uuid4().hex[:8],
            "label": (label or "").strip() or (site or "").strip() or user,
            "site": (site or "").strip(),
            "username": user,
            "password": secret,
            "project_id": str(project_id or "").strip(),
            "auto": bool(auto),
        }
    )
    _save(data)
    return public_keyring()


def delete_login(login_id: str) -> dict:
    data = _load()
    before = len(data.get("logins") or [])
    data["logins"] = [row for row in (data.get("logins") or []) if row.get("id") != login_id]
    if len(data["logins"]) == before:
        raise ValueError("login not found")
    _save(data)
    return public_keyring()


def stage_job_logins(
    project_id: str | None,
    home: str | Path | None,
    extra: dict | None = None,
    only_auto: bool = True,
) -> str:
    folder = Path(home) if home else None
    if folder is None or not folder.is_dir():
        return ""
    path = folder / LOGIN_FILE
    rows = logins_for_project(project_id)
    if only_auto:
        rows = [row for row in rows if row.get("auto")]
    if extra:
        rows = rows + [extra]
    if not rows:
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        return ""
    payload = [
        {
            "label": row.get("label") or "",
            "site": row.get("site") or "",
            "username": row.get("username") or "",
            "password": row.get("password") or "",
        }
        for row in rows
        if str(row.get("username") or "").strip() and str(row.get("password") or "").strip()
    ]
    if not payload:
        return ""
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path)


def staged_logins_ready(home: str | Path | None) -> bool:
    folder = Path(home) if home else None
    return bool(folder and (folder / LOGIN_FILE).is_file())


def use_login(
    *,
    project_id: str | None = None,
    login_id: str | None = None,
    label: str = "",
    site: str = "",
    username: str = "",
    password: str = "",
    save: bool = False,
    auto: bool = False,
    home: str | None = None,
) -> dict:
    extra = None
    saved = False
    if login_id:
        row = next((item for item in _load().get("logins") or [] if item.get("id") == login_id), None)
        if row is None:
            raise ValueError("login not found")
        extra = row
    else:
        user = (username or "").strip()
        secret = str(password or "")
        if not user or not secret.strip():
            raise ValueError("username and password required")
        extra = {
            "label": (label or "").strip() or (site or "").strip() or user,
            "site": (site or "").strip(),
            "username": user,
            "password": secret,
            "project_id": str(project_id or "").strip(),
            "auto": bool(auto),
        }
        if save:
            add_login(
                extra["label"],
                extra["site"],
                extra["username"],
                extra["password"],
                extra["project_id"],
                auto=auto,
            )
            saved = True
    target = (home or "").strip() or hermes_home_for_project(project_id)
    staged = stage_job_logins(project_id, target, extra=extra, only_auto=True)
    return {
        "ok": True,
        "saved": saved or bool(login_id),
        "staged": bool(staged),
        "file": LOGIN_FILE,
        "keyring": public_keyring(),
    }


def add_account(provider: str, key: str, label: str | None = None) -> dict:
    provider = (provider or "").strip()
    secret = (key or "").strip()
    if provider not in {item["id"] for item in PASTEABLE}:
        raise ValueError("unknown provider")
    if not secret:
        raise ValueError("empty key")
    data = _load()
    account_id = uuid.uuid4().hex[:8]
    nice = (label or "").strip() or f"{provider} {sum(1 for row in data['accounts'] if row['provider'] == provider) + 1}"
    data["accounts"].append(
        {"id": account_id, "provider": provider, "label": nice, "key": secret}
    )
    chain = [item for item in (data.get("fallback") or []) if item != account_id]
    if provider == "nous":
        data["fallback"] = [account_id] + chain
    else:
        data["fallback"] = chain + [account_id]
    data["active"][provider] = account_id
    _save(data)
    activate_account(account_id)
    return public_keyring()


def set_fallback(order: list[str]) -> dict:
    data = _load()
    known = {row["id"] for row in data["accounts"]}
    data["fallback"] = [item for item in order if item in known]
    _save(data)
    return public_keyring()


def rename_account(account_id: str, label: str) -> dict:
    nice = (label or "").strip()
    if not nice:
        raise ValueError("label required")
    data = _load()
    row = next((item for item in data["accounts"] if item["id"] == account_id), None)
    if row is None:
        raise ValueError("account not found")
    row["label"] = nice[:80]
    _save(data)
    return public_keyring()


def delete_account(account_id: str) -> dict:
    data = _load()
    data["accounts"] = [row for row in data["accounts"] if row["id"] != account_id]
    data["fallback"] = [item for item in data["fallback"] if item != account_id]
    data["active"] = {k: v for k, v in data["active"].items() if v != account_id}
    _save(data)
    return public_keyring()


def accounts_for(provider: str) -> list[dict]:
    data = _load()
    fallback = data.get("fallback") or []
    ranked = {account_id: i for i, account_id in enumerate(fallback)}
    rows = [row for row in data["accounts"] if row["provider"] == provider and row.get("key")]
    rows.sort(key=lambda row: ranked.get(row["id"], 999))
    return rows


def activate_account(account_id: str) -> dict:
    data = _load()
    row = next((item for item in data["accounts"] if item["id"] == account_id), None)
    if not row or not row.get("key"):
        raise ValueError("account not found")
    spec = next((item for item in PASTEABLE if item["id"] == row["provider"]), None)
    if spec is None:
        raise ValueError("unknown provider")
    if spec.get("auth_id"):
        _write_opencode_auth(str(spec["auth_id"]), row["key"])
    env_updates = {name: row["key"] for name in spec.get("env") or ()}
    if row["provider"] == "opencode":
        env_updates.setdefault("OPENCODE_ZEN_API_KEY", row["key"])
        env_updates.setdefault("OPENCODE_GO_API_KEY", row["key"])
    if env_updates:
        _write_hermes_env(env_updates)
        upsert_env(env_updates)
    data["active"][row["provider"]] = account_id
    _save(data)
    return public_keyring()


def ordered_account_ids(
    *,
    prefer: list[str] | None = None,
    provider: str | None = None,
    engine: str | None = None,
) -> list[str]:
    """Keyring order is the wallet chain. Do not jump a later provider to the front."""
    data = _load()
    instance_chain = data.get("fallback") or [row["id"] for row in data["accounts"]]
    chain: list[str] = []
    for account_id in list(prefer or []) + list(instance_chain):
        if account_id and account_id not in chain:
            chain.append(account_id)
    out: list[str] = []
    for account_id in chain:
        row = next((item for item in data["accounts"] if item["id"] == account_id), None)
        if not row or not row.get("key"):
            continue
        spec = next((item for item in PASTEABLE if item["id"] == row["provider"]), None)
        if spec is None:
            continue
        if engine and engine not in spec["engines"] and engine != "both":
            continue
        if provider and row["provider"] != provider:
            continue
        out.append(account_id)
    return out


def ordered_accounts(
    *,
    prefer: list[str] | None = None,
    provider: str | None = None,
    engine: str | None = None,
) -> list[dict]:
    data = _load()
    by_id = {row["id"]: row for row in data["accounts"]}
    rows: list[dict] = []
    for account_id in ordered_account_ids(prefer=prefer, provider=provider, engine=engine):
        row = by_id.get(account_id)
        if row:
            rows.append(row)
    return rows


def primary_provider(prefer: list[str] | None = None) -> str:
    from .config import load_settings

    pin = str(load_settings().get("profile_account_id") or "").strip()
    extra = list(prefer or [])
    if pin:
        extra.append(pin)
    rows = ordered_accounts(prefer=extra, engine="Hermes Agent")
    if rows:
        return str(rows[0]["provider"])
    return "opencode"


def mark_wallet_empty(account_id: str) -> None:
    """Skip this OpenCode (or other) account for a few hours after a dead-wallet 401."""
    aid = str(account_id or "").strip()
    if aid:
        _EMPTY_UNTIL[aid] = time.time() + _EMPTY_TTL


def wallet_marked_empty(account_id: str) -> bool:
    aid = str(account_id or "").strip()
    until = float(_EMPTY_UNTIL.get(aid) or 0)
    if until <= time.time():
        _EMPTY_UNTIL.pop(aid, None)
        return False
    return True


def clear_marked_empty() -> None:
    _EMPTY_UNTIL.clear()


def activate_for_engine(
    engine: str,
    prefer: list[str] | None = None,
    provider: str | None = None,
) -> str | None:
    """Push the first live key in keyring order. Provider filter stays in that order — no jumping."""
    ids = ordered_account_ids(prefer=prefer, provider=provider, engine=engine)
    if not ids:
        return None
    live = [account_id for account_id in ids if not wallet_marked_empty(account_id)]
    chosen = (live or ids)[0]
    activate_account(chosen)
    return chosen


def _auth_file() -> Path:
    for path in _auth_paths():
        if path and path.is_file():
            return path
    appdata = os.environ.get("APPDATA") or ""
    if appdata:
        return Path(appdata) / "opencode" / "auth.json"
    return Path.home() / ".config" / "opencode" / "auth.json"


def _write_opencode_auth(provider_id: str, key: str) -> None:
    path = _auth_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob: dict = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                blob = raw
        except (OSError, json.JSONDecodeError):
            blob = {}
    blob[provider_id] = {"type": "api", "key": key}
    path.write_text(json.dumps(blob, indent=2), encoding="utf-8")


def _write_hermes_env(updates: dict[str, str]) -> None:
    path = hermes_home() / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        existing = path.read_text(encoding="utf-8").splitlines()
    written: set[str] = set()
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.partition("=")[0].strip()
            if name in updates:
                out.append(f"{name}={updates[name]}")
                written.add(name)
                continue
        out.append(line)
    for name, value in updates.items():
        if name not in written:
            out.append(f"{name}={value}")
    if out and out[-1] != "":
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")
