"""Wallets and spend policy. OpenBot is not the billing system of record."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from .store import in_spend_period, list_jobs, parse_job_time, spend_bucket

PAID_PRESETS = {"think", "builder", "research", "ops"}
DEFAULT_POLICY = {
    "bind": "payg",
    "mode": "hard",
    "allow_zen_fallback": True,
}
_GO_CACHE: dict = {"at": 0.0, "data": None}
_GO_TTL = 60.0


def normalize_policy(raw) -> dict:
    data = dict(DEFAULT_POLICY)
    if isinstance(raw, dict):
        bind = str(raw.get("bind") or "").strip().lower()
        if bind in {"payg", "all"}:
            data["bind"] = bind
        mode = str(raw.get("mode") or "").strip().lower()
        if mode in {"warn", "hard"}:
            data["mode"] = mode
        if "allow_zen_fallback" in raw:
            data["allow_zen_fallback"] = bool(raw["allow_zen_fallback"])
    return data


def parse_go_usage(raw) -> dict:
    """Go quota is percent-used windows. Zen card balance is not on this API."""
    empty = {
        "present": False,
        "exhausted": False,
        "window": None,
        "percent_used": None,
        "remaining_percent": None,
        "resets_at": None,
        "status": None,
        "note": "No OpenCode Go subscription on this key.",
    }
    if not isinstance(raw, dict):
        return empty
    payload = raw.get("usage") if isinstance(raw.get("usage"), dict) else raw
    if "rolling" not in payload and "weekly" not in payload and "monthly" not in payload:
        nested = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        if nested:
            payload = nested
    http_status = raw.get("http_status")
    if http_status and http_status != 200:
        empty["status"] = http_status
        if http_status in {401, 403}:
            empty["note"] = "No OpenCode Go plan on this key (Zen PAYG can still run)."
        else:
            empty["note"] = f"Go usage HTTP {http_status}"
        return empty
    windows = {}
    for name in ("rolling", "weekly", "monthly"):
        row = payload.get(name)
        if isinstance(row, dict) and isinstance(row.get("percent"), (int, float)):
            windows[name] = row
    if not windows:
        return empty
    return {
        "present": True,
        "exhausted": False,
        "window": None,
        "percent_used": None,
        "remaining_percent": None,
        "resets_at": None,
        "status": "ok",
        "windows": windows,
        "note": "Included OpenCode Go quota. Percent used, not dollars.",
    }


def _go_for_period(go: dict, period: str) -> dict:
    parsed = parse_go_usage(go) if go and not go.get("windows") else dict(go or {})
    if not parsed.get("present"):
        return parsed
    windows = parsed.get("windows") or {}
    key = {"day": "rolling", "week": "weekly", "month": "monthly"}.get(period, "weekly")
    row = windows.get(key) or windows.get("weekly") or windows.get("monthly") or windows.get("rolling")
    if not isinstance(row, dict):
        return parsed
    percent = float(row.get("percent") or 0)
    status = str(row.get("status") or "")
    exhausted = percent >= 100 or status.lower() in {"rate_limited", "blocked", "exhausted"}
    parsed.update(
        {
            "window": key,
            "percent_used": round(percent, 2),
            "remaining_percent": round(max(0.0, 100.0 - percent), 2),
            "resets_at": row.get("resetsAt") or row.get("resets_at"),
            "status": status or "ok",
            "exhausted": exhausted,
        }
    )
    if exhausted:
        parsed["note"] = "OpenCode Go quota is used up for this window."
    return parsed


def _go_snapshot() -> dict | None:
    now = time.time()
    if _GO_CACHE["data"] is not None and now - float(_GO_CACHE["at"] or 0) < _GO_TTL:
        return _GO_CACHE["data"]
    try:
        from .providers import zen_usage

        data = zen_usage()
    except Exception:
        data = None
    _GO_CACHE["at"] = now
    _GO_CACHE["data"] = data
    return data


def classify_job(job: dict, go: dict, policy: dict) -> str:
    engine = str(job.get("engine") or "").lower()
    try:
        amount = float(job.get("usd_estimate") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if "opencode" in engine:
        if go.get("present") and not go.get("exhausted"):
            return "included"
        if go.get("present") and go.get("exhausted") and not policy.get("allow_zen_fallback"):
            return "blocked"
        return "payg" if amount > 0 else "unknown"
    if "hermes" in engine:
        return "payg" if amount > 0 else "unknown"
    return "included"


def snapshot(
    cap_usd: float,
    period: str,
    now: datetime | None = None,
    project_id: str | None = None,
    policy=None,
    go_usage=None,
) -> dict:
    policy = normalize_policy(policy)
    go = _go_for_period(go_usage if go_usage is not None else (_go_snapshot() or {}), period)
    current = now or datetime.now(timezone.utc)
    by_engine = {"chat": 0.0, "opencode": 0.0, "hermes": 0.0}
    payg = 0.0
    included = 0.0
    known = 0.0
    unknown_jobs = 0
    for job in list_jobs():
        if job.get("rejected"):
            continue
        if project_id and job.get("project_id") != project_id:
            continue
        if not in_spend_period(str(job.get("at") or ""), period, current):
            continue
        try:
            amount = float(job.get("usd_estimate") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        wallet = classify_job(job, go, policy)
        by_engine[spend_bucket(job)] = round(by_engine[spend_bucket(job)] + amount, 6)
        if wallet == "unknown":
            unknown_jobs += 1
            continue
        known += amount
        if wallet == "payg":
            payg += amount
        elif wallet == "included":
            included += amount
    payg = round(payg, 6)
    included = round(included, 6)
    known = round(known, 6)
    bound = payg if policy["bind"] == "payg" else known
    remaining = round(max(0.0, float(cap_usd) - bound), 6)
    go_blocked = bool(
        go.get("present") and go.get("exhausted") and not policy["allow_zen_fallback"]
    )
    at_cap = remaining <= 0
    enforced = policy["mode"] == "hard" and (at_cap or go_blocked)
    wallets = [
        {
            "id": "go",
            "label": "OpenCode Go",
            "kind": "quota",
            "present": bool(go.get("present")),
            "unit": "%",
            "used": go.get("percent_used"),
            "remaining": go.get("remaining_percent"),
            "resets_at": go.get("resets_at"),
            "note": go.get("note"),
        },
        {
            "id": "payg",
            "label": "PAYG (Zen, OpenRouter, keys)",
            "kind": "payg",
            "present": True,
            "unit": "usd",
            "used": payg,
            "remaining": remaining if policy["bind"] == "payg" else None,
            "note": "Card spend from job receipts. Zen wallet balance is not on the public API.",
        },
        {
            "id": "included",
            "label": "Included",
            "kind": "included",
            "present": True,
            "unit": "usd",
            "used": included,
            "remaining": None,
            "note": "INDEX/chat and OpenCode while Go quota still has room.",
        },
    ]
    return {
        "spend_cap_usd": float(cap_usd),
        "spend_cap_period": period,
        "spent_usd": round(bound, 6),
        "spent_payg_usd": payg,
        "spent_included_usd": included,
        "spent_all_usd": known,
        "cap_remaining": remaining,
        "enforced": enforced,
        "at_cap": at_cap,
        "unknown_jobs": unknown_jobs,
        "project_id": project_id,
        "by_engine": by_engine,
        "policy": policy,
        "go": go,
        "wallets": wallets,
    }


def gate(preset: str, summary: dict) -> dict:
    if preset not in PAID_PRESETS:
        return {"allow": True, "reason": None}
    policy = normalize_policy((summary or {}).get("policy"))
    go = (summary or {}).get("go") or {}
    if (
        preset == "builder"
        and go.get("present")
        and go.get("exhausted")
        and not policy["allow_zen_fallback"]
    ):
        return {
            "allow": False,
            "reason": "OpenCode Go quota is used up. Turn on Zen fallback in Usage, or wait for reset.",
        }
    if policy["mode"] != "hard":
        return {"allow": True, "reason": None}
    if float((summary or {}).get("cap_remaining") or 0) <= 0:
        bind = "PAYG" if policy["bind"] == "payg" else "spend"
        return {
            "allow": False,
            "reason": (
                f"{bind} cap reached. Chief of Staff can still read the brief. "
                "Raise the cap in Usage or wait for the period to reset."
            ),
        }
    return {"allow": True, "reason": None}


def gate_paid_job(preset: str, project_id: str | None, tools: dict | None) -> tuple[bool, str | None, dict]:
    from .config import load_config, load_settings

    cfg = load_config()
    cap = (tools or {}).get("spend_cap_usd")
    if cap is None:
        cap = cfg["spend_cap_usd"]
    summary = snapshot(
        float(cap),
        cfg["spend_cap_period"],
        project_id=project_id,
        policy=load_settings().get("spend_policy"),
        go_usage=_go_snapshot(),
    )
    decision = gate(preset, summary)
    return bool(decision["allow"]), decision.get("reason"), summary


def per_ceo_breakdown(
    cap_usd: float,
    period: str,
    now: datetime | None = None,
    policy=None,
    go_usage=None,
) -> dict:
    """
    Aggregate spend by project_id (CEO) with weekly/daily breakdown.
    Returns per-CEO totals, alert status, and trend data.
    """
    from .org import list_projects

    policy = normalize_policy(policy)
    go = _go_for_period(go_usage if go_usage is not None else (_go_snapshot() or {}), period)
    current = now or datetime.now(timezone.utc)
    
    projects = list_projects()
    ceo_data = {}
    
    # Initialize CEO entries
    for proj in projects:
        pid = proj.get("id")
        if not pid:
            continue
        ceo_data[pid] = {
            "id": pid,
            "name": proj.get("name") or pid,
            "total_usd": 0.0,
            "weekly_usd": 0.0,
            "monthly_usd": 0.0,
            "daily_breakdown": {},  # date -> usd
            "alert_50_percent": False,
            "at_cap": False,
            "cap_usd": cap_usd,
        }
    
    # Aggregate jobs
    for job in list_jobs():
        if job.get("rejected"):
            continue
        pid = job.get("project_id")
        if not pid or pid not in ceo_data:
            continue
        
        try:
            amount = float(job.get("usd_estimate") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        
        wallet = classify_job(job, go, policy)
        if wallet == "unknown":
            continue
        
        # Apply policy binding
        if policy["bind"] == "payg" and wallet != "payg":
            continue
        
        job_time = str(job.get("at") or "")
        job_dt = parse_job_time(job_time)
        if not job_dt:
            continue
        
        # Total
        ceo_data[pid]["total_usd"] += amount
        
        # Period-specific
        if in_spend_period(job_time, "week", current):
            ceo_data[pid]["weekly_usd"] += amount
        if in_spend_period(job_time, "month", current):
            ceo_data[pid]["monthly_usd"] += amount
        
        # Daily breakdown for trends (last 14 days)
        date_key = job_dt.date().isoformat()
        ceo_data[pid]["daily_breakdown"][date_key] = (
            ceo_data[pid]["daily_breakdown"].get(date_key, 0.0) + amount
        )
    
    # Round and detect alerts
    for pid, data in ceo_data.items():
        data["total_usd"] = round(data["total_usd"], 6)
        data["weekly_usd"] = round(data["weekly_usd"], 6)
        data["monthly_usd"] = round(data["monthly_usd"], 6)
        
        # Alert at 50% of weekly cap
        if period == "week" and data["weekly_usd"] >= cap_usd * 0.5:
            data["alert_50_percent"] = True
        
        # Cap exceeded
        if data["weekly_usd"] >= cap_usd:
            data["at_cap"] = True
    
    return {
        "period": period,
        "cap_usd": float(cap_usd),
        "ceos": list(ceo_data.values()),
        "policy": policy,
        "go": go,
    }


def weekly_trend(
    project_id: str | None = None,
    now: datetime | None = None,
    policy=None,
    go_usage=None,
) -> dict:
    """
    Return daily spend breakdown for the last 14 days.
    """
    from datetime import timedelta

    policy = normalize_policy(policy)
    go = _go_for_period(go_usage if go_usage is not None else (_go_snapshot() or {}), "week")
    current = now or datetime.now(timezone.utc)
    
    # Generate date range (last 14 days)
    dates = []
    for i in range(13, -1, -1):
        date = (current - timedelta(days=i)).date()
        dates.append(date.isoformat())
    
    daily_totals = {d: 0.0 for d in dates}
    
    # Aggregate jobs by day
    for job in list_jobs():
        if job.get("rejected"):
            continue
        if project_id and job.get("project_id") != project_id:
            continue
        
        try:
            amount = float(job.get("usd_estimate") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        
        wallet = classify_job(job, go, policy)
        if wallet == "unknown":
            continue
        
        if policy["bind"] == "payg" and wallet != "payg":
            continue
        
        job_time = str(job.get("at") or "")
        job_dt = parse_job_time(job_time)
        if not job_dt:
            continue
        
        date_key = job_dt.date().isoformat()
        if date_key in daily_totals:
            daily_totals[date_key] += amount
    
    # Format response
    series = [{"date": d, "usd": round(daily_totals[d], 6)} for d in dates]
    
    return {
        "project_id": project_id,
        "days": 14,
        "series": series,
        "policy": policy,
    }


def check_cap_alerts(
    cap_usd: float,
    period: str,
    now: datetime | None = None,
    policy=None,
    go_usage=None,
) -> dict:
    """
    Check for cap-related alerts: 50% threshold, cap exceeded.
    Returns list of alerts per CEO.
    """
    breakdown = per_ceo_breakdown(cap_usd, period, now, policy, go_usage)
    current = now or datetime.now(timezone.utc)
    
    alerts = []
    for ceo in breakdown["ceos"]:
        if ceo["alert_50_percent"] and not ceo["at_cap"]:
            alerts.append({
                "ceo_id": ceo["id"],
                "ceo_name": ceo["name"],
                "kind": "warning",
                "level": "50_percent",
                "message": f"{ceo['name']} at {round(ceo['weekly_usd'] / cap_usd * 100)}% of weekly cap (${ceo['weekly_usd']:.2f} / ${cap_usd:.2f})",
                "weekly_usd": ceo["weekly_usd"],
                "cap_usd": cap_usd,
                "percent": round(ceo["weekly_usd"] / cap_usd * 100, 1),
            })
        
        if ceo["at_cap"]:
            # Calculate reset time (end of current week/month)
            if period == "week":
                days_until_reset = 7 - current.isocalendar()[2]  # ISO weekday (1=Mon, 7=Sun)
                reset_msg = f"resets in {days_until_reset} day{'s' if days_until_reset != 1 else ''}"
            elif period == "month":
                import calendar
                last_day = calendar.monthrange(current.year, current.month)[1]
                days_until_reset = last_day - current.day
                reset_msg = f"resets in {days_until_reset} day{'s' if days_until_reset != 1 else ''}"
            else:
                reset_msg = "resets tomorrow"
            
            alerts.append({
                "ceo_id": ceo["id"],
                "ceo_name": ceo["name"],
                "kind": "error",
                "level": "cap_exceeded",
                "message": f"{ceo['name']} hit ${cap_usd:.2f} cap, {reset_msg}",
                "weekly_usd": ceo["weekly_usd"],
                "cap_usd": cap_usd,
                "reset_message": reset_msg,
            })
    
    return {
        "period": period,
        "cap_usd": cap_usd,
        "alerts": alerts,
        "has_alerts": len(alerts) > 0,
    }
