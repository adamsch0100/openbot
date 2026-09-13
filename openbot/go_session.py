"""OpenCode Go session header. One place for Hermes + OpenCode CLI.

Go 400s without x-opencode-session. Hermes does not read OPENCODE_SESSION_ID.
Official Hermes path is extra_headers on a providers entry whose base_url
matches the Go/Zen route. The YAML key must NOT be opencode-go / opencode-zen
— those names shadow the built-in plugin and drop OPENCODE_GO_API_KEY.
OpenCode CLI path is OPENCODE_CONFIG_CONTENT provider headers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

GO_SESSION_HEADER = "x-opencode-session"
GO_BASE_URL = "https://opencode.ai/zen/go/v1"
ZEN_BASE_URL = "https://opencode.ai/zen/v1"
GO_CLI_PROVIDERS = ("opencode", "opencode-go", "zen")
HERMES_OVERLAY_GO = "ottobot-go-session"
HERMES_OVERLAY_ZEN = "ottobot-zen-session"
_MARK_START = "# ottobot-go-session-start"
_MARK_END = "# ottobot-go-session-end"

# Hermes Anthropic-messages on Go drops extra_headers. Do not Auto those.
HERMES_GO_DROP_HEADERS = ("qwen", "minimax")


def session_headers(session_id: str | None) -> dict[str, str]:
    sid = str(session_id or "").strip()
    if not sid:
        return {}
    return {GO_SESSION_HEADER: sid}


def opencode_cli_overlay(session_id: str | None) -> dict:
    headers = session_headers(session_id)
    if not headers:
        return {}
    providers: dict[str, dict] = {}
    for provider_id in GO_CLI_PROVIDERS:
        providers[provider_id] = {"headers": dict(headers)}
    return {"providers": providers}


def merge_opencode_cli_config(config: dict | None, session_id: str | None) -> dict:
    blob = dict(config) if isinstance(config, dict) else {}
    overlay = opencode_cli_overlay(session_id)
    if not overlay:
        return blob
    providers = dict(blob.get("providers") or {})
    for provider_id, extra in overlay["providers"].items():
        row = dict(providers.get(provider_id) or {})
        headers = dict(row.get("headers") or {})
        headers.update(extra.get("headers") or {})
        row["headers"] = headers
        providers[provider_id] = row
    blob["providers"] = providers
    return blob


def bind_go_session_env(env: dict[str, str], session_id: str | None) -> dict[str, str]:
    """Hermes + OpenCode subprocess env. Never log session_id."""
    out = dict(env)
    sid = str(session_id or "").strip()
    if not sid:
        return out
    out["OPENCODE_SESSION_ID"] = sid
    existing: dict = {}
    raw = str(out.get("OPENCODE_CONFIG_CONTENT") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                existing = parsed
        except json.JSONDecodeError:
            existing = {}
    out["OPENCODE_CONFIG_CONTENT"] = json.dumps(merge_opencode_cli_config(existing, sid))
    return out


def _hermes_overlay_inner(session_id: str) -> str:
    sid = str(session_id).strip()
    return (
        f"  {HERMES_OVERLAY_GO}:\n"
        f"    base_url: {GO_BASE_URL}\n"
        "    extra_headers:\n"
        f"      {GO_SESSION_HEADER}: {sid}\n"
        f"  {HERMES_OVERLAY_ZEN}:\n"
        f"    base_url: {ZEN_BASE_URL}\n"
        "    extra_headers:\n"
        f"      {GO_SESSION_HEADER}: {sid}\n"
    )


def _marked_overlay(session_id: str) -> str:
    return f"{_MARK_START}\n{_hermes_overlay_inner(session_id)}{_MARK_END}\n"


def _strip_marked_overlay(text: str) -> str:
    if _MARK_START not in text or _MARK_END not in text:
        return text
    cleaned = re.sub(
        re.escape(_MARK_START) + r".*?" + re.escape(_MARK_END) + r"\n?",
        "",
        text,
        flags=re.S,
    )
    return cleaned


def _drop_extra_providers_blocks(text: str) -> str:
    """A second top-level `providers:` makes Hermes reject the whole YAML."""
    matches = list(re.finditer(r"(?m)^providers:\s*$", text or ""))
    if len(matches) <= 1:
        return text or ""
    return (text or "")[: matches[1].start()].rstrip() + "\n"


def _fix_scalar_model_with_indented_keys(text: str) -> str:
    """`model: foo` then indented keys is invalid YAML (Hermes: line 14 column 3)."""
    return re.sub(
        r"(?m)^model:\s+(\S[^\n]*)$\n(?=  \S)",
        lambda match: f"model:\n  default: {match.group(1).strip()}\n",
        text or "",
        count=1,
    )


def heal_hermes_config_yaml(home: str | Path | None) -> dict:
    """Make CEO config.yaml parse for Hermes. Does not restore Telegram."""
    if not home:
        return {"ok": False, "error": "no home"}
    path = Path(home) / "config.yaml"
    if not path.is_file():
        return {"ok": True, "skipped": True}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return {"ok": False, "error": str(err)[:200]}
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\t", "  ")
    healed = _fix_scalar_model_with_indented_keys(_drop_extra_providers_blocks(_strip_marked_overlay(text)))
    if healed == text:
        return {"ok": True, "changed": False, "path": str(path)}
    try:
        path.write_text(healed if healed.endswith("\n") else healed + "\n", encoding="utf-8")
    except OSError as err:
        return {"ok": False, "error": str(err)[:200]}
    return {"ok": True, "changed": True, "path": str(path)}


def quarantine_unparseable_hermes_yaml(home: str | Path | None) -> dict:
    """If Hermes cannot parse CEO YAML, park it and leave a valid stub. Overrides were already ignored."""
    if not home:
        return {"ok": False, "error": "no home"}
    path = Path(home) / "config.yaml"
    if not path.is_file():
        return {"ok": True, "skipped": True}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return {"ok": False, "error": str(err)[:200]}
    bak = path.with_name("config.yaml.broken")
    try:
        if not bak.is_file():
            bak.write_text(raw, encoding="utf-8")
        path.write_text(
            "# ottobot healed unparseable YAML; original saved as config.yaml.broken\n"
            "runtime:\n"
            "  nofile_soft_limit: 4096\n",
            encoding="utf-8",
        )
    except OSError as err:
        return {"ok": False, "error": str(err)[:200]}
    return {"ok": True, "quarantined": True, "path": str(path), "backup": str(bak)}


def sync_hermes_go_session(home: str | Path | None, session_id: str | None) -> bool:
    """Write Hermes config.yaml extra_headers so Go chat_completions send the header."""
    heal_hermes_config_yaml(home)
    sid = str(session_id or "").strip()
    if not sid or not home:
        return False
    path = Path(home) / "config.yaml"
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return False
    text = _drop_extra_providers_blocks(_strip_marked_overlay(text))
    overlay = _marked_overlay(sid)
    if re.search(r"(?m)^providers:\s*$", text):
        text = re.sub(
            r"(?m)^providers:\s*$",
            "providers:\n" + overlay.rstrip(),
            text,
            count=1,
        )
    else:
        text = (text.rstrip() + "\n\nproviders:\n" + overlay) if text.strip() else ("providers:\n" + overlay)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def resolve_go_session_id(tools: dict | None = None, env: dict | None = None) -> str:
    blob = tools if isinstance(tools, dict) else {}
    sid = str(blob.get("opencode_session_id") or "").strip()
    if sid:
        return sid
    src = env if isinstance(env, dict) else {}
    return str(src.get("OPENCODE_SESSION_ID") or "").strip()
