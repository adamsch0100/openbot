"""Pull Hermes cron runs into CEO threads. Hermes remains the scheduler."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .hermes import cron_outcome, cron_runs, cron_title, read_home_crons
from .org import ORG, patch_scope, project_ids, project_tools, rollup_staff
from .store import now_iso, write_job
from .threadstore import append_turn, thread_key

SEEN = ORG / "cron_seen.json"
OPENBOT_JOB = re.compile(r"openbot-([a-z0-9-]{1,40})-(?:ceo|[a-z0-9-]+)", re.I)
ROUTINE_CRON = re.compile(r"^openbot-routine-(.+)-(routine-[a-f0-9]{8})$")
FRESH = timedelta(hours=36)
CRON_INDEX_NOISE = re.compile(
    r"^(grok-heartbeat|grok-build-supervisor|grok-build-driver|grok-finish-notify|alerts-email-outbox)$",
    re.I,
)


def _cron_is_noise(name: str) -> bool:
    return bool(CRON_INDEX_NOISE.match(str(name or "").strip()))


def _cron_enabled(row: dict) -> bool:
    if row.get("enabled") is False:
        return False
    return not bool(re.search(r"paused", str(row.get("state") or ""), re.I))


def _cron_failed(row: dict) -> bool:
    return bool(re.search(r"error|fail", str(row.get("last_status") or ""), re.I))


def _cron_due_soon(row: dict, *, now: datetime | None = None) -> bool:
    """Mirror board cronIsDueSoon: due within 24h, or late by up to 7 days."""
    raw = str(row.get("next_run_at") or "").strip()
    if not raw:
        return False
    when = _parse_when(raw)
    if when is None:
        return False
    stamp = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    ms = (stamp.astimezone(timezone.utc) - current).total_seconds()
    return ms <= 24 * 3600 and ms > -7 * 86400


def honest_next_line(peers: list[dict] | None) -> str:
    """INDEX Next after a healthy cron. Never claim On schedule when peers are due or failed."""
    rows = [
        row
        for row in (peers or [])
        if isinstance(row, dict) and not _cron_is_noise(str(row.get("name") or ""))
    ]
    enabled = [row for row in rows if _cron_enabled(row)]
    failed = [row for row in enabled if _cron_failed(row)]
    never = [row for row in enabled if not str(row.get("last_run_at") or "").strip()]
    if failed:
        # Schedule trust — prefer Open Schedule over hollow Open Results.
        return f"{len(failed)} failed · {len(never)} never · Open Schedule"[:160]
    due = [row for row in enabled if _cron_due_soon(row)]
    if due:
        due.sort(key=lambda row: str(row.get("next_run_at") or ""))
        title = cron_title(str(due[0].get("name") or due[0].get("title") or "job"))
        if len(due) == 1:
            return f"Due soon · {title}. Open Next."[:160]
        return f"{len(due)} due · next {title}. Open Next."[:160]
    return "On schedule. Open Next for the upcoming job."


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


def _parse_when(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def ingest_cron_runs() -> list[dict]:
    """Poll CEO Hermes homes and post a short chat card per fresh run."""
    from .org import ensure_org

    known_projects = set(project_ids())
    jobs: list[dict] = []
    jobs.extend(_ingest_home_files(None, None))
    org = ensure_org()
    for project in org.get("projects") or []:
        project_id = project.get("id")
        if not project_id:
            continue
        tools = project_tools(project_id)
        home = str(tools.get("hermes_home") or "").strip() or None
        if home:
            jobs.extend(_ingest_home_files(str(project_id), home))
        else:
            jobs.extend(_ingest_home_runs(str(project_id), known_projects, None))
        if str(project_id) == "saa-homes":
            jobs.extend(_ingest_overlay_rows("saa-homes"))
    return jobs


def _ingest_home_files(project_id: str | None, hermes_home: str | None) -> list[dict]:
    if not hermes_home:
        return []
    seen = _load_seen()
    known = set(seen.get("lines") or [])
    now = datetime.now(timezone.utc)
    posted: list[dict] = []
    rows = [row for row in read_home_crons(hermes_home, results=True) if row.get("last_run_at")]
    rows.sort(key=lambda row: str(row.get("last_run_at") or ""), reverse=True)
    for row in rows[:8]:
        last = str(row.get("last_run_at") or "")
        when = _parse_when(last)
        if when is not None:
            stamp = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
            if now - stamp.astimezone(timezone.utc) > timedelta(days=14):
                continue
        key = f"{project_id or '_staff'}:{row.get('id')}:{last}"
        if key in known:
            continue
        known.add(key)
        if _cron_is_noise(str(row.get("name") or "")):
            continue
        posted.append(_post_cron_card(project_id, row, hermes_home))
    if posted:
        seen["lines"] = list(known)[-400:]
        _save_seen(seen)
    return posted


def _ingest_overlay_rows(project_id: str) -> list[dict]:
    from .hermes import load_saa_overlay_cache, overlay_to_cron_rows

    rows = overlay_to_cron_rows(load_saa_overlay_cache())
    if not rows:
        return []
    hermes_home = str(project_tools(project_id).get("hermes_home") or "").strip() or None
    seen = _load_seen()
    known = set(seen.get("lines") or [])
    now = datetime.now(timezone.utc)
    posted: list[dict] = []
    rows = [row for row in rows if row.get("last_run_at")]
    rows.sort(key=lambda row: str(row.get("last_run_at") or ""), reverse=True)
    for row in rows[:8]:
        last = str(row.get("last_run_at") or "")
        when = _parse_when(last)
        if when is not None:
            stamp = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
            if now - stamp.astimezone(timezone.utc) > timedelta(days=14):
                continue
        key = f"{project_id or '_staff'}:{row.get('id')}:{last}"
        if key in known:
            continue
        known.add(key)
        if _cron_is_noise(str(row.get("name") or "")):
            continue
        posted.append(_post_cron_card(project_id, row, hermes_home))
    if posted:
        seen["lines"] = list(known)[-400:]
        _save_seen(seen)
    return posted



def _honest_next_line(project_id: str | None, hermes_home: str | None = None, finished: str = "") -> str:
    """Never blanket 'On schedule' when dues or fails exist on this CEO."""
    home = hermes_home
    if not home and project_id:
        home = str(project_tools(project_id).get("hermes_home") or "").strip() or None
    rows: list[dict] = []
    if home:
        try:
            rows = [
                row
                for row in read_home_crons(home, results=False)
                if not _cron_is_noise(str(row.get("name") or ""))
            ]
        except Exception:
            rows = []
    now = datetime.now(timezone.utc)
    fails: list[dict] = []
    dues: list[tuple[datetime, dict]] = []
    for row in rows:
        if row.get("enabled") is False:
            continue
        status = str(row.get("last_status") or "").lower()
        if re.search(r"error|fail", status):
            blob = f"{row.get('last_error') or ''} {row.get('outcome') or ''} {row.get('last_result') or ''}"
            if re.search(r"gateway shutdown|gateway stopped mid-run", blob, re.I):
                continue
            last = _parse_when(str(row.get("last_run_at") or ""))
            if last is not None:
                stamp = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                if now - stamp.astimezone(timezone.utc) > timedelta(hours=48):
                    continue
            fails.append(row)
            continue
        nxt = _parse_when(str(row.get("next_run_at") or ""))
        if nxt is None:
            continue
        stamp = nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)
        delta = stamp.astimezone(timezone.utc) - now
        if timedelta(days=-7) < delta <= timedelta(hours=24):
            dues.append((stamp, row))
    dues.sort(key=lambda item: item[0])
    never_n = sum(
        1
        for row in rows
        if row.get("enabled") is not False and not str(row.get("last_run_at") or "").strip()
    )
    # Include gateway scars in schedule-trust NOW (UI Schedule tab owns them).
    fail_n = sum(
        1
        for row in rows
        if row.get("enabled") is not False
        and re.search(r"error|fail", str(row.get("last_status") or ""), re.I)
    )
    if fail_n:
        who = "SAA" if "saa" in str(project_id or "").lower() else "CEO"
        return f"{who} · {fail_n} failed · {never_n} never · Open Schedule."
    if dues:
        stamp, row = dues[0]
        title = cron_title(str(row.get("name") or row.get("id") or "job"))
        mins = int(max(0, (stamp.astimezone(timezone.utc) - now).total_seconds() // 60))
        if mins <= 30:
            when = "due now"
        elif mins < 60:
            when = f"in {mins} min"
        else:
            when = stamp.astimezone().strftime("%a %H:%M")
        more = f" · +{len(dues) - 1} more" if len(dues) > 1 else ""
        return f"Next: {title} {when}{more}."
    if finished:
        return f"{finished} done. Nothing else due in the next day."
    return "Nothing due in the next day. Open Next for the full queue."


def _post_cron_card(project_id: str | None, row: dict, hermes_home: str | None = None, *, peers: list[dict] | None = None) -> dict:
    name = str(row.get("name") or row.get("id") or "cron")
    title = str(row.get("title") or cron_title(name))
    outcome = str(row.get("outcome") or cron_outcome(row.get("last_status") or "", row.get("last_result") or "")[0])
    nxt = str(row.get("next_action") or "No action unless something failed.")
    report = str(row.get("last_result") or "")
    when = str(row.get("last_run_at") or "").strip()
    snippet = f"RESULT\n{title}\n{outcome}"
    if nxt and not re.search(r"no action", nxt, re.I):
        snippet = f"{snippet}\nWhat to do: {nxt}"
    if when:
        snippet = f"{snippet}\nRan: {when}"
    body = str(row.get("last_result") or report)
    job_id = f"cron{abs(hash(f'{project_id}:{row.get('id')}:{row.get('last_run_at')}')) % 10**8:08x}"
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
        "cron_id": str(row.get("id") or ""),
        "cron_name": title,
        "cron_outcome": outcome,
        "cron_next": nxt,
        "cron_report": report[:4000] or body[:4000],
        "cron_result": report[:4000] or body[:4000],
        "cron_when": when,
        "keep_going": bool(re.search(r"fail|error", f"{row.get('last_status') or ''} {outcome}", re.I)),
        "next": nxt,
    }
    write_job(receipt)
    if receipt["keep_going"]:
        patch_scope(project_id, None, "Now", f"{title} failed · {outcome[:80]}")
        patch_scope(project_id, None, "Last", f"{title} failed")
        patch_scope(project_id, None, "Next", nxt[:160] or "Open this CEO and handle the failed job.")
        patch_scope(project_id, None, "Blocker", outcome[:140])
    else:
        patch_scope(project_id, None, "Now", f"{title} is done · {outcome[:80]}")
        patch_scope(project_id, None, "Last", f"{title} · {outcome[:80]}")
        if hermes_home is not None or peers is None:
            next_line = _honest_next_line(project_id, hermes_home=hermes_home, finished=title)[:160]
        else:
            next_line = honest_next_line(peers)[:160]
        patch_scope(project_id, None, "Next", next_line)
        patch_scope(project_id, None, "Blocker", "—")
    rollup_staff(project_id, None, f"{title} is done · {outcome}")
    append_turn(thread_key(project_id, None), {"role": "bot", "job": receipt})
    return receipt


def _ingest_home_runs(project_id: str | None, known_projects: set, hermes_home: str | None = None) -> list[dict]:
    """Fallback: parse `hermes cron runs` for homes without jobs.json."""
    try:
        ran = cron_runs(limit=40, cwd=None, home=hermes_home)
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
        parts = line.split(maxsplit=2)
        cron_name = parts[1] if len(parts) >= 2 else ""
        routine_match = ROUTINE_CRON.match(cron_name)
        if routine_match:
            continue
        match = OPENBOT_JOB.search(line)
        target = match.group(1) if match and match.group(1) in known_projects else project_id
        if not target:
            continue
        snippet = re.sub(r"\s+", " ", line)[:400]
        job_id = f"cron{abs(hash(line)) % 10**8:08x}"
        receipt = {
            "id": job_id,
            "at": now_iso(),
            "preset": "ops",
            "engine": "Hermes Agent",
            "model": "cron",
            "text": f"{snippet}\nOpen Schedule for the report.",
            "message": snippet,
            "project_id": target,
            "worker_id": None,
            "usd_estimate": 0.0,
            "cron": True,
            "keep_going": True,
            "next": "Open Schedule for the report.",
        }
        write_job(receipt)
        patch_scope(target, None, "Last", f"cron {job_id}")
        rollup_staff(target, None, snippet)
        append_turn(thread_key(target, None), {"role": "bot", "job": receipt})
        jobs.append(receipt)
    return jobs
