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
    ran = cron_runs(limit=40)
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
    known_projects = set(project_ids())
    jobs: list[dict] = []
    for line in fresh:
        match = OPENBOT_JOB.search(line)
        project_id = match.group(1) if match and match.group(1) in known_projects else None
        if not project_id:
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
            "project_id": project_id,
            "worker_id": None,
            "usd_estimate": 0.0,
            "cron": True,
            "keep_going": True,
            "next": "Review the run, or ask the CEO to keep going",
        }
        write_job(receipt)
        patch_scope(project_id, None, "Last", f"cron {job_id}")
        patch_scope(project_id, None, "Now", "Scheduled work reported")
        rollup_staff(project_id, None, snippet)
        append_turn(thread_key(project_id, None), {"role": "bot", "job": receipt})
        jobs.append(receipt)
    return jobs
