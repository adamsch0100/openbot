"""22 weekday ticks = one compressed month. Files, not calendar. No live SAA Think."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .decide import (
    ACCEPT_ONLY,
    FINANCIAL,
    HEARTBEAT_MARK,
    auto_labor_allowed,
    classify_proposal,
    ingest_think_result,
    last_labor_review,
    load_open_proposal,
    proposal_packet_extra,
    recommended_auto_policy,
    write_proposal,
)
from .org import horizon_week, index_field, patch_project_tools, patch_scope, read_project_index
from .store import write_job

DESK_ID = "desk-month"
WEEK = "1 live CHFA page · NoCO · via organic · proof form 200"

# One weekday each. World is what changed. labor is what happens if the board autos.
MONTH = (
    {"world": "CHFA contact form returns HTTP 404", "labor": "ok"},
    {"world": "Form still 404 after overnight cache", "labor": "ok"},
    {"world": "Need a NoCO city landing page in the repo", "labor": "ok"},
    {"world": "Comps show the listing price is too low", "labor": "hold"},
    {"world": "Railway box looks stale; ops should restart gateway", "labor": "hold"},
    {"world": "Form 200 restored; add proof screenshot path in repo", "labor": "ok"},
    {"world": "Research public CHFA page copy vs our overlay", "labor": "ok"},
    {"world": "OpenCode missing while patching the form", "labor": "fail"},
    {"world": "Same form 404 after yesterday's failed Code job", "labor": "ok"},
    {"world": "Organic landing still has no proof metric", "labor": "ok"},
    {"world": "Pay the Stripe ads invoice or the wallet dies", "labor": "hold"},
    {"world": "Fix the contact form handler unit test", "labor": "ok"},
    {"world": "Publish the CHFA page live to production", "labor": "hold"},
    {"world": "Draft a research note on NoCO search demand", "labor": "ok"},
    {"world": "Form 200; git dirty on the city page", "labor": "ok"},
    {"world": "Budget talk: raise spend cap this week", "labor": "hold"},
    {"world": "Ops: pause a noisy local cron copy, not Railway", "labor": "hold"},
    {"world": "Wire the city page CTA to the restored form", "labor": "ok"},
    {"world": "Listing price still below comps on the draft page", "labor": "hold"},
    {"world": "Delete the old 404 debug banner from the template", "labor": "hold"},
    {"world": "Research whether CHFA still lists our city", "labor": "ok"},
    {"world": "Form 200 and city page in repo; next is proof screenshot", "labor": "ok"},
)


def file_brain(project_id: str, world: str) -> str:
    """Stand-in for Hermes Think. Reads the same files the packet would. Not a third engine."""
    audit = last_labor_review(project_id)
    review = str(audit.get("review") or "none")
    week = horizon_week(read_project_index(project_id)) or WEEK
    extra = proposal_packet_extra(project_id, HEARTBEAT_MARK)
    prior = str(audit.get("proposal_next") or "").strip()
    lower = world.lower()
    if ACCEPT_ONLY.search(world):
        lane, nxt, kind = "none", f"Park: {world[:80]}", "accept"
    elif FINANCIAL.search(world):
        lane, nxt, kind = "ops", world[:80], "financial"
    elif "research" in lower or "public chfa" in lower or "search demand" in lower:
        lane, nxt, kind = "research", world[:80], "research"
    elif "ops:" in lower or "railway" in lower or " cron" in lower or "gateway" in lower:
        lane, nxt, kind = "ops", world[:80], "ops"
    else:
        lane, nxt, kind = "code", world[:80], "code"
    if review in {"failed", "drifted"} and prior and kind not in {"financial", "accept"}:
        nxt = f"Re-do after {review}: {prior[:120]}"
        lane = "code"
    # Brain may mark Auto: yes on financial. Board policy is the gate that holds.
    auto = "no" if review in {"failed", "drifted"} or kind == "accept" else "yes"
    discuss = f"Would this be the wrong move given Review {review}?"
    if extra:
        discuss = f"{discuss} Packet saw last-labor + AUTO POLICY."
    return (
        f"Why: {world[:160]} blocks {week[:80]}\n"
        f"Horizon: {week[:160]}\n"
        f"Evidence: VERIFIED\n"
        f"Alternatives: Do not blast email; do not touch live Railway\n"
        f"Review: {review}\n"
        f"Lane: {lane}\n"
        f"Next: {nxt}\n"
        f"Auto: {auto}\n"
        f"Uncertainties: compressed month; not live GSC\n"
        f"Discuss: {discuss}\n"
    )


def _stamp(day: int, hour: int) -> str:
    d = min(max(day, 1), 28)
    return f"2026-10-{d:02d}T{hour:02d}:00:00Z"


def _apply_labor(project_id: str, day: int, allowed: bool, labor: str, prop: dict) -> str:
    if not allowed:
        return "held"
    preset = {"code": "builder", "research": "research", "ops": "ops"}.get(
        classify_proposal(prop), "builder"
    )
    if labor == "fail":
        write_job(
            {
                "id": f"{day:02d}fail",
                "at": _stamp(day, 10),
                "project_id": project_id,
                "preset": preset,
                "engine": "OpenCode" if preset == "builder" else "Hermes Agent",
                "blocker": "OpenCode binary missing",
                "text": "failed",
            }
        )
        patch_scope(project_id, None, "Blocker", "OpenCode binary missing")
        return "failed"
    write_job(
        {
            "id": f"{day:02d}okxx",
            "at": _stamp(day, 10),
            "project_id": project_id,
            "preset": preset,
            "engine": "OpenCode" if preset == "builder" else "Hermes Agent",
            "text": "done",
        }
    )
    patch_scope(project_id, None, "Last", str(prop.get("next") or "")[:160])
    patch_scope(project_id, None, "Blocker", "—")
    return "implemented"


def tick(project_id: str, day: int, world: str, labor: str) -> dict:
    patch_scope(project_id, None, "Now", world[:160])
    result = file_brain(project_id, world)
    decided = ingest_think_result(
        project_id,
        f"{HEARTBEAT_MARK} month day {day}",
        result,
        job_id=f"{day:02d}thnk",
    )
    prop = decided.get("proposal") or load_open_proposal(project_id)
    if prop:
        prop["id"] = f"prop-{project_id}-d{day:02d}"
        prop["at"] = _stamp(day, 9)
        write_proposal(project_id, prop)
        prop = load_open_proposal(project_id)
    allowed, reason = auto_labor_allowed(project_id, prop)
    outcome = _apply_labor(project_id, day, allowed, labor, prop or {})
    audit = last_labor_review(project_id)
    return {
        "day": day,
        "world": world,
        "class": classify_proposal(prop),
        "why": str((prop or {}).get("why") or "")[:160],
        "next": str((prop or {}).get("next") or "")[:160],
        "review_in": str((prop or {}).get("review") or ""),
        "auto_mark": bool((prop or {}).get("auto")),
        "allowed": allowed,
        "reason": reason,
        "labor": outcome,
        "review_out": audit.get("review"),
        "index_next": "",
    }


def seed_desk(home: Path, policy: dict | None = None) -> str:
    import openbot.bus as bus_mod
    import openbot.org as org_mod
    import openbot.store as store_mod

    org_mod.ROOT = home
    org_mod.ORG = home / "org"
    org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
    org_mod.HERMES_HOMES = home / "hermes-homes"
    bus_mod.ROOT = home
    bus_mod.ORG = home / "org"
    store_mod.ROOT = home
    store_mod.BRAINS = home / "brains"
    store_mod.JOBS = home / "jobs"
    store_mod.INDEX = store_mod.BRAINS / "INDEX.md"
    org_mod.ORG.mkdir(parents=True)
    store_mod.BRAINS.mkdir(parents=True)
    store_mod.JOBS.mkdir(parents=True)
    store_mod.INDEX.write_text("Now: month sim\nLast: —\nNext: —\nBlocker: —\n", encoding="utf-8")
    dest = org_mod.ORG / "projects" / DESK_ID
    dest.mkdir(parents=True)
    (dest / "INDEX.md").write_text(
        f"# Month desk\n\nNow: ready\nLast: —\nNext: —\nBlocker: —\nHorizon-week: {WEEK}\n",
        encoding="utf-8",
    )
    org_mod.PROFILE_PATH.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "id": DESK_ID,
                        "name": "Month desk",
                        "role": "ceo",
                        "folder": str(home / "work"),
                        "workers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (home / "work").mkdir(exist_ok=True)
    mix = policy if isinstance(policy, dict) else recommended_auto_policy()
    patch_project_tools(DESK_ID, {"auto_policy": mix})
    return DESK_ID


def run_month(days: int = 22, policy: dict | None = None) -> dict:
    """Run weekday ticks on an isolated desk. Never live SAA."""
    import openbot.bus as bus_mod
    import openbot.org as org_mod
    import openbot.store as store_mod

    days = max(1, min(int(days), len(MONTH)))
    tmp = tempfile.TemporaryDirectory()
    home = Path(tmp.name)
    saved = {
        "org_root": org_mod.ROOT,
        "org": org_mod.ORG,
        "profile": org_mod.PROFILE_PATH,
        "homes": org_mod.HERMES_HOMES,
        "bus_org": bus_mod.ORG,
        "bus_root": bus_mod.ROOT,
        "store_root": store_mod.ROOT,
        "brains": store_mod.BRAINS,
        "jobs": store_mod.JOBS,
        "index": store_mod.INDEX,
    }
    try:
        pid = seed_desk(home, policy)
        rows = []
        for i, spec in enumerate(MONTH[:days], start=1):
            row = tick(pid, i, spec["world"], spec["labor"])
            try:
                row["index_next"] = index_field(read_project_index(pid), "Next")
            except Exception:
                row["index_next"] = ""
            rows.append(row)
        auto_n = sum(1 for row in rows if row["allowed"])
        hold_n = sum(1 for row in rows if not row["allowed"])
        fail_n = sum(1 for row in rows if row["labor"] == "failed")
        classes = {row["class"] for row in rows}
        return {
            "ok": True,
            "days": days,
            "desk": pid,
            "auto": auto_n,
            "held": hold_n,
            "failed": fail_n,
            "classes": sorted(classes),
            "rows": rows,
        }
    finally:
        org_mod.ROOT = saved["org_root"]
        org_mod.ORG = saved["org"]
        org_mod.PROFILE_PATH = saved["profile"]
        org_mod.HERMES_HOMES = saved["homes"]
        bus_mod.ORG = saved["bus_org"]
        bus_mod.ROOT = saved["bus_root"]
        store_mod.ROOT = saved["store_root"]
        store_mod.BRAINS = saved["brains"]
        store_mod.JOBS = saved["jobs"]
        store_mod.INDEX = saved["index"]
        tmp.cleanup()


def format_month(report: dict) -> str:
    lines = [
        f"Compressed month · {report.get('days')} weekdays · desk {report.get('desk')}",
        f"Auto {report.get('auto')} · held {report.get('held')} · failed labor {report.get('failed')}",
        f"Classes: {', '.join(report.get('classes') or [])}",
        "",
    ]
    for row in report.get("rows") or []:
        gate = "AUTO" if row.get("allowed") else "NOTIFY"
        lines.append(
            f"D{row['day']:02d} {gate:6} {row.get('class') or '?':10} "
            f"{row.get('labor') or '':11} {str(row.get('next') or '')[:72]}"
        )
        lines.append(f"     why: {str(row.get('why') or '')[:88]}")
        if not row.get("allowed"):
            lines.append(f"     gate: {row.get('reason')}")
    return "\n".join(lines)


def main() -> int:
    report = run_month(22)
    print(format_month(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
