"""Routines: multi-step scheduled flows. Files-first. No second scheduler."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .store import ROOT, now_iso

ORG = ROOT / "org"


def routine_dir(project_id: str | None) -> Path:
    """Return routines folder for a CEO or staff."""
    if project_id:
        slug = re.sub(r"[^a-z0-9]+", "-", project_id.lower()).strip("-")[:40] or "staff"
        return ORG / "projects" / slug / "bus" / "routines"
    return ORG / "bus" / "routines"


def ensure_routine_dir(project_id: str | None) -> Path:
    """Create routines folder if missing."""
    path = routine_dir(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def routine_path(routine_id: str, project_id: str | None) -> Path:
    """Return path to a specific routine file."""
    return routine_dir(project_id) / f"{routine_id}.md"


def list_routines(project_id: str | None = None, include_hermes: bool = True) -> dict:
    """
    List all routines for a CEO or staff, optionally including Hermes crons.
    
    Args:
        project_id: CEO scope (None for staff)
        include_hermes: If True, also fetch Hermes crons from the CEO's home
    
    Returns:
        {
            "routines": [list of OpenBot routine metadata],
            "hermes_crons": [list of Hermes cron metadata],
            "openbot_count": int,
            "hermes_count": int,
            "total": int
        }
    """
    folder = routine_dir(project_id)
    routines = []
    
    if folder.exists():
        for path in folder.glob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
                meta = parse_routine(content)
                meta["id"] = path.stem
                meta["project_id"] = project_id
                meta["source"] = "openbot"
                routines.append(meta)
            except Exception:
                continue
    
    routines = sorted(routines, key=lambda r: r.get("name", ""))
    
    hermes_crons = []
    if include_hermes:
        try:
            from .hermes import cron_list
            from .org import project_tools
            
            tools = project_tools(project_id) if project_id else {}
            hermes_home = str(tools.get("hermes_home") or "").strip() or None
            
            cron_data = cron_list(hermes_home, timeout=8)
            if cron_data.get("ok"):
                for cron in cron_data.get("crons", []):
                    hermes_crons.append({
                        "id": cron.get("id", ""),
                        "name": cron.get("name", ""),
                        "schedule": cron.get("schedule", ""),
                        "enabled": cron.get("enabled", False),
                        "source": "hermes",
                        "project_id": project_id,
                        "raw": cron.get("raw", "")
                    })
        except Exception:
            # Silently skip Hermes crons if fetch fails (gateway may not be running)
            pass
    
    return {
        "routines": routines,
        "hermes_crons": hermes_crons,
        "openbot_count": len(routines),
        "hermes_count": len(hermes_crons),
        "total": len(routines) + len(hermes_crons)
    }


def parse_routine(text: str) -> dict:
    """Parse routine markdown into structured data.
    
    Format:
    # Routine Name
    
    Schedule: every morning at 8am
    Enabled: true
    Owner: project-id or staff
    
    ## Steps
    
    1. **Builder** - Check git status
    2. **Think** - Summarize changes from last 24h
    3. **Ops** - Post summary note to INDEX
    
    ## History
    
    - 2026-09-05 10:23 - Run abc123 completed (3/3 steps)
    - 2026-09-04 10:22 - Run xyz789 failed at step 2 (Think)
    """
    lines = text.split("\n")
    name = ""
    schedule = ""
    enabled = True
    owner = None
    steps = []
    
    # Parse header
    for line in lines[:20]:
        if line.startswith("# "):
            name = line[2:].strip()
        elif line.startswith("Schedule:"):
            schedule = line.split(":", 1)[1].strip()
        elif line.startswith("Enabled:"):
            val = line.split(":", 1)[1].strip().lower()
            enabled = val in {"true", "yes", "1"}
        elif line.startswith("Owner:"):
            owner = line.split(":", 1)[1].strip() or None
    
    # Parse steps
    in_steps = False
    for line in lines:
        if line.startswith("## Steps"):
            in_steps = True
            continue
        if line.startswith("## ") and in_steps:
            break
        if in_steps and re.match(r"^\d+\.\s+\*\*", line):
            # Example: "1. **Builder** - Check git status"
            match = re.match(r"^\d+\.\s+\*\*([^*]+)\*\*\s*-\s*(.+)$", line)
            if match:
                seat_raw = match.group(1).strip().lower()
                instruction = match.group(2).strip()
                # Map "code" to "builder" for router compatibility
                seat = "builder" if seat_raw == "code" else seat_raw
                steps.append({"seat": seat, "instruction": instruction})
    
    return {
        "name": name,
        "schedule": schedule,
        "enabled": enabled,
        "owner": owner,
        "steps": steps,
    }


def format_routine(meta: dict) -> str:
    """Format routine metadata as markdown file."""
    name = meta.get("name", "Untitled Routine")
    schedule = meta.get("schedule", "")
    enabled = "true" if meta.get("enabled", True) else "false"
    owner = meta.get("owner") or "staff"
    steps = meta.get("steps") or []
    
    lines = [
        f"# {name}",
        "",
        f"Schedule: {schedule}",
        f"Enabled: {enabled}",
        f"Owner: {owner}",
        "",
        "## Steps",
        "",
    ]
    
    for idx, step in enumerate(steps, 1):
        seat_raw = step.get("seat", "builder")
        # Display "Builder" in markdown (internal preset name)
        seat = seat_raw.title()
        instruction = step.get("instruction", "")
        lines.append(f"{idx}. **{seat}** - {instruction}")
    
    lines.extend(["", "## History", "", ""])
    
    return "\n".join(lines)


def create_routine(
    name: str,
    schedule: str,
    steps: list[dict],
    project_id: str | None = None,
    enabled: bool = True,
    routine_id: str | None = None,
) -> str:
    """Create a new routine. Returns routine_id.
    
    Args:
        name: Routine name
        schedule: Schedule string (e.g., "every Monday at 10am")
        steps: List of step dicts with seat and instruction
        project_id: CEO scope (None for staff)
        enabled: Whether routine is enabled
        routine_id: Optional fixed routine ID (default: generate random UUID)
    
    Returns:
        routine_id
    """
    if routine_id is None:
        routine_id = f"routine-{uuid.uuid4().hex[:8]}"
    ensure_routine_dir(project_id)
    
    meta = {
        "name": name,
        "schedule": schedule,
        "enabled": enabled,
        "owner": project_id or "staff",
        "steps": steps,
    }
    
    path = routine_path(routine_id, project_id)
    path.write_text(format_routine(meta), encoding="utf-8")
    
    return routine_id


def read_routine(routine_id: str, project_id: str | None = None) -> dict | None:
    """Read routine by id. Returns metadata dict or None if not found."""
    path = routine_path(routine_id, project_id)
    if not path.exists():
        return None
    
    try:
        content = path.read_text(encoding="utf-8")
        meta = parse_routine(content)
        meta["id"] = routine_id
        meta["project_id"] = project_id
        return meta
    except Exception:
        return None


def update_routine(
    routine_id: str,
    project_id: str | None = None,
    **fields: Any,
) -> bool:
    """Update routine fields. Returns True on success."""
    routine = read_routine(routine_id, project_id)
    if not routine:
        return False
    
    routine.update(fields)
    path = routine_path(routine_id, project_id)
    
    try:
        path.write_text(format_routine(routine), encoding="utf-8")
        return True
    except Exception:
        return False


def delete_routine(routine_id: str, project_id: str | None = None) -> bool:
    """Delete a routine file. Returns True on success."""
    path = routine_path(routine_id, project_id)
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def add_history_entry(
    routine_id: str,
    project_id: str | None,
    run_id: str,
    status: str,
    step_count: int,
    total_steps: int,
) -> None:
    """Append a history line to the routine file."""
    path = routine_path(routine_id, project_id)
    if not path.exists():
        return
    
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        # Find History section
        history_idx = -1
        for idx, line in enumerate(lines):
            if line.startswith("## History"):
                history_idx = idx
                break
        
        if history_idx == -1:
            # Add History section
            lines.extend(["", "## History", ""])
            history_idx = len(lines) - 1
        
        # Insert new entry after ## History
        entry = f"- {now_iso()} - Run {run_id} {status} ({step_count}/{total_steps} steps)"
        lines.insert(history_idx + 2, entry)
        
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def execute_routine(
    routine_id: str,
    project_id: str | None = None,
    resume_step: int | None = None,
    resume_result: str | None = None,
) -> dict:
    """Execute a routine's steps in order.
    
    Args:
        routine_id: The routine to execute
        project_id: CEO scope (None for staff)
        resume_step: If provided, resume from this step (1-indexed)
        resume_result: If resuming, carry this RESULT forward
    
    Returns:
        dict with run_id, status, completed_steps, total_steps, results
    """
    from .router import handle
    
    routine = read_routine(routine_id, project_id)
    if not routine:
        return {
            "ok": False,
            "error": "routine not found",
            "run_id": None,
        }
    
    if not routine.get("enabled", True):
        return {
            "ok": False,
            "error": "routine disabled",
            "run_id": None,
        }
    
    steps = routine.get("steps") or []
    if not steps:
        return {
            "ok": False,
            "error": "routine has no steps",
            "run_id": None,
        }
    
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    total_steps = len(steps)
    start_step = resume_step if resume_step else 1
    carry_result = resume_result or ""
    
    results = []
    
    for idx, step in enumerate(steps, 1):
        if idx < start_step:
            # Skip steps before resume point
            continue
        
        seat = step.get("seat", "builder")
        instruction = step.get("instruction", "")
        
        # Build prompt: include prior RESULT if available
        if idx > 1 and carry_result:
            prompt = (
                f"{instruction}\n\n"
                f"PRIOR RESULT from step {idx - 1}:\n{carry_result[-1200:]}"
            )
        else:
            prompt = instruction
        
        # Execute step via router
        try:
            job = handle(
                prompt,
                folder=None,
                preset=seat,
                project_id=project_id,
                worker_id=None,
                on_delta=None,
                on_progress=None,
                run_id=None,
                quote=None,
                chain_context={
                    "step": idx,
                    "total": total_steps,
                    "routine_id": routine_id,
                    "run_id": run_id,
                },
                attachments=None,
            )
            
            result_text = job.get("text") or ""
            blocker = job.get("blocker")
            stopped = job.get("stopped", False)
            
            results.append({
                "step": idx,
                "seat": seat,
                "instruction": instruction,
                "job_id": job.get("id"),
                "ok": not blocker and not stopped,
                "blocker": blocker,
                "text": result_text[:400],  # Brief summary
            })
            
            # If step failed or stopped, halt routine
            if blocker or stopped:
                add_history_entry(
                    routine_id,
                    project_id,
                    run_id,
                    f"failed at step {idx} ({seat})",
                    idx,
                    total_steps,
                )
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "failed",
                    "completed_steps": idx - 1,
                    "total_steps": total_steps,
                    "failed_at_step": idx,
                    "blocker": blocker or "stopped",
                    "results": results,
                    "resume_step": idx,  # Where to resume from
                }
            
            # Carry RESULT forward to next step
            carry_result = result_text
        
        except Exception as e:
            results.append({
                "step": idx,
                "seat": seat,
                "instruction": instruction,
                "ok": False,
                "error": str(e)[:200],
            })
            add_history_entry(
                routine_id,
                project_id,
                run_id,
                f"error at step {idx} ({seat})",
                idx - 1,
                total_steps,
            )
            return {
                "ok": False,
                "run_id": run_id,
                "status": "error",
                "completed_steps": idx - 1,
                "total_steps": total_steps,
                "failed_at_step": idx,
                "error": str(e)[:200],
                "results": results,
                "resume_step": idx,
            }
    
    # All steps completed
    add_history_entry(
        routine_id,
        project_id,
        run_id,
        "completed",
        total_steps,
        total_steps,
    )
    
    return {
        "ok": True,
        "run_id": run_id,
        "status": "completed",
        "completed_steps": total_steps,
        "total_steps": total_steps,
        "results": results,
    }


def routine_cron_name(routine_id: str, project_id: str | None) -> str:
    """Generate Hermes cron job name for a routine."""
    scope = project_id or "staff"
    return f"openbot-routine-{scope}-{routine_id}"


def attach_routine_cron(
    routine_id: str,
    project_id: str | None = None,
) -> dict:
    """Attach or update Hermes cron for this routine.
    
    Hermes remains the scheduler. OpenBot just creates a cron job that
    calls back to execute_routine when it fires.
    """
    from .hermes import cron_create
    from .org import project_tools
    
    routine = read_routine(routine_id, project_id)
    if not routine:
        return {"ok": False, "error": "routine not found"}
    
    schedule = routine.get("schedule", "")
    if not schedule:
        return {"ok": False, "error": "routine has no schedule"}
    
    name = routine.get("name", "Untitled")
    cron_name = routine_cron_name(routine_id, project_id)
    
    # Build cron prompt: tell operator to trigger routine execution
    # (In real deployment, this would be a webhook or direct call)
    # For now, just post a note to inbox
    prompt = (
        f"Routine {name} fired at schedule {schedule}. "
        f"OpenBot board should execute routine {routine_id} now. "
        "Post a note to inbox/ops.md."
    )
    
    tools = project_tools(project_id) if project_id else {}
    hermes_home = str(tools.get("hermes_home") or "").strip() or None
    
    result = cron_create(
        schedule,
        prompt,
        cron_name,
        cwd=None,
        home=hermes_home,
    )
    
    return result
