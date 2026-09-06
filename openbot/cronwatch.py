"""Pull Hermes cron runs into CEO threads. Hermes remains the scheduler."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .hermes import cron_runs
from .org import ORG, patch_scope, project_ids, project_tools, rollup_staff
from .store import now_iso, write_job
from .threadstore import append_turn, thread_key

SEEN = ORG / "cron_seen.json"
OPENBOT_JOB = re.compile(r"openbot-([a-z0-9-]{1,40})-(?:ceo|[a-z0-9-]+)", re.I)
ROUTINE_CRON = re.compile(r"^openbot-routine-(.+)-(routine-[a-f0-9]{8})$")


def _cron_home_to_project(home_path: str | None) -> str | None:
    """Map a Hermes home path to a project_id."""
    if not home_path:
        return None
    
    # Check all projects for matching hermes_home
    for pid in project_ids():
        tools = project_tools(pid)
        project_home = tools.get("hermes_home")
        if project_home and Path(project_home).resolve() == Path(home_path).resolve():
            return pid
    
    return None


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
    """Poll all known Hermes homes for cron runs and route to CEO threads."""
    from .org import ensure_org
    
    org = ensure_org()
    known_projects = set(project_ids())
    jobs: list[dict] = []
    
    # Ingest from each CEO's Hermes home
    for project in org.get("projects") or []:
        pid = project.get("id")
        if not pid:
            continue
        
        tools = project_tools(pid)
        hermes_home = tools.get("hermes_home")
        if not hermes_home:
            continue
        
        # Get cron runs for this home
        try:
            from .hermes import _hermes_env, _run, which
            
            binary = which("hermes")
            if not binary:
                continue
            
            # Run hermes cron runs in this home's context
            code, text = _run([binary, "cron", "runs", "--limit", "40"], None, 30, home=hermes_home)
            if code != 0:
                continue
            
            lines = parse_run_lines(text)
            seen = _load_seen()
            known = set(seen.get("lines") or [])
            fresh = [line for line in lines if line not in known]
            
            if not fresh:
                continue
            
            known.update(fresh)
            seen["lines"] = list(known)[-200:]
            _save_seen(seen)
            
            for line in fresh:
                # Check if this is a routine cron first
                parts = line.split(maxsplit=2)
                cron_name = parts[1] if len(parts) >= 2 else ""
                routine_match = ROUTINE_CRON.match(cron_name)
                
                if routine_match:
                    scope = routine_match.group(1)
                    routine_id = routine_match.group(2)
                    project_id = None if scope == "staff" else scope
                    
                    # Execute the routine
                    from .routines import execute_routine
                    result = execute_routine(routine_id, project_id)
                    
                    job_id = f"cron{abs(hash(line)) % 10**8:08x}"
                    if result.get("ok"):
                        snippet = f"Routine {routine_id} completed ({result.get('completed_steps')}/{result.get('total_steps')} steps)"
                        patch_scope(project_id, None, "Last", f"routine {routine_id} completed")
                        patch_scope(project_id, None, "Now", "Routine finished")
                    else:
                        error = result.get("error") or result.get("blocker") or "failed"
                        failed_step = result.get("failed_at_step")
                        snippet = f"Routine {routine_id} failed at step {failed_step}: {error}"
                        patch_scope(project_id, None, "Blocker", f"routine {routine_id} step {failed_step}")
                        patch_scope(project_id, None, "Now", "Routine blocked")
                    
                    receipt = {
                        "id": job_id,
                        "at": now_iso(),
                        "preset": "ops",
                        "engine": "Hermes Agent",
                        "model": "cron",
                        "text": snippet,
                        "message": snippet,
                        "project_id": project_id,
                        "worker_id": None,
                        "usd_estimate": 0.0,
                        "cron": True,
                        "routine_result": result,
                        "keep_going": not result.get("ok"),
                        "next": "Resume routine from failed step" if not result.get("ok") else "Routine complete",
                    }
                    write_job(receipt)
                    rollup_staff(project_id, None, snippet)
                    append_turn(thread_key(project_id, None), {"role": "bot", "job": receipt})
                    jobs.append(receipt)
                    continue
                
                # Regular cron - attribute to this CEO
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
                    "project_id": pid,
                    "worker_id": None,
                    "usd_estimate": 0.0,
                    "cron": True,
                    "keep_going": True,
                    "next": "Review the run, or ask the CEO to keep going",
                }
                write_job(receipt)
                patch_scope(pid, None, "Last", f"cron {job_id}")
                patch_scope(pid, None, "Now", "Scheduled work reported")
                rollup_staff(pid, None, snippet)
                append_turn(thread_key(pid, None), {"role": "bot", "job": receipt})
                jobs.append(receipt)
                
        except Exception as e:
            print(f"[cronwatch] Error ingesting crons for {pid}: {e}", flush=True)
            continue
    
    return jobs
