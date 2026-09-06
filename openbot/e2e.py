"""E2E test helpers for OpenBot board."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import ROOT


def record_e2e_run(run_id: str, results: list[dict], metadata: dict | None = None) -> Path:
    """Record E2E test run results to activity log."""
    e2e_dir = ROOT / "tests" / "e2e" / "runs"
    e2e_dir.mkdir(parents=True, exist_ok=True)
    
    run_file = e2e_dir / f"{run_id}.json"
    
    passed = sum(1 for r in results if r.get("passed"))
    failed = sum(1 for r in results if not r.get("passed"))
    
    run_data = {
        "run_id": run_id,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
        },
        "metadata": metadata or {},
    }
    
    with open(run_file, "w") as f:
        json.dump(run_data, f, indent=2)
    
    return run_file


def latest_e2e_run() -> dict | None:
    """Get latest E2E run results."""
    e2e_dir = ROOT / "tests" / "e2e" / "runs"
    if not e2e_dir.exists():
        return None
    
    run_files = sorted(e2e_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not run_files:
        return None
    
    with open(run_files[0]) as f:
        return json.load(f)


def e2e_status() -> dict:
    """Get E2E test status summary."""
    latest = latest_e2e_run()
    if not latest:
        return {
            "status": "never_run",
            "message": "No E2E test runs found",
        }
    
    summary = latest.get("summary", {})
    all_passed = summary.get("failed", 0) == 0
    
    return {
        "status": "passed" if all_passed else "failed",
        "run_id": latest.get("run_id"),
        "summary": summary,
        "results": latest.get("results", []),
    }
