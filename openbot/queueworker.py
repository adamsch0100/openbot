"""Autonomous task queue worker. Checks bus/handoffs/ and claims open work."""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from .bus import claim_handoff, load_open_handoffs
from .router import handle
from .store import ROOT

# Global worker pool state
_worker_threads: dict[str, threading.Thread] = {}
_worker_lock = threading.Lock()
_shutdown = threading.Event()

# Pattern to detect need-docs or similar signals
NEED_DOCS = re.compile(
    r"\b(need (the )?(api )?docs?|fetch (the )?(api )?docs?|"
    r"look up (the )?(api )?docs?|research (the )?(api )?docs?|"
    r"documentation needed|check (the )?documentation)\b",
    re.I,
)


def detect_handoff_signals(text: str) -> list[tuple[str, str]]:
    """Detect handoff signals in job result text.
    
    Returns list of (to_seat, reason) tuples.
    
    Patterns:
    - "need docs" / "fetch docs" → Research
    - Future: add more patterns as needed
    """
    signals = []
    
    if NEED_DOCS.search(text or ""):
        signals.append(("research", "documentation lookup needed"))
    
    return signals


def auto_create_handoffs(
    job_result: dict,
    result_text: str,
    project_id: str | None = None,
) -> list[dict]:
    """Auto-create handoffs based on signals in job result.
    
    Returns list of created handoff dicts.
    """
    signals = detect_handoff_signals(result_text)
    if not signals:
        return []
    
    from .bus import create_handoff
    
    created = []
    from_seat = str(job_result.get("preset") or "board")
    
    for to_seat, reason in signals:
        # Extract task from result or use generic
        task = f"[Auto-handoff] {reason}: {result_text[:200]}"
        
        result = create_handoff(
            task=task,
            project_id=project_id,
            from_seat=from_seat,
            to_seat=to_seat,
            next_owner=to_seat,
            output="—",
        )
        
        if result.get("ok"):
            created.append({
                "handoff_id": result["handoff_id"],
                "to_seat": to_seat,
                "reason": reason,
            })
    
    return created


def claim_and_execute(
    handoff_id: str,
    project_id: str | None,
    claimant: str,
    *,
    on_progress=None,
) -> dict | None:
    """Claim a handoff and execute it as a job.
    
    Returns job result dict or None if claim failed.
    """
    from .bus import ensure_bus
    from .org import ensure_ceo_engines
    
    # Claim the handoff
    claim_result = claim_handoff(handoff_id, project_id, claimant)
    
    if not claim_result.get("ok"):
        return None
    
    # Read the handoff file directly by id (don't rely on load_open_handoffs + status filter)
    bus_dir = ensure_bus(project_id)
    handoff_path = bus_dir / "handoffs" / f"{handoff_id}.md"
    
    if not handoff_path.is_file():
        return None
    
    try:
        text = handoff_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        
        # Parse fields
        task = ""
        to_seat = ""
        
        for line in lines:
            if line.startswith("TASK:"):
                task = line[5:].strip()
            elif line.startswith("TO:"):
                to_seat = line[3:].strip()
        
        if not task or not to_seat:
            return None
        
    except (OSError, UnicodeDecodeError):
        return None
    
    # Ensure CEO engines are warmed
    if project_id:
        ensure_ceo_engines(project_id)
    
    # Map to_seat to preset
    preset_map = {
        "builder": "builder",
        "code": "builder",
        "research": "research",
        "think": "think",
        "ops": "ops",
    }
    preset = preset_map.get(to_seat.lower(), "builder")
    
    # Execute via router.handle
    try:
        result = handle(
            message=task,
            folder=None,
            preset=preset,
            project_id=project_id,
            worker_id=None,
            on_delta=None,
            on_progress=on_progress,
            run_id=None,
            quote=None,
            chain_context=None,
            attachments=None,
        )
        
        # Update handoff to complete
        if handoff_path.is_file():
            text = handoff_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            updated = []
            for line in lines:
                if line.startswith("STATUS:"):
                    status = "complete" if not result.get("blocker") else "blocked"
                    updated.append(f"STATUS: {status}")
                elif line.startswith("OUTPUT:"):
                    output = str(result.get("text") or "—")[:1600]
                    updated.append(f"OUTPUT: {output}")
                else:
                    updated.append(line)
            handoff_path.write_text("\n".join(updated), encoding="utf-8")
        
        return result
    except Exception as err:
        # Update handoff to blocked
        if handoff_path.is_file():
            text = handoff_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            updated = []
            for line in lines:
                if line.startswith("STATUS:"):
                    updated.append("STATUS: blocked")
                elif line.startswith("OUTPUT:"):
                    updated.append(f"OUTPUT: Worker failed: {err}")
                else:
                    updated.append(line)
            handoff_path.write_text("\n".join(updated), encoding="utf-8")
        
        return None


def queue_worker_loop(project_id: str | None, worker_name: str) -> None:
    """Worker loop: poll for open handoffs and claim+execute them.
    
    Runs until _shutdown is set.
    """
    poll_interval = 10  # seconds between polls
    
    while not _shutdown.is_set():
        try:
            # Load open handoffs for this CEO scope
            handoffs = load_open_handoffs(project_id, limit=20)
            
            # Filter for open (not claimed) handoffs
            open_handoffs = [h for h in handoffs if h["status"] == "open"]
            
            if open_handoffs:
                # Claim the first open handoff
                handoff = open_handoffs[0]
                
                result = claim_and_execute(
                    handoff["id"],
                    project_id,
                    worker_name,
                    on_progress=None,
                )
                
                # If execution succeeded, check for new handoff signals
                if result and not result.get("blocker"):
                    auto_create_handoffs(
                        result,
                        result.get("text") or "",
                        project_id=project_id,
                    )
            
            # Sleep between polls
            _shutdown.wait(poll_interval)
            
        except Exception:
            # Swallow errors and keep running
            _shutdown.wait(poll_interval)


def start_queue_worker(project_id: str | None, worker_name: str) -> str:
    """Start a queue worker thread for a CEO scope.
    
    Returns worker thread id.
    """
    key = f"{project_id or 'staff'}::{worker_name}"
    
    with _worker_lock:
        if key in _worker_threads and _worker_threads[key].is_alive():
            return key  # Already running
        
        thread = threading.Thread(
            target=queue_worker_loop,
            args=(project_id, worker_name),
            daemon=True,
            name=f"qworker-{key}",
        )
        thread.start()
        _worker_threads[key] = thread
    
    return key


def stop_queue_workers() -> None:
    """Stop all queue worker threads."""
    _shutdown.set()
    
    with _worker_lock:
        for thread in _worker_threads.values():
            if thread.is_alive():
                thread.join(timeout=2.0)
        _worker_threads.clear()
    
    _shutdown.clear()


def active_workers() -> list[dict]:
    """List active queue worker threads.
    
    Returns list of {key, name, alive} dicts.
    """
    with _worker_lock:
        return [
            {
                "key": key,
                "name": thread.name,
                "alive": thread.is_alive(),
            }
            for key, thread in _worker_threads.items()
        ]
