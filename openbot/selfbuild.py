"""Self-build loop: OpenBot dogfoods itself by implementing ROADMAP items."""

from __future__ import annotations

from pathlib import Path

from .config import load_settings
from .roadmap import next_roadmap_item
from .routine_templates import get_template_by_id
from .routines import (
    attach_routine_cron,
    create_routine,
    delete_routine,
    list_routines,
    read_routine,
    routine_dir,
    update_routine,
)


SELF_BUILD_ROUTINE_ID = "routine-selfbuild"


def self_build_enabled() -> bool:
    """Check if self-build loop is enabled in settings."""
    settings = load_settings()
    return bool(settings.get("enable_self_build", False))


def self_build_routine_exists(project_id: str | None = None) -> bool:
    """Check if self-build routine exists for a project or staff."""
    routine = read_routine(SELF_BUILD_ROUTINE_ID, project_id)
    return routine is not None


def ensure_self_build_routine(project_id: str | None = None) -> dict:
    """Create or update self-build routine based on settings.
    
    Returns:
        dict with ok, action (created/updated/deleted/skipped), routine_id
    """
    enabled = self_build_enabled()
    exists = self_build_routine_exists(project_id)
    
    if enabled and not exists:
        # Create the routine from template
        template = get_template_by_id("self-build")
        if not template:
            return {"ok": False, "error": "self-build template not found"}
        
        routine_id = create_routine(
            name=template["name"],
            schedule=template["schedule"],
            steps=template["steps"],
            project_id=project_id,
            enabled=True,
        )
        
        # Attach to Hermes cron
        cron_result = attach_routine_cron(routine_id, project_id)
        
        return {
            "ok": True,
            "action": "created",
            "routine_id": routine_id,
            "cron": cron_result.get("ok", False),
        }
    
    elif enabled and exists:
        # Update if needed (ensure it's enabled)
        routine = read_routine(SELF_BUILD_ROUTINE_ID, project_id)
        if routine and not routine.get("enabled", True):
            update_routine(SELF_BUILD_ROUTINE_ID, project_id, enabled=True)
            return {
                "ok": True,
                "action": "enabled",
                "routine_id": SELF_BUILD_ROUTINE_ID,
            }
        return {
            "ok": True,
            "action": "exists",
            "routine_id": SELF_BUILD_ROUTINE_ID,
        }
    
    elif not enabled and exists:
        # Disable the routine (don't delete, just disable)
        update_routine(SELF_BUILD_ROUTINE_ID, project_id, enabled=False)
        return {
            "ok": True,
            "action": "disabled",
            "routine_id": SELF_BUILD_ROUTINE_ID,
        }
    
    else:
        # Not enabled, doesn't exist - nothing to do
        return {
            "ok": True,
            "action": "skipped",
            "routine_id": None,
        }


def self_build_status(project_id: str | None = None) -> dict:
    """Get status of self-build loop for a project or staff.
    
    Returns:
        dict with enabled, routine_exists, next_item (ROADMAP item or None)
    """
    enabled = self_build_enabled()
    exists = self_build_routine_exists(project_id)
    next_item = next_roadmap_item()
    
    routine = read_routine(SELF_BUILD_ROUTINE_ID, project_id) if exists else None
    
    return {
        "enabled": enabled,
        "routine_exists": exists,
        "routine_enabled": routine.get("enabled", False) if routine else False,
        "next_item": {
            "id": next_item["id"],
            "name": next_item["name"],
        } if next_item else None,
    }
