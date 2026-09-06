"""Parse and execute multi-seat spawns from one message."""

from __future__ import annotations

import re
import threading
from typing import Callable

from .router import handle

# Pattern to detect @seat mentions in a message
# Matches: @builder, @Builder, @Code, @Research, etc.
SEAT_MENTION = re.compile(
    r"@(builder|code|research|think|ops|cos|auto)\b",
    re.I,
)

# Map UI seat names to router presets
SEAT_TO_PRESET = {
    "builder": "builder",
    "code": "builder",
    "research": "research",
    "think": "think",
    "ops": "ops",
    "cos": "cos",
    "auto": None,  # Auto routing
}


def parse_seat_tasks(message: str) -> list[tuple[str, str]]:
    """Parse message for @seat mentions and extract per-seat tasks.
    
    Format examples:
    - "@Builder: add logging; @Research: fetch API docs"
    - "@Code add logging @Research fetch docs"
    - "Builder: add logging. Research: fetch the docs."
    
    Returns list of (preset, task) tuples, preserving order.
    """
    tasks = []
    
    # Split message by @seat mentions
    parts = re.split(r"(@(?:builder|code|research|think|ops|cos|auto)\b[:\s]*)", message, flags=re.I)
    
    current_seat = None
    current_task = []
    
    for part in parts:
        # Check if this part is a @seat mention
        match = SEAT_MENTION.match(part.strip())
        if match:
            # Save previous task if any
            if current_seat and current_task:
                task_text = " ".join(current_task).strip()
                # Remove trailing semicolons/periods if they separate tasks
                task_text = task_text.rstrip(";.").strip()
                if task_text:
                    tasks.append((current_seat, task_text))
            
            # Start new task
            seat_name = match.group(1).lower()
            current_seat = SEAT_TO_PRESET.get(seat_name)
            current_task = []
        else:
            # Accumulate task text
            if current_seat is not None:
                current_task.append(part.strip())
    
    # Save final task
    if current_seat and current_task:
        task_text = " ".join(current_task).strip().rstrip(";.").strip()
        if task_text:
            tasks.append((current_seat, task_text))
    
    # If no @mentions found, return empty list (not an error, just single-seat routing)
    return tasks


def spawn_parallel(
    tasks: list[tuple[str, str]],
    folder: str | None = None,
    project_id: str | None = None,
    worker_id: str | None = None,
    on_delta: Callable | None = None,
    on_progress: Callable | None = None,
    run_id: str | None = None,
    quote: str | None = None,
    attachments: list | None = None,
) -> list[dict]:
    """Spawn multiple handle() calls in parallel, one per seat task.
    
    Returns list of job result dicts, in order of tasks.
    """
    if not tasks:
        return []
    
    results = [None] * len(tasks)
    threads = []
    
    def worker_fn(index: int, preset: str, message: str) -> None:
        try:
            result = handle(
                message=message,
                folder=folder,
                preset=preset,
                project_id=project_id,
                worker_id=worker_id,
                on_delta=on_delta,
                on_progress=on_progress,
                run_id=None,  # Each spawn gets its own run
                quote=quote if index == 0 else None,
                chain_context=None,
                attachments=attachments if index == 0 else None,
            )
            results[index] = result
        except Exception as err:
            # Record error as a pseudo-job result
            results[index] = {
                "id": f"spawn-error-{index}",
                "preset": preset,
                "engine": "board",
                "text": f"Spawn failed: {err}",
                "blocker": str(err),
                "ok": False,
            }
    
    # Launch threads
    for i, (preset, task) in enumerate(tasks):
        thread = threading.Thread(
            target=worker_fn,
            args=(i, preset, task),
            daemon=False,
            name=f"spawn-{i}-{preset}",
        )
        thread.start()
        threads.append(thread)
    
    # Wait for all to complete
    for thread in threads:
        thread.join(timeout=600)  # 10 min max per spawn
    
    # Filter out None results (shouldn't happen, but defensive)
    return [r for r in results if r is not None]


def is_multi_spawn(message: str) -> bool:
    """Check if message contains multiple @seat mentions."""
    mentions = SEAT_MENTION.findall(message)
    return len(mentions) >= 2


def multi_spawn_handle(
    message: str,
    folder: str | None = None,
    project_id: str | None = None,
    worker_id: str | None = None,
    on_delta: Callable | None = None,
    on_progress: Callable | None = None,
    run_id: str | None = None,
    quote: str | None = None,
    attachments: list | None = None,
) -> dict:
    """Handle a multi-spawn message, returning combined result.
    
    If message has 2+ @seat mentions, parses and spawns parallel workers.
    Otherwise, falls through to normal routing.
    
    Returns a job-like dict with:
    - spawns: list of individual job results
    - text: combined text from all spawns
    - preset: "multi-spawn"
    """
    tasks = parse_seat_tasks(message)
    
    if len(tasks) < 2:
        # Not a multi-spawn, return None to signal fallthrough
        return None
    
    # Spawn parallel workers
    if on_progress:
        try:
            on_progress(f"Spawning {len(tasks)} workers: {', '.join(t[0] or 'auto' for t in tasks)}", None)
        except Exception:
            pass
    
    results = spawn_parallel(
        tasks,
        folder=folder,
        project_id=project_id,
        worker_id=worker_id,
        on_delta=on_delta,
        on_progress=on_progress,
        run_id=run_id,
        quote=quote,
        attachments=attachments,
    )
    
    # Combine results
    combined_text = "\n\n".join(
        f"[{r.get('preset', 'unknown')} · {r.get('engine', 'board')}]\n{r.get('text', '(no output)')}"
        for r in results
    )
    
    # Build combined job result
    import uuid
    from .store import now_iso
    
    combined = {
        "id": uuid.uuid4().hex[:10],
        "at": now_iso(),
        "preset": "multi-spawn",
        "engine": "board",
        "model": "none",
        "text": combined_text,
        "spawns": results,
        "spawn_count": len(results),
        "message": message,
        "project_id": project_id,
        "worker_id": worker_id,
        "blocker": None,
        "keep_going": False,
    }
    
    # Check if any spawns blocked
    if any(r.get("blocker") for r in results):
        combined["blocker"] = f"{sum(1 for r in results if r.get('blocker'))} spawn(s) blocked"
    
    return combined
