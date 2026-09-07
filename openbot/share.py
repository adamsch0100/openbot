"""Per-CEO human collaborators. Owner keeps billing and vault; members get a scoped session."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import store as store_mod
from .config import hash_pin, public_operator
from .store import list_jobs

INVITE_EXPIRE_DAYS = 7
MAX_MEMBERS = 3
SECRET_MIN = 4
PERM_KEYS = (
    "chat_read",
    "chat_write",
    "jobs_view",
    "jobs_run",
    "index_edit",
    "approve_needs_you",
    "engines_view",
    "workers_manage",
    "wiring_edit",
)
DEFAULT_PERMISSIONS = {
    "chat_read": True,
    "chat_write": True,
    "jobs_view": True,
    "jobs_run": True,
    "index_edit": True,
    "approve_needs_you": False,
    "engines_view": True,
    "workers_manage": False,
    "wiring_edit": False,
}
WORK_PRESETS = {"builder", "think", "research", "ops"}
OWNER_ONLY_PREFIXES = (
    "/api/keys",
    "/api/logins",
    "/api/connections",
    "/api/control/",
    "/api/hermes/import",
    "/api/hermes/instances",
)
_LOCK = threading.Lock()
_SESSION_MEMBERS: dict[str, str] = {}


def shares_path() -> Path:
    return store_mod.ROOT / "shares.local.json"


def _empty() -> dict:
    return {"members": [], "invites": []}


def _load() -> dict:
    path = shares_path()
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    members = data.get("members")
    invites = data.get("invites")
    data["members"] = members if isinstance(members, list) else []
    data["invites"] = invites if isinstance(invites, list) else []
    return data


def _save(data: dict) -> None:
    path = shares_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()


def merge_permissions(raw) -> dict:
    out = dict(DEFAULT_PERMISSIONS)
    if isinstance(raw, dict):
        for key in PERM_KEYS:
            if key in raw:
                out[key] = bool(raw.get(key))
    return out


def _parse_when(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_permissions() -> dict:
    return dict(DEFAULT_PERMISSIONS)


def public_member(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "project_id": str(row.get("project_id") or ""),
        "display_name": str(row.get("display_name") or ""),
        "role": str(row.get("role") or "collaborator"),
        "permissions": merge_permissions(row.get("permissions")),
        "spend_ceiling_usd_day": row.get("spend_ceiling_usd_day"),
        "require_approval_over_usd": row.get("require_approval_over_usd"),
        "seats_mode": str(row.get("seats_mode") or "inherit"),
        "status": str(row.get("status") or "active"),
        "created_at": str(row.get("created_at") or ""),
        "last_active_at": str(row.get("last_active_at") or ""),
    }


def public_invite(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "project_id": str(row.get("project_id") or ""),
        "expires_at": str(row.get("expires_at") or ""),
        "max_uses": int(row.get("max_uses") or 1),
        "uses": int(row.get("uses") or 0),
        "status": str(row.get("status") or "active"),
        "created_at": str(row.get("created_at") or ""),
        "permissions": merge_permissions(row.get("permissions")),
        "spend_ceiling_usd_day": row.get("spend_ceiling_usd_day"),
        "require_approval_over_usd": row.get("require_approval_over_usd"),
        "seats_mode": str(row.get("seats_mode") or "inherit"),
    }


def _active_members(data: dict, project_id: str) -> list[dict]:
    pid = str(project_id or "").strip()
    rows = []
    for row in data.get("members") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("project_id") or "") != pid:
            continue
        if str(row.get("status") or "active") == "removed":
            continue
        rows.append(row)
    return rows


def project_share(project_id: str) -> dict:
    data = _load()
    pid = str(project_id or "").strip()
    members = [public_member(row) for row in _active_members(data, pid)]
    invites = [
        public_invite(row)
        for row in (data.get("invites") or [])
        if isinstance(row, dict)
        and str(row.get("project_id") or "") == pid
        and str(row.get("status") or "active") == "active"
    ]
    return {"project_id": pid, "members": members, "invites": invites, "max_members": MAX_MEMBERS}


def create_invite(
    project_id: str,
    *,
    permissions=None,
    expires_days: int | None = None,
    max_uses: int = 1,
    spend_ceiling_usd_day=None,
    require_approval_over_usd=None,
    seats_mode: str = "inherit",
) -> dict:
    pid = str(project_id or "").strip()
    if not pid:
        raise ValueError("CEO required")
    data = _load()
    live = [row for row in _active_members(data, pid) if str(row.get("status") or "") == "active"]
    if len(live) >= MAX_MEMBERS:
        raise ValueError(f"this CEO already has {MAX_MEMBERS} collaborators")
    days = INVITE_EXPIRE_DAYS if expires_days is None else int(expires_days)
    if days < 1 or days > 90:
        raise ValueError("invite expiry must be 1–90 days")
    uses = int(max_uses or 1)
    if uses < 1 or uses > 20:
        raise ValueError("max uses must be 1–20")
    raw = secrets.token_urlsafe(24)
    now = _utc_now()
    row = {
        "id": secrets.token_hex(6),
        "token_hash": _hash_token(raw),
        "project_id": pid,
        "permissions": merge_permissions(permissions),
        "spend_ceiling_usd_day": _optional_float(spend_ceiling_usd_day),
        "require_approval_over_usd": _optional_float(require_approval_over_usd),
        "seats_mode": "chat_only" if seats_mode == "chat_only" else "inherit",
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "max_uses": uses,
        "uses": 0,
        "status": "active",
        "created_at": now.isoformat(),
    }
    data["invites"].append(row)
    _save(data)
    public = public_invite(row)
    public["token"] = raw
    return public


def peek_invite(token: str) -> dict:
    row = _find_invite(token)
    if row is None:
        raise ValueError("invite not found")
    from .org import ensure_org

    org = ensure_org()
    pid = str(row.get("project_id") or "")
    project = next((item for item in org.get("projects") or [] if item.get("id") == pid), None)
    operator = public_operator()
    return {
        "ok": True,
        "project_id": pid,
        "project_name": str((project or {}).get("name") or pid),
        "operator_name": operator.get("operator_name") or "Owner",
        "permissions": merge_permissions(row.get("permissions")),
        "expires_at": str(row.get("expires_at") or ""),
        "status": str(row.get("status") or "active"),
    }


def _find_invite(token: str) -> dict | None:
    hashed = _hash_token(str(token or "").strip())
    if not hashed or hashed == _hash_token(""):
        return None
    data = _load()
    for row in data.get("invites") or []:
        if not isinstance(row, dict):
            continue
        stored = str(row.get("token_hash") or "")
        if stored and secrets.compare_digest(stored, hashed):
            return row
    return None


def _invite_live(row: dict) -> str | None:
    if str(row.get("status") or "active") != "active":
        return "invite is no longer active"
    expires = _parse_when(str(row.get("expires_at") or ""))
    if expires and expires < _utc_now():
        return "invite expired"
    if int(row.get("uses") or 0) >= int(row.get("max_uses") or 1):
        return "invite already used"
    return None


def _optional_float(value):
    if value in (None, "", False):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError("amount must be a number") from err
    if number < 0:
        raise ValueError("amount must be >= 0")
    return number


def redeem_invite(token: str, display_name: str, secret: str) -> dict:
    raw = str(token or "").strip()
    name = str(display_name or "").strip()
    pin = str(secret or "")
    if not name:
        raise ValueError("display name required")
    if len(name) > 80:
        raise ValueError("display name too long")
    if len(pin) < SECRET_MIN:
        raise ValueError(f"unlock secret must be at least {SECRET_MIN} characters")
    with _LOCK:
        data = _load()
        hashed = _hash_token(raw)
        found = None
        for row in data.get("invites") or []:
            if not isinstance(row, dict):
                continue
            stored = str(row.get("token_hash") or "")
            if stored and secrets.compare_digest(stored, hashed):
                found = row
                break
        if found is None:
            raise ValueError("invite not found")
        err = _invite_live(found)
        if err:
            raise ValueError(err)
        pid = str(found.get("project_id") or "")
        live = [row for row in _active_members(data, pid) if str(row.get("status") or "") == "active"]
        if len(live) >= MAX_MEMBERS:
            raise ValueError(f"this CEO already has {MAX_MEMBERS} collaborators")
        salt, digest = hash_pin(pin)
        now = _utc_now().isoformat()
        member = {
            "id": secrets.token_hex(6),
            "project_id": pid,
            "display_name": name,
            "role": "collaborator",
            "permissions": merge_permissions(found.get("permissions")),
            "spend_ceiling_usd_day": found.get("spend_ceiling_usd_day"),
            "require_approval_over_usd": found.get("require_approval_over_usd"),
            "seats_mode": found.get("seats_mode") or "inherit",
            "secret_salt": salt,
            "secret_hash": digest,
            "status": "active",
            "created_at": now,
            "last_active_at": now,
        }
        data["members"].append(member)
        found["uses"] = int(found.get("uses") or 0) + 1
        if found["uses"] >= int(found.get("max_uses") or 1):
            found["status"] = "used"
        _save(data)
    session = mint_member_session(member)
    return {"member": public_member(member), "token": session, "owner_name": public_operator().get("operator_name") or "Owner"}


def get_member(member_id: str) -> dict | None:
    wanted = str(member_id or "").strip()
    if not wanted:
        return None
    for row in _load().get("members") or []:
        if isinstance(row, dict) and str(row.get("id") or "") == wanted:
            return row
    return None


def verify_member_secret(member_id: str, secret: str) -> dict:
    row = get_member(member_id)
    if row is None or str(row.get("status") or "") != "active":
        raise ValueError("membership not found")
    salt = str(row.get("secret_salt") or "")
    hashed = str(row.get("secret_hash") or "")
    if not salt or not hashed:
        raise ValueError("membership has no unlock secret")
    try:
        _, check = hash_pin(str(secret or ""), salt)
    except (ValueError, TypeError) as err:
        raise ValueError("wrong secret") from err
    if not secrets.compare_digest(check, hashed):
        raise ValueError("wrong secret")
    return row


def member_session_token(row: dict) -> str:
    digest = str(row.get("secret_hash") or "")
    member_id = str(row.get("id") or "")
    return hmac.new(digest.encode("utf-8"), f"openbot-share-v1:{member_id}".encode("utf-8"), hashlib.sha256).hexdigest()


def mint_member_session(row: dict) -> str:
    token = member_session_token(row)
    with _LOCK:
        _SESSION_MEMBERS[token] = str(row.get("id") or "")
    return token


def member_from_session(token: str) -> dict | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    member_id = ""
    with _LOCK:
        member_id = _SESSION_MEMBERS.get(raw) or ""
    row = get_member(member_id) if member_id else None
    if row is not None:
        expected = member_session_token(row)
        if not expected or not secrets.compare_digest(expected, raw):
            row = None
    if row is None:
        for item in _load().get("members") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "") != "active":
                continue
            expected = member_session_token(item)
            if expected and secrets.compare_digest(expected, raw):
                row = item
                break
    if row is None or str(row.get("status") or "") != "active":
        return None
    return row


def unlock_member(member_id: str, secret: str) -> dict:
    row = verify_member_secret(member_id, secret)
    touch_member(str(row.get("id") or ""))
    session = mint_member_session(row)
    return {
        "member": public_member(row),
        "token": session,
        "owner_name": public_operator().get("operator_name") or "Owner",
    }


def set_member_secret(member_id: str, secret: str) -> dict:
    pin = str(secret or "")
    if len(pin) < SECRET_MIN:
        raise ValueError(f"unlock secret must be at least {SECRET_MIN} characters")
    with _LOCK:
        data = _load()
        found = None
        for row in data.get("members") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == str(member_id or ""):
                found = row
                break
        if found is None or str(found.get("status") or "") == "removed":
            raise ValueError("membership not found")
        salt, digest = hash_pin(pin)
        found["secret_salt"] = salt
        found["secret_hash"] = digest
        _save(data)
    return public_member(found)


def patch_member(member_id: str, patch: dict) -> dict:
    with _LOCK:
        data = _load()
        found = None
        for row in data.get("members") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == str(member_id or ""):
                found = row
                break
        if found is None:
            raise ValueError("membership not found")
        if "display_name" in patch and patch.get("display_name") is not None:
            name = str(patch.get("display_name") or "").strip()
            if not name:
                raise ValueError("display name required")
            found["display_name"] = name[:80]
        if "permissions" in patch:
            found["permissions"] = merge_permissions(patch.get("permissions"))
        if "status" in patch and patch.get("status") in {"active", "paused", "removed"}:
            found["status"] = patch.get("status")
        if "spend_ceiling_usd_day" in patch:
            found["spend_ceiling_usd_day"] = _optional_float(patch.get("spend_ceiling_usd_day"))
        if "require_approval_over_usd" in patch:
            found["require_approval_over_usd"] = _optional_float(patch.get("require_approval_over_usd"))
        if "seats_mode" in patch:
            mode = str(patch.get("seats_mode") or "inherit")
            found["seats_mode"] = "chat_only" if mode == "chat_only" else "inherit"
        _save(data)
    return public_member(found)


def pause_member(member_id: str, paused: bool = True) -> dict:
    return patch_member(member_id, {"status": "paused" if paused else "active"})


def remove_member(member_id: str) -> dict:
    return patch_member(member_id, {"status": "removed"})


def revoke_invite(invite_id: str) -> dict:
    wanted = str(invite_id or "").strip()
    with _LOCK:
        data = _load()
        found = None
        for row in data.get("invites") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == wanted:
                found = row
                break
        if found is None:
            raise ValueError("invite not found")
        found["status"] = "revoked"
        _save(data)
    return public_invite(found)


def touch_member(member_id: str) -> None:
    wanted = str(member_id or "").strip()
    if not wanted:
        return
    with _LOCK:
        data = _load()
        for row in data.get("members") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == wanted:
                row["last_active_at"] = _utc_now().isoformat()
                _save(data)
                return


def member_can(row: dict | None, permission: str) -> bool:
    if not row or str(row.get("status") or "") != "active":
        return False
    perms = merge_permissions(row.get("permissions"))
    return bool(perms.get(permission))


def member_project_id(row: dict | None) -> str:
    return str((row or {}).get("project_id") or "").strip()


def allows_project(row: dict | None, project_id: str | None) -> bool:
    allowed = member_project_id(row)
    wanted = str(project_id or "").strip()
    return bool(allowed) and allowed == wanted


def actor_stamp(row: dict | None) -> dict:
    if not row:
        return {"kind": "owner", "id": "owner", "label": "Owner"}
    return {
        "kind": "collaborator",
        "id": str(row.get("id") or ""),
        "label": str(row.get("display_name") or "Collaborator"),
        "project_id": member_project_id(row),
    }


def member_spend_today(member_id: str, project_id: str | None = None) -> float:
    wanted = str(member_id or "").strip()
    pid = str(project_id or "").strip()
    today = _utc_now().date().isoformat()
    total = 0.0
    for job in list_jobs():
        actor = job.get("actor") if isinstance(job.get("actor"), dict) else {}
        if str(actor.get("id") or "") != wanted:
            continue
        if pid and str(job.get("project_id") or "") != pid:
            continue
        at = str(job.get("at") or "")[:10]
        if at != today:
            continue
        try:
            total += float(job.get("usd_estimate") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 6)


def check_job_run(row: dict, project_id: str | None, preset: str | None) -> str | None:
    if not member_can(row, "jobs_run") and not member_can(row, "chat_write"):
        return "this share cannot send chat or jobs"
    if not allows_project(row, project_id):
        return "this share is for a different CEO"
    if not project_id:
        return "collaborators cannot use Chief of Staff"
    chosen = str(preset or "cos")
    seats_mode = str(row.get("seats_mode") or "inherit")
    if seats_mode == "chat_only" and chosen in WORK_PRESETS:
        return "this share is limited to chat"
    if chosen in WORK_PRESETS and not member_can(row, "jobs_run"):
        return "this share cannot trigger jobs"
    ceiling = row.get("spend_ceiling_usd_day")
    if ceiling is not None:
        used = member_spend_today(str(row.get("id") or ""), project_id)
        if used >= float(ceiling):
            return "collaborator daily spend ceiling reached"
    threshold = row.get("require_approval_over_usd")
    if threshold is not None and chosen in WORK_PRESETS:
        used = member_spend_today(str(row.get("id") or ""), project_id)
        if float(threshold) <= 0 or used >= float(threshold):
            return "owner approval required for paid jobs on this share"
    return None


def filter_jobs(jobs: list, project_id: str) -> list:
    pid = str(project_id or "").strip()
    return [job for job in jobs if str(job.get("project_id") or "") == pid]


def filter_needs(rows: list, project_id: str) -> list:
    pid = str(project_id or "").strip()
    return [row for row in rows if str(row.get("project_id") or "") == pid]


def filter_org(org: dict, project_id: str) -> dict:
    pid = str(project_id or "").strip()
    projects = [row for row in (org.get("projects") or []) if str(row.get("id") or "") == pid]
    out = dict(org)
    out["projects"] = projects
    out["index"] = (projects[0].get("index") if projects else "") or ""
    out["index_now"] = (projects[0].get("index_now") if projects else "") or ""
    out["staff"] = ""
    out["role"] = "shared"
    out["title"] = "Shared CEO"
    return out


def owner_only_path(path: str) -> bool:
    raw = str(path or "")
    return any(raw == prefix or raw.startswith(prefix) for prefix in OWNER_ONLY_PREFIXES)


def keys_connected_flag(has_key: bool) -> dict:
    return {"connected": bool(has_key)}
