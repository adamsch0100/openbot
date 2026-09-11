"""Founding INDEX + Horizon steers. Chat is the pipe. INDEX is memory."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .org import (
    CEO_PRETTY_NAMES,
    HORIZON_KEYS,
    _project_dir,
    _slug,
    horizon_filled,
    list_projects,
    parse_horizons,
    write_project_horizons,
)
from .store import now_iso

HORIZON_SHAPE = "{money or count} · {who pays} · via {how they arrive} · proof {metric}"
FOUNDING_MARK = "FOUNDING_TASK"
HORIZON_ALIASES = {
    "week": ("Horizon-week", "1 week", "1-week", "Week", "This week"),
    "month": ("Horizon-month", "1 month", "1-month", "Month", "This month"),
    "quarter": ("Horizon-quarter", "3 months", "3-month", "Quarter"),
    "half": ("Horizon-half", "6 months", "6-month", "Half"),
    "year": ("Horizon-year", "1 year", "1-year", "Year"),
    "five": ("Horizon-five", "5 years", "5-year", "Five years", "Five"),
}
STEER_RE = re.compile(
    r"(?i)\b("
    r"founding_task|steer:|goals? board|"
    r"1[\s-]?week goal|1[\s-]?month goal|1[\s-]?year goal|"
    r"pay for (the )?seat|customer acquisition|unit economics|"
    r"rewrite (the )?horizons|re-?do the goals|"
    r"horizon-(?:week|month|quarter|half|year|five)"
    r")\b"
)
TELL_RE = re.compile(
    r"(?is)^(?:tell|ask|send(?:\s+this)?\s+to|route(?:\s+this)?\s+to)\s+"
    r"(?:the\s+)?(?P<who>saa(?:\s*homes)?|listlogic|nadia|ottobot|openbot|support|pmill)"
    r"(?:'s)?(?:\s+ceo)?\s*[:\-,]\s*(?P<body>.+)$"
)
WHO_TO_ID = {
    "saa": "saa-homes",
    "saa homes": "saa-homes",
    "saahomes": "saa-homes",
    "listlogic": "listlogic",
    "nadia": "nadia",
    "ottobot": "openbot",
    "openbot": "openbot",
    "support": "support",
    "pmill": "pmill",
}

KNOWN_HORIZONS = {
    "saa-homes": {
        "week": "1 live city or CHFA page that can take a lead · NoCO buyer/seller · via organic area + program URLs · proof live URL + contact form HTTP 200",
        "month": "8+ qualified inquiries (form / CHFA / market report) · NoCO ready-to-act · via organic city + CHFA/Champions pages · proof form submits + GSC clicks on money URLs",
        "quarter": "Top-8 on named Tier S {city} realtor / homes for sale queries · NoCO searchers · via city pages + internal links · proof GSC position not paid ads",
        "half": "Organic + local pack covering Hermes/OpenCode spend · NoCO · via SEO (GBP login still skip+note) · proof Maps/GSC vs token spend",
        "year": "Organic covers the SAA Hermes seat then profit · NoCO buy/sell · via search ownership not paid · proof leads/week vs seat cost",
        "five": "Schwartz and Associates is the name NoCO already trusts to buy or sell · via compounding local search · proof branded queries + inbound",
    },
    "openbot": {
        "week": "1 paying tenant on a live CEO desk · operators who will pay · via hosted OttoBot wrapping Hermes + OpenCode · proof tenant login + isolated INDEX",
        "month": "Paid board seats (engines billed to the tenant) · companies who want CEOs without running glue · via signup · proof paid seats vs churn",
        "quarter": "Multi-tenant isolation — INDEX, Hermes home, OpenCode folder per company · tenants · via product · proof tenant A cannot see tenant B",
        "half": "Seat MRR covers OttoBot's own Hermes + OpenCode · tenants · via subscriptions · proof revenue vs token spend",
        "year": "OttoBot is the paid board companies run from · tenants · via CEOs + engines that stay theirs · proof paying tenants with live Horizons",
        "five": "The wrapper that gets paid for Hermes Agent + OpenCode · via multi-tenant seats · proof P&L",
    },
    "support": {
        "week": "Every ask is a ticket file · Adam · via Support CEO · proof no silent Accept / send / announce",
        "month": "Working-on board matches ticket phase · operators · via INDEX four-liners · proof Now/Last/Next honest",
        "quarter": "Help other people can clone · operators · via tickets not chat memory · proof a stranger can file and see status",
        "half": "Support pays for itself by making OttoBot delightful · seat cost · via fewer owner interrupts · proof Accept-only gates hold",
        "year": "Help stays a CEO, not a chatbot · operators · via files · proof tickets still route to openbot Builder",
        "five": "Transparent help · people who clone · via Working-on + Accept · proof Support never ships live",
    },
    "listlogic": {
        "week": "Live ListLogic Hermes replica Online (today: deploys removed — Adam gate) · listing agents · via product not city SEO · proof Railway replica before labor",
        "month": "Paid activations (trial → $39/mo) covering Hermes/OpenCode · listing agents · via FUB-group help then one plug · proof activations vs spend",
        "quarter": "A conversion path that covers the seat · agents who price listings · via ListLogic.homes · proof paid activations",
        "half": "ListLogic is the pricing story agents use with sellers · via product + drafts (never auto-post) · proof parked Needs-you not browser posts",
        "year": "Paid activations cover the seat first, then profit · listing agents · via product · proof revenue vs token spend",
        "five": "The listing-price company that pays for itself · via one CEO not a C-suite · proof P&L on INDEX",
    },
    "nadia": {
        "week": "Conversion Hermes stays Online; SMS never claims Adam · ISA tenants · via follow-up that books · proof no impersonation",
        "month": "Paid seats ($79/1, $149/5, $279/6+) covering spend · brokerages · via ISA outcomes, SAA as dogfood · proof seats vs token spend",
        "quarter": "ISA that books without sounding like a landing page · FUB users · via Adam-voice drafts in groups, Nadia-voice to leads · proof parked Needs-you",
        "half": "Nadia is the ISA layer brokerages pay for · via seats not ads · proof paid seats",
        "year": "Seats cover Hermes/OpenCode; voice calling still off until Adam says · via product · proof spend vs seats",
        "five": "The ISA company that pays for itself · via one CEO · proof P&L on INDEX",
    },
}


def is_founding_message(message: str) -> bool:
    return FOUNDING_MARK in (message or "")


def is_steer_message(message: str) -> bool:
    raw = str(message or "")
    if is_founding_message(raw):
        return False
    return bool(STEER_RE.search(raw))


def resolve_tell_target(message: str) -> tuple[str, str] | None:
    match = TELL_RE.match((message or "").strip())
    if not match:
        return None
    who = re.sub(r"\s+", " ", match.group("who") or "").strip().lower()
    body = (match.group("body") or "").strip()
    pid = WHO_TO_ID.get(who)
    if not pid or not body:
        return None
    live = {str(row.get("id") or "") for row in list_projects()}
    if pid not in live and pid not in {"openbot", "support"}:
        return None
    return pid, body


def founding_prompt(*, name: str, idea: str = "", site: str = "", goals: str = "") -> str:
    who = (name or "this company").strip() or "this company"
    idea_line = (idea or goals or "pay for this seat first, then profit").strip()
    site_line = f"Site: {site}\n" if site else ""
    return (
        f"{FOUNDING_MARK}\n"
        f"You are founding {who}. The operator will Accept before Horizons go live. "
        "Do not write INDEX.md. Do not invent a CFO or COO bot. "
        "Spin Code/Think/Research/Ops or one named worker only if a jam already repeats.\n\n"
        f"{site_line}"
        f"Operator Goal (source of truth for what they want this CEO to produce): {idea_line}\n"
        "Turn that Goal into six Horizon lines. Paid products and multi-tenant seats are allowed. "
        "Do not assume a free clone or supporter-only model unless they said that.\n\n"
        "Output exactly these labels, one line each, shape "
        f"`{HORIZON_SHAPE}`:\n"
        "Offer: what they buy and the price (who is not a customer)\n"
        "Who: one buyer, one job-to-be-done\n"
        "How: how they find us (SEO, outbound, product, sales)\n"
        "Proof: the metric we will look at\n"
        "Never: brand / legal / auto-post / Adam gates\n"
        "Horizon-week:\n"
        "Horizon-month:\n"
        "Horizon-quarter:\n"
        "Horizon-half:\n"
        "Horizon-year:\n"
        "Horizon-five:\n"
        "Lanes: which specialist lanes to open this month (not C-suite titles)\n"
        "Next: one shippable thing this week\n"
    )


def founding_intent(project_id: str | None) -> dict[str, str]:
    """Operator Goal + site saved at Add CEO, else INDEX Goals / tools."""
    pid = _slug(project_id) if project_id else ""
    blob = load_founding(pid) if pid else {}
    idea = str(blob.get("idea") or blob.get("goals") or "").strip()
    site = str(blob.get("site") or "").strip()
    if pid:
        from .org import index_field, project_tools, read_project_index

        text = read_project_index(pid)
        if not idea:
            idea = index_field(text, "Goals")
            if not horizon_filled(idea):
                idea = ""
        if not idea:
            from .org import horizon_week

            idea = horizon_week(text)
        if not site:
            tools = project_tools(pid) or {}
            site = str(tools.get("site_url") or "").strip()
    return {"idea": idea, "site": site, "goals": idea}


def founding_display(name: str, idea: str = "") -> str:
    who = (name or "this CEO").strip() or "this CEO"
    want = re.sub(r"\s+", " ", (idea or "").strip())[:80]
    if want:
        return f"Ask {who} to propose Goals from: {want}"
    return f"Ask {who} to propose Goals from what you want"


def founding_prompt_for(project_id: str | None) -> str:
    pid = _slug(project_id) if project_id else ""
    name = CEO_PRETTY_NAMES.get(pid, pid or "this company")
    if pid:
        for row in list_projects():
            if str(row.get("id") or "") == pid:
                name = str(row.get("name") or name)
                break
    intent = founding_intent(pid)
    return founding_prompt(name=name, idea=intent["idea"], site=intent["site"], goals=intent["goals"])


def horizon_packet_extra(project_id: str | None, message: str = "") -> str:
    if not project_id:
        return ""
    from .org import read_project_index

    text = read_project_index(project_id)
    parsed = parse_horizons(text)
    lines = [f"HORIZONS (labor serves these). Shape: {HORIZON_SHAPE}"]
    for key, label in HORIZON_KEYS:
        val = parsed.get(key) or "—"
        lines.append(f"{label}: {val}")
    draft = load_founding(project_id)
    status = str((draft or {}).get("status") or "")
    if status == "needed":
        lines.append("FOUNDING: Horizons are not live until the operator Accepts a founding RESULT.")
    if is_founding_message(message):
        lines.append(
            "FOUNDING LAW: Output Offer/Who/How/Proof/Never and Horizon-* lines. "
            "Do not write INDEX. The board parks Accept."
        )
    elif is_steer_message(message):
        lines.append(
            "STEER LAW: The operator is steering this company. "
            "Output the six Horizon-* lines in the RESULT (full set, same shape). "
            "Do not rewrite Never/gates. Do not write INDEX — the board will."
        )
    return "\n".join(lines)


def extract_labeled(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", text or "", re.M)
    return (match.group(1).strip() if match else "")[:280]


def extract_horizons_from_text(text: str) -> dict[str, str]:
    parsed = parse_horizons(text or "")
    out = {key: val for key, val in parsed.items() if horizon_filled(val)}
    blob = text or ""
    for key, aliases in HORIZON_ALIASES.items():
        if key in out:
            continue
        for alias in aliases:
            match = re.search(rf"^\**{re.escape(alias)}:\**\s*(.*)$", blob, re.M | re.I)
            if not match:
                continue
            val = (match.group(1) or "").strip().strip("*").strip()
            if horizon_filled(val):
                out[key] = val[:280]
                break
    return out


def _founding_path(project_id: str) -> Path:
    return _project_dir(_slug(project_id)) / "founding.json"


def load_founding(project_id: str | None) -> dict:
    if not project_id:
        return {}
    path = _founding_path(project_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_founding(project_id: str, data: dict) -> dict:
    pid = _slug(project_id)
    path = _founding_path(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(data)
    blob["project_id"] = pid
    blob["at"] = now_iso()
    path.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
    return blob


def mark_founding_needed(project_id: str, *, idea: str = "", site: str = "", goals: str = "") -> dict:
    prev = load_founding(project_id)
    prev["status"] = "needed"
    want = (idea or goals or "").strip()
    if want:
        prev["idea"] = want[:400]
        prev["goals"] = want[:400]
    if (site or "").strip():
        prev["site"] = str(site).strip()[:240]
    return save_founding(project_id, prev)


def mark_founding_accepted(project_id: str) -> dict:
    prev = load_founding(project_id)
    prev["status"] = "accepted"
    return save_founding(project_id, prev)


def park_founding_draft(project_id: str, result: str) -> dict:
    horizons = extract_horizons_from_text(result)
    draft = {
        "status": "draft",
        "horizons": horizons,
        "offer": extract_labeled(result, "Offer"),
        "who": extract_labeled(result, "Who"),
        "how": extract_labeled(result, "How"),
        "proof": extract_labeled(result, "Proof"),
        "never": extract_labeled(result, "Never"),
        "lanes": extract_labeled(result, "Lanes"),
        "next": extract_labeled(result, "Next"),
        "raw": (result or "")[:4000],
    }
    return save_founding(project_id, draft)


def accept_founding(project_id: str) -> dict:
    pid = _slug(project_id)
    draft = load_founding(pid)
    horizons = draft.get("horizons") if isinstance(draft.get("horizons"), dict) else {}
    if sum(1 for v in horizons.values() if horizon_filled(str(v or ""))) < 3:
        raise ValueError("founding draft needs at least 3 Horizon lines")
    written = write_project_horizons(pid, horizons, notify=True)
    from .org import patch_file_index, read_project_index

    path = _project_dir(pid) / "INDEX.md"
    extra = []
    for label in ("Offer", "Who", "How", "Proof", "Never"):
        val = str(draft.get(label.lower()) or "").strip()
        if val:
            extra.append(f"{label}: {val}")
            patch_file_index(path, label, val)
    nxt = str(draft.get("next") or "").strip()
    if nxt:
        patch_file_index(path, "Next", nxt)
    mark_founding_accepted(pid)
    written["founding"] = load_founding(pid)
    written["index"] = read_project_index(pid)
    return written


def reject_founding(project_id: str, reason: str = "") -> dict:
    pid = _slug(project_id)
    prev = load_founding(pid)
    prev["status"] = "needed"
    prev["horizons"] = {}
    saved = save_founding(pid, prev)
    try:
        from .memory import teach_from_founding

        teach_from_founding(pid, accepted=False, reason=reason)
    except Exception:
        pass
    return saved


def ingest_ceo_result(project_id: str | None, message: str, result: str) -> dict:
    """After Think: park founding Accept, or apply a steer to Horizons."""
    if not project_id:
        return {}
    pid = _slug(project_id)
    if is_founding_message(message):
        return park_founding_draft(pid, result)
    if is_steer_message(message):
        horizons = extract_horizons_from_text(result)
        if len(horizons) < 3:
            return {"status": "steer-incomplete", "horizons": horizons}
        return write_project_horizons(pid, _merge_steer(pid, horizons), notify=True)
    return {}


def _merge_steer(project_id: str, incoming: dict) -> dict:
    from .org import read_project_index

    current = parse_horizons(read_project_index(project_id))
    for key, _label in HORIZON_KEYS:
        if incoming.get(key):
            current[key] = incoming[key]
    return current


def apply_known_horizons(project_id: str, *, notify: bool = False) -> dict | None:
    pid = _slug(project_id)
    blob = KNOWN_HORIZONS.get(pid)
    if not blob:
        return None
    result = write_project_horizons(pid, blob, notify=notify)
    mark_founding_accepted(pid)
    return result


def seed_seated_horizons(*, notify: bool = False) -> list[str]:
    done = []
    for row in list_projects():
        pid = str(row.get("id") or "")
        if pid in KNOWN_HORIZONS:
            apply_known_horizons(pid, notify=notify)
            done.append(pid)
    for pid in KNOWN_HORIZONS:
        if pid not in done:
            path = _project_dir(pid) / "INDEX.md"
            if path.is_file():
                apply_known_horizons(pid, notify=False)
                done.append(pid)
    return done


def _write_cos_inbox(project_id: str, body: str) -> None:
    """Ticket only. Cos never patches that CEO's INDEX."""
    path = _project_dir(_slug(project_id)) / "inbox.md"
    snippet = re.sub(r"\s+", " ", (body or "").strip())[:400]
    block = (
        f"## {now_iso()}\n"
        "Now: queued\n"
        f"Last: Cos steer: {snippet}\n"
        "Next: This CEO owns Horizons. Cos does not write INDEX.\n"
        "Blocker: —\n\n"
    )
    prev = path.read_text(encoding="utf-8") if path.is_file() else "# Inbox\n\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prev + block, encoding="utf-8")


def route_cos_to_ceo(message: str) -> str | None:
    """Cos chairs. Write inbox + handoff. Do not rewrite that CEO INDEX."""
    hit = resolve_tell_target(message)
    if not hit:
        return None
    pid, body = hit
    _write_cos_inbox(pid, body)
    try:
        from .bus import create_handoff

        create_handoff(
            task=body,
            project_id=pid,
            from_seat="cos",
            to_seat="ceo",
            next_owner=pid,
            output="Operator steer via Cos. CEO owns Horizons / Next. Do not rewrite INDEX from Cos.",
        )
    except Exception:
        pass
    who = CEO_PRETTY_NAMES.get(pid, pid)
    return (
        f"Routed to {who}. It's in that CEO's inbox as a ticket — Cos does not write their INDEX. "
        f"Open {who} and talk, or they'll pick it up as TICKET. Steer: {body[:180]}"
    )


def founding_public(project_id: str | None) -> dict:
    blob = load_founding(project_id)
    status = str(blob.get("status") or "")
    return {
        "status": status or "",
        "offer": str(blob.get("offer") or "")[:160],
        "changed": list((blob.get("horizons") or {}).keys()) if status == "draft" else [],
    }
