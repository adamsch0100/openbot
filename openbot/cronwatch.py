"""Pull Hermes cron runs into CEO threads. Hermes remains the scheduler."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .hermes import cron_runs
from .org import ORG, patch_scope, project_ids, rollup_staff
from .store import now_iso, write_job
from .threadstore import append_turn, thread_key

SEEN = ORG / "cron_seen.json"
OPENBOT_JOB = re.compile(r"openbot-([a-z0-9-]{1,40})-(?:ceo|[a-z0-9-]+)", re.I)
ROUTINE_CRON = re.compile(r"^openbot-routine-(.+)-(routine-[a-f0-9]{8})$")


def _load_seen() -> dict:
    if not SEEN.is_file():
        return {"lines": []}
    try:
        data = json.loads(SEEN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lines": []}
    return data if isinstance(data, dict) else {"lines": []}


def _save_seen(data: dict) -> None:
    ORG.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_run_lines(text: str) -> list[str]:
    if not text or "No cron execution" in text:
        return []
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or set(line) <= {"-", "="}:
            continue
        if re.match(r"^(job|id|name|schedule|status|when)\b", line, re.I):
            continue
        lines.append(line)
    return lines[-40:]


def ingest_cron_runs() -> list[dict]:
    """
    Poll all CEO Hermes homes for cron runs and route to correct threads.
    
    Returns list of job receipts posted to threads.
    """
    from .org import ensure_org
    
    known_projects = set(project_ids())
    jobs: list[dict] = []
    
    # Staff crons (default home)
    staff_runs = _ingest_home_runs(None, known_projects)
    jobs.extend(staff_runs)
    
    # Per-CEO crons
    org = ensure_org()
    for project in org.get("projects") or []:
        project_id = project.get("id")
        if not project_id:
            continue
        
        from .org import project_tools
        tools = project_tools(project_id)
        hermes_home = str(tools.get("hermes_home") or "").strip() or None
        
        if hermes_home:
            ceo_runs = _ingest_home_runs(project_id, known_projects, hermes_home)
            jobs.extend(ceo_runs)
    
    return jobs


def _ingest_home_runs(project_id: str | None, known_projects: set, hermes_home: str | None = None) -> list[dict]:
    """Ingest cron runs from a specific Hermes home."""
    try:
        ran = cron_runs(limit=40, cwd=None, home=hermes_home) if hermes_home else cron_runs(limit=40)
    except Exception:
        return []
    
    text = ran.get("text") or ""
    lines = parse_run_lines(text)
    seen = _load_seen()
    known = set(seen.get("lines") or [])
    fresh = [line for line in lines if line not in known]
    if not fresh:
        return []
    known.update(fresh)
    seen["lines"] = list(known)[-200:]
    _save_seen(seen)
    
    jobs: list[dict] = []
    for line in fresh:
        # Check if this is a routine cron first
        parts = line.split(maxsplit=2)
        cron_name = parts[1] if len(parts) >= 2 else ""
        routine_match = ROUTINE_CRON.match(cron_name)
        
        if routine_match:
            scope = routine_match.group(1)
            routine_id = routine_match.group(2)
            target_project_id = None if scope == "staff" else scope
            
            # Execute the routine
            from .routines import execute_routine
            result = execute_routine(routine_id, target_project_id)
            
            job_id = f"cron{abs(hash(line)) % 10**8:08x}"
            if result.get("ok"):
                snippet = f"Routine {routine_id} completed ({result.get('completed_steps')}/{result.get('total_steps')} steps)"
                patch_scope(target_project_id, None, "Last", f"routine {routine_id} completed")
                patch_scope(target_project_id, None, "Now", "Routine finished")
            else:
                error = result.get("error") or result.get("blocker") or "failed"
                failed_step = result.get("failed_at_step")
                snippet = f"Routine {routine_id} failed at step {failed_step}: {error}"
                patch_scope(target_project_id, None, "Blocker", f"routine {routine_id} step {failed_step}")
                patch_scope(target_project_id, None, "Now", "Routine blocked")
            
            receipt = {
                "id": job_id,
                "at": now_iso(),
                "preset": "ops",
                "engine": "Hermes Agent",
                "model": "cron",
                "text": snippet,
                "message": snippet,
                "project_id": target_project_id,
                "worker_id": None,
                "usd_estimate": 0.0,
                "cron": True,
                "routine_result": result,
                "keep_going": not result.get("ok"),
                "next": "Resume routine from failed step" if not result.get("ok") else "Routine complete",
            }
            write_job(receipt)
            rollup_staff(target_project_id, None, snippet)
            append_turn(thread_key(target_project_id, None), {"role": "bot", "job": receipt})
            jobs.append(receipt)
            continue
        
        # Regular OpenBot cron (not a routine)
        match = OPENBOT_JOB.search(line)
        target_project_id = match.group(1) if match and match.group(1) in known_projects else project_id
        if not target_project_id:
            continue
        job_id = f"cron{abs(hash(line)) % 10**8:08x}"
        snippet = re.sub(r"\s+", " ", line)[:400]
        receipt = {
            "id": job_id,
            "at": now_iso(),
            "preset": "ops",
            "engine": "Hermes Agent",
            "model": "cron",
            "text": f"Scheduled run\n{snippet}",
            "message": snippet,
            "project_id": target_project_id,
            "worker_id": None,
            "usd_estimate": 0.0,
            "cron": True,
            "keep_going": True,
            "next": "Review the run, or ask the CEO to keep going",
        }
        write_job(receipt)
        patch_scope(target_project_id, None, "Last", f"cron {job_id}")
        patch_scope(target_project_id, None, "Now", "Scheduled work reported")
        rollup_staff(target_project_id, None, snippet)
        append_turn(thread_key(target_project_id, None), {"role": "bot", "job": receipt})
        jobs.append(receipt)
    return jobs
