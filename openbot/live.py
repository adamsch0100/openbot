"""Live engine runs. Stream and stop. Not a third agent."""

from __future__ import annotations

import subprocess
import threading

_lock = threading.Lock()
_runs: dict[str, dict] = {}


def start(run_id: str) -> threading.Event:
    cancel = threading.Event()
    with _lock:
        _runs[run_id] = {"cancel": cancel, "proc": None}
    return cancel


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
