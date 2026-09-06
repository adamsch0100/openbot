"""Instance settings. Keys live in .env, never in git."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

from .store import ROOT

ENV_PATH = ROOT / ".env"
SETTINGS_PATH = ROOT / "openbot.local.json"
PIN_ROUNDS = 120_000
SECRET_SETTING_KEYS = ("pin_salt", "pin_hash", "license_key")
DEFAULT_SETTINGS = {
    "default_provider": "opencode",
    "mcp_github": False,
    "operator_name": "",
    "pin_salt": "",
    "pin_hash": "",
    "license_key": "",
    "profile_account_id": "",
    "hermes_skills": "",
    "enable_self_build": False,
    "connectors": {
        "skills": {},
        "mcp": {}
    },
    "models": {
        "cos": "",
        "builder": "",
        "research": "",
        "ops": "",
        "think": "",
    },
    "seats": {
        "chat": {"model": "", "account_id": ""},
        "think": {"model": "", "account_id": ""},
        "code": {"model": "", "account_id": ""},
        "research": {"model": "", "account_id": ""},
        "ops": {"model": "", "account_id": ""},
    },
    "spend_policy": {
        "bind": "payg",
        "mode": "hard",
        "allow_zen_fallback": True,
    },
}

DEFAULT_SPEND_CAP_USD = 5.0
DEFAULT_SPEND_CAP_PERIOD = "week"

MANAGED_KEYS = (
    "OPENBOT_WORK_DIR",
    "OPENBOT_SPEND_CAP_USD",
    "OPENBOT_SPEND_CAP_PERIOD",
)


def hash_pin(pin: str, salt_hex: str | None = None) -> tuple[str, str]:
    cleaned = str(pin or "")
    if len(cleaned) < 4:
        raise ValueError("PIN must be at least 4 characters")
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", cleaned.encode("utf-8"), salt, PIN_ROUNDS)
    return salt.hex(), digest.hex()


def public_operator(settings: dict | None = None) -> dict:
    data = settings if settings is not None else load_settings()
    name = str(data.get("operator_name") or "").strip()
    return {
        "operator_name": name,
        "has_pin": bool(data.get("pin_hash")),
        "has_license": bool(str(data.get("license_key") or "").strip()),
    }


def verify_pin(pin: str) -> bool:
    data = load_settings()
    salt = str(data.get("pin_salt") or "")
    hashed = str(data.get("pin_hash") or "")
    if not salt or not hashed:
        return True
    try:
        _, check = hash_pin(pin, salt)
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(check, hashed)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        value = rest.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def apply_env_file() -> None:
    """Load .env into the process. Existing environment values win."""
    for key, value in _parse_env_file(ENV_PATH).items():
        if os.environ.get(key, "") == "":
            os.environ[key] = value


def _lookup(key: str, file_values: dict[str, str] | None = None) -> str:
    if key in os.environ and os.environ[key] != "":
        return os.environ[key]
    values = file_values if file_values is not None else _parse_env_file(ENV_PATH)
    return values.get(key, "")


def load_config() -> dict:
    file_values = _parse_env_file(ENV_PATH)
    work_dir = _lookup("OPENBOT_WORK_DIR", file_values).strip()
    cap_raw = _lookup("OPENBOT_SPEND_CAP_USD", file_values).strip() or str(DEFAULT_SPEND_CAP_USD)
    period = (_lookup("OPENBOT_SPEND_CAP_PERIOD", file_values).strip() or DEFAULT_SPEND_CAP_PERIOD).lower()
    if period not in {"day", "week", "month"}:
        period = DEFAULT_SPEND_CAP_PERIOD
    try:
        spend_cap_usd = float(cap_raw)
    except ValueError:
        spend_cap_usd = DEFAULT_SPEND_CAP_USD
    if spend_cap_usd < 0:
        spend_cap_usd = DEFAULT_SPEND_CAP_USD
    work_path = Path(work_dir).expanduser() if work_dir else None
    work_ok = bool(work_path and work_path.is_dir())
    settings = load_settings()
    public_settings = {key: value for key, value in settings.items() if key not in SECRET_SETTING_KEYS}
    return {
        "work_dir": str(work_path.resolve()) if work_ok else (work_dir or ""),
        "work_dir_ok": work_ok,
        "spend_cap_usd": spend_cap_usd,
        "spend_cap_period": period,
        "first_run_done": work_ok,
        **public_settings,
        **public_operator(settings),
    }


def upsert_env(updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if ENV_PATH.exists():
        existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    written: set[str] = set()
    out: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in written:
            out.append(f"{key}={value}")
            written.add(key)
    if out and out[-1] != "":
        out.append("")
    ENV_PATH.write_text("\n".join(out), encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def save_work_dir(folder: str) -> dict:
    path = Path(folder).expanduser()
    if not path.exists():
        raise ValueError("folder does not exist")
    if not path.is_dir():
        raise ValueError("path is not a folder")
    resolved = str(path.resolve())
    upsert_env({"OPENBOT_WORK_DIR": resolved})
    return load_config()


def save_spend_cap(usd: float, period: str | None = None) -> dict:
    if usd < 0:
        raise ValueError("spend cap must be >= 0")
    updates = {"OPENBOT_SPEND_CAP_USD": f"{usd:.2f}"}
    if period:
        if period not in {"day", "week", "month"}:
            raise ValueError("period must be day, week, or month")
        updates["OPENBOT_SPEND_CAP_PERIOD"] = period
    upsert_env(updates)
    return load_config()


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    data["models"] = dict(DEFAULT_SETTINGS["models"])
    data["seats"] = {key: dict(value) for key, value in DEFAULT_SETTINGS["seats"].items()}
    data["spend_policy"] = dict(DEFAULT_SETTINGS["spend_policy"])
    if SETTINGS_PATH.is_file():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            if isinstance(raw.get("default_provider"), str) and raw["default_provider"].strip():
                data["default_provider"] = raw["default_provider"].strip()
            if "mcp_github" in raw:
                data["mcp_github"] = bool(raw["mcp_github"])
            if isinstance(raw.get("operator_name"), str):
                data["operator_name"] = raw["operator_name"].strip()[:80]
            if isinstance(raw.get("profile_account_id"), str):
                data["profile_account_id"] = raw["profile_account_id"].strip()
            if isinstance(raw.get("hermes_skills"), str):
                data["hermes_skills"] = raw["hermes_skills"].strip()
            if "enable_self_build" in raw:
                data["enable_self_build"] = bool(raw["enable_self_build"])
            connectors = raw.get("connectors")
            if isinstance(connectors, dict):
                if isinstance(connectors.get("skills"), dict):
                    data["connectors"]["skills"] = connectors["skills"]
                if isinstance(connectors.get("mcp"), dict):
                    data["connectors"]["mcp"] = connectors["mcp"]
            for secret_key in SECRET_SETTING_KEYS:
                value = raw.get(secret_key)
                if isinstance(value, str):
                    data[secret_key] = value
            models = raw.get("models")
            if isinstance(models, dict):
                for key in data["models"]:
                    value = models.get(key)
                    if isinstance(value, str) and value.strip():
                        data["models"][key] = value.strip()
            seats = raw.get("seats")
            if isinstance(seats, dict):
                for key, current in data["seats"].items():
                    patch = seats.get(key)
                    if isinstance(patch, dict):
                        if isinstance(patch.get("model"), str):
                            current["model"] = patch["model"].strip()
                        if isinstance(patch.get("account_id"), str):
                            current["account_id"] = patch["account_id"].strip()
            policy = raw.get("spend_policy")
            if isinstance(policy, dict):
                from .spend import normalize_policy

                data["spend_policy"] = normalize_policy(policy)
            from .models import allowed_for_seat

            for key, current in data["seats"].items():
                if not allowed_for_seat(key, current.get("model") or ""):
                    current["model"] = ""
    return data


def save_settings(patch: dict) -> dict:
    current = load_settings()
    if "default_provider" in patch and patch["default_provider"]:
        current["default_provider"] = str(patch["default_provider"]).strip()
    if "mcp_github" in patch:
        current["mcp_github"] = bool(patch["mcp_github"])
    if "operator_name" in patch:
        current["operator_name"] = str(patch.get("operator_name") or "").strip()[:80]
    if "profile_account_id" in patch:
        current["profile_account_id"] = str(patch.get("profile_account_id") or "").strip()
    if "hermes_skills" in patch:
        current["hermes_skills"] = str(patch.get("hermes_skills") or "").strip()
    if "enable_self_build" in patch:
        current["enable_self_build"] = bool(patch.get("enable_self_build"))
    if "connectors" in patch and isinstance(patch.get("connectors"), dict):
        connectors = patch["connectors"]
        if isinstance(connectors.get("skills"), dict):
            current["connectors"]["skills"] = connectors["skills"]
        if isinstance(connectors.get("mcp"), dict):
            current["connectors"]["mcp"] = connectors["mcp"]
    pin = patch.get("pin")
    if isinstance(pin, str) and pin:
        salt, hashed = hash_pin(pin)
        current["pin_salt"] = salt
        current["pin_hash"] = hashed
    if patch.get("clear_pin"):
        current["pin_salt"] = ""
        current["pin_hash"] = ""
    if "license_key" in patch and isinstance(patch.get("license_key"), str):
        current["license_key"] = patch["license_key"].strip()
    if patch.get("clear_license"):
        current["license_key"] = ""
    if "spend_policy" in patch:
        from .spend import normalize_policy

        current["spend_policy"] = normalize_policy(patch.get("spend_policy"))
    models = patch.get("models")
    if isinstance(models, dict):
        for key in current["models"]:
            value = models.get(key)
            if isinstance(value, str) and value.strip():
                current["models"][key] = value.strip()
    seats = patch.get("seats")
    if isinstance(seats, dict):
        for key, current_seat in current["seats"].items():
            row = seats.get(key)
            if not isinstance(row, dict):
                continue
            if isinstance(row.get("model"), str):
                current_seat["model"] = row["model"].strip()
        current["models"]["cos"] = current["seats"]["chat"].get("model") or ""
        current["models"]["think"] = current["seats"]["think"].get("model") or ""
        current["models"]["builder"] = current["seats"]["code"].get("model") or ""
        current["models"]["research"] = current["seats"]["research"].get("model") or ""
        current["models"]["ops"] = current["seats"]["ops"].get("model") or ""
    if "profile_account_id" in patch:
        for seat in current["seats"].values():
            if isinstance(seat, dict):
                seat["account_id"] = current.get("profile_account_id") or ""
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_config()
