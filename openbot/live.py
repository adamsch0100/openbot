"""Live engine runs. Stream and stop. Not a third agent."""

from __future__ import annotations

import subprocess
import threading

_lock = threading.Lock()
_runs: dict[str, dict] = {}


def start(run_id: str, meta: dict | None = None) -> threading.Event:
    cancel = threading.Event()
    row = {"cancel": cancel, "proc": None}
    if isinstance(meta, dict):
        for key in ("project_id", "worker_id", "preset", "title"):
            value = meta.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                row[key] = text[:80] if key == "title" else text
    with _lock:
        _runs[run_id] = row
    return cancel


def snapshot() -> list[dict]:
    """In-flight board chats. Hermes remains the scheduler."""
    with _lock:
        out = []
        for run_id, row in _runs.items():
            out.append(
                {
                    "id": run_id,
                    "project_id": str(row.get("project_id") or ""),
                    "worker_id": str(row.get("worker_id") or ""),
                    "preset": str(row.get("preset") or "cos"),
                    "title": str(row.get("title") or "This chat"),
                }
            )
        return out


def attach(run_id: str, proc: subprocess.Popen | None) -> None:
    with _lock:
        row = _runs.get(run_id)
        if row is not None:
            row["proc"] = proc


def cancel_event(run_id: str) -> threading.Event | None:
    with _lock:
        row = _runs.get(run_id)
        return row["cancel"] if row else None


def stop(run_id: str) -> bool:
    with _lock:
        row = _runs.get(run_id)
    if not row:
        return False
    row["cancel"].set()
    proc = row.get("proc")
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    return True


def finish(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)
