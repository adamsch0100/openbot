"""INDEX and brains are files. Chat is not the database."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAINS = ROOT / "brains"
JOBS = ROOT / "jobs"
INDEX = BRAINS / "INDEX.md"
JOB_ID_RE = re.compile(r"^[a-f0-9]{6,32}$")
BRAIN_NAMES = {"cos", "builder", "research", "ops", "think"}
MAX_FILE_CHARS = 100_000


def read_index() -> str:
    return INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""


def read_brain(name: str) -> str:
    if name not in BRAIN_NAMES:
        return ""
    path = BRAINS / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_index(text: str) -> str:
    if len(text) > MAX_FILE_CHARS:
        raise ValueError("INDEX too large")
    INDEX.write_text(text, encoding="utf-8")
    return read_index()


def write_brain(name: str, text: str) -> str:
    if name not in BRAIN_NAMES:
        raise ValueError("unknown brain")
    if len(text) > MAX_FILE_CHARS:
        raise ValueError("brain too large")
    path = BRAINS / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return read_brain(name)


def list_brains() -> dict[str, str]:
    return {name: read_brain(name) for name in sorted(BRAIN_NAMES)}


def patch_index_line(label: str, value: str) -> None:
    text = read_index()
    pattern = rf"^{re.escape(label)}:.*$"
    repl = f"{label}: {value}"
    if re.search(pattern, text, flags=re.M):
        text = re.sub(pattern, lambda _match: repl, text, count=1, flags=re.M)
    else:
        text = text.rstrip() + f"\n{repl}\n"
    INDEX.write_text(text, encoding="utf-8")


def write_job(receipt: dict) -> Path:
    JOBS.mkdir(exist_ok=True)
    path = JOBS / f"{receipt['id']}.json"
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return path


def job_path(job_id: str) -> Path | None:
    if not JOB_ID_RE.match(job_id):
        return None
    path = JOBS / f"{job_id}.json"
    return path if path.is_file() else None


def read_job(job_id: str) -> dict | None:
    path = job_path(job_id)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def update_job(job_id: str, fields: dict) -> dict | None:
    receipt = read_job(job_id)
    if receipt is None:
        return None
    receipt.update(fields)
    write_job(receipt)
    return receipt


def list_jobs() -> list[dict]:
    if not JOBS.exists():
        return []
    jobs: list[dict] = []
    for path in JOBS.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            jobs.append(data)
    return jobs


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_job_time(at_iso: str) -> datetime | None:
    if not at_iso:
        return None
    try:
        return datetime.fromisoformat(at_iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def in_spend_period(at_iso: str, period: str, now: datetime | None = None) -> bool:
    dt = parse_job_time(at_iso)
    if dt is None:
        return False
    current = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if period == "day":
        return dt.date() == current.date()
    if period == "month":
        return dt.year == current.year and dt.month == current.month
    return dt.isocalendar()[:2] == current.isocalendar()[:2]


def spend_bucket(job: dict) -> str:
    engine = str(job.get("engine") or "").lower()
    if "opencode" in engine:
        return "opencode"
    if "hermes" in engine:
        return "hermes"
    return "chat"


def spend_summary(
    cap_usd: float,
    period: str,
    now: datetime | None = None,
    project_id: str | None = None,
    policy=None,
    go_usage=None,
) -> dict:
    from .spend import snapshot

    kwargs = {"now": now, "project_id": project_id, "policy": policy}
    if go_usage is not None:
        kwargs["go_usage"] = go_usage
    return snapshot(float(cap_usd), period, **kwargs)
