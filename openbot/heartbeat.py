"""Weekday CEO Think heartbeat. Hermes is WHEN. Board packets are HOW."""

from __future__ import annotations

import threading

from .decide import HEARTBEAT_MARK, heartbeat_step_instruction
from .routines import (
    create_routine,
    read_routine,
    update_routine,
)

HEARTBEAT_ROUTINE_ID = "routine-heartbeat"
HEARTBEAT_SCHEDULE = "0 9 * * 1-5"
HEARTBEAT_NAME = "CEO weekday Think"


def heartbeat_enabled(project_id: str | None) -> bool:
    if not project_id:
        return False
    routine = read_routine(HEARTBEAT_ROUTINE_ID, project_id)
    return bool(routine and routine.get("enabled"))


def ensure_heartbeat_routine(project_id: str, *, enabled: bool = False) -> dict:
    """Seed the routine file. Do not attach Hermes cron unless attach_heartbeat runs."""
    if not project_id:
        return {"ok": False, "error": "no CEO"}
    steps = [{"seat": "think", "instruction": heartbeat_step_instruction()}]
    existing = read_routine(HEARTBEAT_ROUTINE_ID, project_id)
    if existing:
        update_routine(
            HEARTBEAT_ROUTINE_ID,
            project_id,
            name=HEARTBEAT_NAME,
            schedule=HEARTBEAT_SCHEDULE,
            steps=steps,
            enabled=bool(enabled if enabled else existing.get("enabled")),
        )
        return {"ok": True, "action": "updated", "routine_id": HEARTBEAT_ROUTINE_ID, "enabled": heartbeat_enabled(project_id)}
    create_routine(
        HEARTBEAT_NAME,
        HEARTBEAT_SCHEDULE,
        steps,
        project_id,
        enabled=enabled,
        routine_id=HEARTBEAT_ROUTINE_ID,
    )
    return {"ok": True, "action": "created", "routine_id": HEARTBEAT_ROUTINE_ID, "enabled": bool(enabled)}


def attach_heartbeat(project_id: str) -> dict:
    """Operator Accept: enable weekday Think and attach Hermes cron. Never silent."""
    seeded = ensure_heartbeat_routine(project_id, enabled=True)
    if not seeded.get("ok"):
        return seeded
    update_routine(HEARTBEAT_ROUTINE_ID, project_id, enabled=True)
    try:
        from .decide import recommended_auto_policy
        from .org import patch_project_tools, project_tools

        tools = project_tools(project_id) or {}
        if not tools.get("auto_policy_set"):
            policy = recommended_auto_policy()
            patch_project_tools(
                project_id,
                {"auto_policy": policy, "auto_labor": True, "heartbeat_offer": "on"},
            )
    except Exception:
        pass
    from .hermes import cron_create
    from .org import project_tools
    from .routines import routine_cron_name

    tools = project_tools(project_id) if project_id else {}
    hermes_home = str((tools or {}).get("hermes_home") or "").strip() or None
    cron = cron_create(
        HEARTBEAT_SCHEDULE,
        (
            "HEARTBEAT_TICK. Timer only. Reply HEARTBEAT_TICK and stop. "
            "Do not plan, browse, or edit. The OttoBot board will run Think with PULSE."
        ),
        routine_cron_name(HEARTBEAT_ROUTINE_ID, project_id),
        cwd=None,
        home=hermes_home,
    )
    return {
        "ok": bool(cron.get("ok")),
        "action": "attached",
        "routine_id": HEARTBEAT_ROUTINE_ID,
        "cron": cron,
        "engine": "Hermes Agent",
        "note": "Hermes is the weekday timer. Board Think writes Why. Auto vs notify follows this CEO's per-lane policy.",
    }


def run_heartbeat_now(project_id: str) -> dict:
    """Operator prove: one Think now. Does not attach weekday cron."""
    if not project_id:
        return {"ok": False, "error": "no CEO"}
    ensure_heartbeat_routine(project_id, enabled=False)

    def _run() -> None:
        from .router import handle

        try:
            handle(
                heartbeat_step_instruction(),
                folder=None,
                preset="think",
                project_id=project_id,
                worker_id=None,
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return {
        "ok": True,
        "action": "run_now",
        "project_id": project_id,
        "engine": "Hermes Agent",
        "preset": "think",
        "heartbeat": True,
        "cron_attached": heartbeat_enabled(project_id),
        "message": HEARTBEAT_MARK,
        "note": "One Think now. Weekday cron stays off until you Attach.",
    }


def detach_heartbeat(project_id: str) -> dict:
    if not project_id:
        return {"ok": False, "error": "no CEO"}
    if not read_routine(HEARTBEAT_ROUTINE_ID, project_id):
        return {"ok": True, "action": "missing"}
    update_routine(HEARTBEAT_ROUTINE_ID, project_id, enabled=False)
    return {"ok": True, "action": "disabled", "routine_id": HEARTBEAT_ROUTINE_ID}


def fire_heartbeat(project_id: str) -> dict:
    """Run the Think step through the board (packet + PULSE). Hermes already ticked WHEN."""
    if not project_id:
        return {"ok": False, "error": "no CEO"}
    if not heartbeat_enabled(project_id):
        return {"ok": False, "error": "heartbeat not attached"}

    def _run() -> None:
        from .routines import execute_routine

        try:
            execute_routine(HEARTBEAT_ROUTINE_ID, project_id)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return {
        "ok": True,
        "action": "started",
        "routine_id": HEARTBEAT_ROUTINE_ID,
        "project_id": project_id,
        "engine": "Hermes Agent",
        "preset": "think",
        "heartbeat": True,
        "message": HEARTBEAT_MARK,
    }


def cron_is_heartbeat(name: str) -> bool:
    raw = str(name or "").lower()
    return "routine-heartbeat" in raw
