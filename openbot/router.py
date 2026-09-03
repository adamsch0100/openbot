"""Dumb router. Four presets. No third runtime."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .config import load_config, load_settings
from .detect import detect
from .gitutil import diff_against_head, new_untracked, restore_snapshot, snapshot
from .hermes import chat as hermes_chat
from .hermes import chat_packet, cron_create, job_packet, parse_schedule, split_model
from .keyring import (
    LOGIN_FILE,
    activate_account,
    activate_for_engine,
    mark_wallet_empty,
    ordered_accounts,
    public_logins,
    redact_chat_login,
    stage_job_logins,
    staged_logins_ready,
    wallet_marked_empty,
)
from .models import cheap_chat_for_provider, hermes_chat_model_for_provider, model_provider, recommended_chat_id
from .auto import seated_or_auto
from .pickers import SKIP_HERMES_PROVIDERS
from .providers import nous_portal_connected
from .ops import write_ops_ticket
from .bus import (
    classify_gate,
    close_work_job,
    cos_file_reply,
    law_extra,
    log_approval,
)
from .org import (
    add_schedule,
    ensure_ceo_engines,
    inbox_tail,
    index_field,
    node_label,
    patch_project_tools,
    patch_scope,
    project_tools,
    read_project_index,
    read_worker_brain,
    rollup_staff,
    session_name,
    staff_briefing,
    staff_status_reply,
    wiring_brief,
    work_target,
    write_project_inbox,
)
from .threadstore import search_quote, thread_key, wants_quote
from .research import fetch_page, first_url
from .store import (
    list_jobs,
    now_iso,
    read_brain,
    read_index,
    read_job,
    spend_summary,
    update_job,
    write_job,
)
from .usage import parse_opencode_events

STATUS = re.compile(
    r"\b(what('?s| is) (going on|blocked|the status)|status|blocked|index)\b",
    re.I,
)
CODE = re.compile(
    r"\b(diff|commit|refactor|implement|fix|pr\b|pull request|opencode|change the code|"
    r"(create|write|add)\b.{0,48}\b(\.md|md file|markdown))\b",
    re.I,
)
URL = re.compile(r"https?://", re.I)
CRON = re.compile(r"\b(every morning|every day|schedule|cron|remind|watch this)\b", re.I)
THINK = re.compile(r"\b(think hard|reason (about|through)|make a plan|deep think)\b", re.I)
LOOK = re.compile(r"\b(look at this site|open (the )?browser)\b", re.I)
BROWSER_LOGIN = re.compile(
    r"\b(browser\s+login|login\s+(to\s+)?(the\s+)?browser|site\s+login|vault\s+login|"
    r"cookies?\s+for\s+(facebook|fb|chrome)|did\s+the\s+browser\s+login|"
    r"whatever you need for the browser)\b",
    re.I,
)
PROGRAM = re.compile(
    r"\b(\d{1,3})\s+tasks?\b|\balways\b.{0,48}\bimprov|\bbuild (me )?(a )?full\b",
    re.I,
)
GREET = re.compile(
    r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|good (morning|afternoon|evening))\b",
    re.I,
)
THANKS = re.compile(r"^\s*(thanks|thank you)\b", re.I)
SKILL = re.compile(
    r"\b(add|install|enable|turn on|list|what|which|how).{0,48}\bskills?\b|"
    r"\bskills?\b.{0,40}\b(add|install|settings|available)\b",
    re.I,
)
WALLET_EMPTY = re.compile(
    r"insufficient balance|opencode\.ai/.*/billing",
    re.I,
)
PRESETS = {"cos", "builder", "research", "ops", "think"}
LANE_LABEL = {
    "cos": "Chat",
    "think": "Think",
    "builder": "Code",
    "research": "Research",
    "ops": "Ops",
}
OPENCODE_TIMEOUT = 600
DEFAULT_CODE_MODEL = "opencode/deepseek-v4-flash"
OPENROUTER_CODE_MODEL = "openrouter/deepseek/deepseek-v4-flash-0731"


def classify(message: str) -> str:
    if STATUS.search(message):
        return "cos"
    if CRON.search(message):
        return "ops"
    if URL.search(message) or LOOK.search(message):
        return "research"
    if CODE.search(message):
        return "builder"
    if THINK.search(message):
        return "think"
    return "cos"


def route_plan(message: str, requested: str | None) -> list[str]:
    if requested in PRESETS:
        return [requested]
    needs_code = bool(CODE.search(message))
    needs_web = bool(URL.search(message) or LOOK.search(message))
    needs_cron = bool(CRON.search(message))
    steps: list[str] = []
    if needs_web:
        steps.append("research")
    if needs_code:
        steps.append("builder")
    if needs_cron:
        steps.append("ops")
    if steps:
        return steps
    return [classify(message)]


def _call_progress(on_progress, text: str, lane: str | None = None) -> None:
    if not on_progress:
        return
    try:
        on_progress(text, lane)
    except TypeError:
        on_progress(text)


def resolve_preset(message: str, requested: str | None) -> str:
    if requested in PRESETS:
        return requested
    return classify(message)


def _prefer_accounts(tools: dict | None) -> list[str]:
    prefer = []
    blob = tools or {}
    account_id = str(blob.get("account_id") or "").strip()
    if not account_id:
        account_id = str(load_settings().get("profile_account_id") or "").strip()
    if account_id:
        prefer.append(account_id)
    for item in blob.get("fallback") or []:
        value = str(item or "").strip()
        if value:
            prefer.append(value)
    return prefer


def _activate(engine: str, tools: dict | None, model: str | None = None) -> str | None:
    provider = model_provider(model) or None
    if provider == "opencode-zen":
        provider = "opencode"
    return activate_for_engine(engine, prefer=_prefer_accounts(tools), provider=provider or None)


def _live_accounts(rows: list[dict]) -> list[dict]:
    live = [row for row in rows if not wallet_marked_empty(str(row.get("id") or ""))]
    return live or rows


def _hermes_talk_model(seated_model: str | None, provider: str) -> str | None:
    """Chat talk runs on Hermes CLI. Never hand it OpenCode Muse / Zen seat IDs."""
    seated = str(seated_model or "").strip()
    seated_provider = model_provider(seated) if seated else ""
    if provider in SKIP_HERMES_PROVIDERS:
        return None
    if seated and seated_provider == provider and seated_provider not in SKIP_HERMES_PROVIDERS:
        low = seated.lower()
        if "muse-spark" in low or "contributor-free" in low:
            return hermes_chat_model_for_provider(provider) or None
        return seated
    return hermes_chat_model_for_provider(provider) or None


def _chat_attempts(tools: dict | None, seated_model: str | None) -> list[tuple[dict, str]]:
    """Walk Hermes-capable wallets. OpenCode Go keys are for Code, not Cos talk."""
    attempts: list[tuple[dict, str]] = []
    seen: set[tuple[str, str]] = set()
    rows = _live_accounts(list(ordered_accounts(prefer=_prefer_accounts(tools), engine="Hermes Agent")))
    seated_provider = model_provider(seated_model) if seated_model else ""
    if seated_provider == "nous":
        nous_rows = [row for row in rows if str(row.get("provider") or "") == "nous"]
        rest = [row for row in rows if str(row.get("provider") or "") != "nous"]
        if not nous_rows and nous_portal_connected():
            nous_rows = [{"id": "", "provider": "nous"}]
        rows = nous_rows + rest
    preferred = [row for row in rows if str(row.get("provider") or "") not in SKIP_HERMES_PROVIDERS]
    if preferred:
        rows = preferred
    for row in rows:
        provider = str(row.get("provider") or "")
        model = _hermes_talk_model(seated_model, provider)
        if not model:
            continue
        key = (str(row.get("id") or ""), model)
        if key in seen:
            continue
        seen.add(key)
        attempts.append((row, model))
    if not attempts:
        for provider in ("nous", "openrouter", "anthropic", "openai"):
            model = hermes_chat_model_for_provider(provider) or None
            if not model:
                continue
            attempts.append(({}, model))
            break
    return attempts


def _cos_chat_fallback(project_id: str | None, worker_id: str | None, message: str, why: str) -> str:
    """Cos is files-first. Never leave the operator with only 'send it again'."""
    if project_id:
        brief = status_reply(
            read_project_index(project_id) if project_id else read_index(),
            message,
            node_label(project_id, worker_id) or "Chief of Staff",
            wiring=wiring_brief(project_id),
        )
    else:
        brief = staff_status_reply()
    tip = (why or "").strip()
    if tip:
        return f"{brief}\n\n({tip})"
    return brief


def _code_model_for_provider(provider: str, seated_model: str | None) -> str:
    seated_provider = model_provider(seated_model) if seated_model else ""
    if seated_model and seated_provider == provider:
        return seated_model
    if provider == "opencode":
        if seated_provider in {"opencode", "opencode-zen"} and seated_model:
            return seated_model
        return DEFAULT_CODE_MODEL
    if provider == "openrouter":
        return cheap_chat_for_provider("openrouter") or OPENROUTER_CODE_MODEL
    return cheap_chat_for_provider(provider)


def _code_attempts(tools: dict | None, seated_model: str | None) -> list[tuple[dict, str]]:
    """OpenCode keys in keyring order, then OpenRouter. Do not jump OpenRouter ahead of a live Go key."""
    attempts: list[tuple[dict, str]] = []
    seen: set[tuple[str, str]] = set()
    rows = _live_accounts(list(ordered_accounts(prefer=_prefer_accounts(tools), engine="OpenCode")))
    for row in rows:
        provider = str(row.get("provider") or "")
        model = _code_model_for_provider(provider, seated_model)
        if not model:
            continue
        key = (str(row.get("id") or ""), model)
        if key in seen:
            continue
        seen.add(key)
        attempts.append((row, model))
    return attempts


def _quiet_delta(on_delta):
    if on_delta is None:
        return None

    def wrapped(chunk: str) -> None:
        if wallet_empty(chunk):
            return
        on_delta(chunk)

    return wrapped


def wallet_empty(text: str) -> bool:
    return bool(WALLET_EMPTY.search(text or ""))


def wallet_empty_reply() -> str:
    return (
        "That OpenCode workspace is out of included Go quota and Zen balance. "
        "The other OpenCode keys, then OpenRouter, were already tried in keyring order. "
        "Top up any of those wallets from Keys, or pick a Chat model on a provider that still has credit. "
        "Do not paste keys here."
    )


def cos_browser_login_reply() -> str:
    return (
        "Cos has no browser. Site logins stay in the board vault — never paste cookies or passwords into chat.\n"
        "1. You → Keys → Site logins — add facebook.com (or the site) with user/pass there.\n"
        "2. Open the CEO that owns the work (Nadia), pin Research or Think.\n"
        "3. Ask that CEO to open the group; if a login wall hits, Approve the vault login on the card.\n"
        "I cannot see whether a browser login already worked from this Staff chat — check the CEO thread "
        "or the last Research/Think card for a login wall vs success."
    )


def clean_hermes_fail_hint(ran: dict | None) -> str:
    blob = ran or {}
    code = blob.get("code")
    raw = str(blob.get("text") or "").strip()
    if code == 127:
        return "Hermes Agent binary missing on this box — answered from the brief."
    if code == 2:
        return "Chat needs a Hermes-capable model (OpenRouter/Nous). Muse Spark is OpenCode-only."
    if code == 124:
        return "Hermes chat timed out — answered from the brief."
    if raw and raw not in {"(no output)", "Stopped.", "hermes timed out"} and len(raw) < 240:
        return f"Hermes chat failed ({code}): {raw}"
    return f"Hermes chat exited {code} — answered from the brief."


def _work_folder(folder: str | None, project_id: str | None = None) -> str:
    from .org import ensure_project_workspace, is_board_folder, is_primary_project

    raw = str(folder or "").strip()
    if project_id and not is_primary_project(project_id):
        if not raw or is_board_folder(raw):
            return ensure_project_workspace(project_id)
        return str(Path(raw).expanduser())
    if raw:
        return str(Path(raw).expanduser())
    cfg = load_config()
    if cfg["work_dir_ok"]:
        return cfg["work_dir"]
    return str(Path.cwd())


def run_opencode(
    folder: str,
    prompt: str,
    binary: str | None = None,
    model: str | None = None,
    on_delta=None,
    cancel: threading.Event | None = None,
    run_id: str | None = None,
    mcp_github: bool = False,
    on_progress=None,
) -> tuple[int, str]:
    exe = binary or "opencode"
    cmd = [exe, "run", "--format", "json", "--auto", "--dir", folder]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    env = os.environ.copy()
    if mcp_github:
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            {
                "mcp": {
                    "github": {
                        "type": "remote",
                        "url": "https://api.githubcopilot.com/mcp/",
                        "enabled": True,
                        "oauth": True,
                    }
                }
            }
        )
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": env,
        "bufsize": 1,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError:
        return 127, "opencode not on PATH"
    if run_id:
        from .live import attach

        attach(run_id, proc)
    chunks: list[str] = []
    deadline = time.time() + OPENCODE_TIMEOUT
    try:
        while True:
            if cancel is not None and cancel.is_set():
                proc.terminate()
                return 130, "".join(chunks)[-24000:] or "Stopped."
            if time.time() > deadline:
                proc.kill()
                return 124, "opencode run timed out"
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                chunks.append(line)
                if on_delta:
                    try:
                        event = json.loads(line)
                        part = event.get("part") if isinstance(event, dict) else None
                        text = ""
                        if isinstance(part, dict):
                            text = str(part.get("text") or "")
                        if not text and isinstance(event, dict) and event.get("type") == "error":
                            from .usage import error_message

                            text = error_message(event)
                        if text:
                            on_delta(text)
                        if on_progress and isinstance(event, dict):
                            etype = str(event.get("type") or "")
                            part_type = str((part or {}).get("type") or "") if isinstance(part, dict) else ""
                            name = ""
                            if isinstance(part, dict):
                                name = str(part.get("name") or part.get("tool") or "").strip()
                            if etype in {"step_start", "tool_use"} or part_type in {"step-start", "tool-start", "tool"}:
                                try:
                                    _call_progress(
                                        on_progress,
                                        f"OpenCode · {name or part_type or etype}",
                                        "builder",
                                    )
                                except Exception:
                                    pass
                    except json.JSONDecodeError:
                        if "set-cookie" not in line.lower():
                            on_delta(line)
                continue
            if proc.poll() is not None:
                rest = proc.stdout.read() if proc.stdout else ""
                if rest:
                    chunks.append(rest)
                break
            time.sleep(0.05)
        out = "".join(chunks)
        unknown = proc.returncode != 0 and re.search(r"unknown|unexpected argument", out, re.I)
        if unknown:
            proc2 = subprocess.run(
                [exe, "run", prompt],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=OPENCODE_TIMEOUT,
                check=False,
                env=env,
            )
            out = (proc2.stdout or "") + (("\n" + proc2.stderr) if proc2.stderr else "")
            return proc2.returncode, out[-24000:]
        return proc.returncode or 0, out[-24000:]
    except subprocess.TimeoutExpired:
        return 124, "opencode run timed out"


def _receipt_base(job_id: str, preset: str, engine: str, message: str, folder: str | None) -> dict:
    cfg = load_config()
    spend = spend_summary(cfg["spend_cap_usd"], cfg["spend_cap_period"])
    return {
        "id": job_id,
        "at": now_iso(),
        "preset": preset,
        "engine": engine,
        "model": "none" if engine == "board" else "engine-default",
        "prompt_tokens": 0,
        "cached_tokens": 0,
        "output_tokens": 0,
        "tools_on": preset in {"builder", "research", "ops"},
        "usd_estimate": 0.0,
        "cap_remaining": spend["cap_remaining"],
        "message": redact_chat_login(message),
        "folder": folder,
        "blocker": None,
        "diff": "",
        "untracked": [],
        "diff_pending": False,
        "accepted": None,
        "rejected": False,
        "git_snapshot": None,
        "brain_excerpt": read_brain(preset if preset != "ask" else "cos")[:400],
    }


def last_results(limit: int = 3, project_id: str | None = None) -> str:
    from .store import list_jobs

    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    if project_id:
        jobs = [job for job in jobs if job.get("project_id") == project_id]
    lines: list[str] = []
    for job in jobs[:limit]:
        snippet = re.sub(r"\s+", " ", str(job.get("text") or ""))[:180]
        who = job.get("worker_id") or job.get("project_id") or "staff"
        lines.append(f"{who} · {job.get('engine')} {job.get('id')}: {snippet}")
    return "\n".join(lines)


def _index_last(text: str, *, failed: bool = False) -> str:
    """INDEX Last is a recoverable snippet. Job ids live in jobs/, not as memory."""
    snippet = re.sub(r"\s+", " ", (text or "").strip())[:160] or "—"
    if failed:
        return f"failed: {snippet}"
    return snippet


def _packet_extra(
    project_id: str | None,
    extra: str = "",
    quote: str = "",
    preset: str = "cos",
    worker_id: str | None = None,
    hermes_home: str | None = None,
) -> str:
    bits: list[str] = []
    wire = wiring_brief(project_id)
    if wire:
        bits.append(f"CHIEF OF STAFF:\n{wire}")
    if quote:
        bits.append(f"QUOTE (local thread, one snippet, not a replay):\n{quote}")
    hints = last_results(project_id=project_id)
    if hints:
        bits.append(f"HINTS:\n{hints}")
    ticket = inbox_tail(project_id)
    if ticket:
        bits.append(f"TICKET:\n{ticket}")
    if extra:
        bits.append(extra.strip())
    if preset in {"think", "research", "ops"} and hermes_home:
        staged = stage_job_logins(project_id, hermes_home, only_auto=True)
        if staged:
            bits.append(
                "VAULT LOGINS:\n"
                f"Approved site usernames and passwords for this CEO are in this Hermes home as {LOGIN_FILE}. "
                "Fill login forms from that file with browser_type. "
                "Never print the file, usernames, or passwords in RESULT, chat, or INDEX. "
                "If TOTP, CAPTCHA, or a bank wall appears, stop with a line that is exactly LOGIN_WALL and the page URL."
            )
    if preset not in {"cos", "ask"}:
        law = law_extra(preset, project_id, worker_id)
        if law:
            bits.append(f"LAW:\n{law}")
    return "\n\n".join(bits)


def status_reply(index_text: str, message: str = "", who: str = "", wiring: str = "") -> str:
    name = (who or "OpenBot").strip() or "OpenBot"
    is_status = bool(STATUS.search(message or ""))
    greeting = bool(GREET.search(message or "")) and not is_status
    now = index_field(index_text, "Now") or "—"
    last = index_field(index_text, "Last") or "—"
    nxt = index_field(index_text, "Next") or "—"
    blocker = index_field(index_text, "Blocker") or "—"
    if greeting:
        if THANKS.search(message or ""):
            if name in {"OpenBot", "Chief of Staff"}:
                return "You're welcome. Chief of Staff is here — or open any CEO and talk to them directly."
            return f"You're welcome. I'm {name} — I report to Chief of Staff."
        if name in {"OpenBot", "Chief of Staff"}:
            return "Hello — I'm Chief of Staff. The CEOs report to me. You can also open any CEO and talk to them directly."
        return f"Hello — {name}. I report to Chief of Staff. How can I help?"
    if is_status:
        lines: list[str] = [now]
        if nxt and nxt != "—":
            lines.append(f"Next: {nxt}")
        if last and last != "—":
            lines.append(f"Last: {last}")
        if blocker and blocker != "—":
            lines.append(f"Blocked: {blocker}")
        if wiring:
            lines.append(wiring)
        return "\n".join(lines).strip() or now
    if name in {"OpenBot", "Chief of Staff"}:
        return "Chief of Staff. Ask what's going on across the org, or open a CEO and talk to them directly."
    return f"I'm {name}. I report to Chief of Staff. Ask what's going on, or send the work."


def skills_reply() -> str:
    names = str(load_settings().get("hermes_skills") or "").strip()
    listed = ", ".join(part.strip() for part in names.split(",") if part.strip()) or "all skills installed on this Hermes home"
    return (
        "Skills live in Settings → Models, not on a CEO. "
        "Chat never loads them. Think, Research, and Ops can use them without Chat calling tools. "
        f"This instance: {listed}. "
        "To add one: Settings → Models → Hermes skills, type the names Hermes lists "
        "(`hermes skills list`), Save. Leave the field blank to keep every installed skill available to the work bots."
    )


def keep_going_for(
    chosen: str,
    *,
    talk: bool = False,
    stopped: bool = False,
    login_wall: bool = False,
    ok: bool = True,
) -> bool:
    if stopped or not ok:
        return False
    if login_wall:
        return True
    if talk or chosen == "cos":
        return False
    return chosen in {"builder", "research", "ops", "think"}


LOGIN_WALL_MARK = re.compile(r"^LOGIN_WALL\b", re.M)


def _capture_login_wall(text: str, page_url: str | None = None) -> tuple[bool, str | None]:
    if not LOGIN_WALL_MARK.search(text or ""):
        return False, page_url
    url = page_url
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("http://") or stripped.startswith("https://"):
            url = stripped
            break
    return True, url


def pending_approvals(limit: int = 12) -> list[dict]:
    jobs = sorted(list_jobs(), key=lambda job: str(job.get("at") or ""), reverse=True)
    latest: dict[str, dict] = {}
    for job in jobs:
        if not isinstance(job, dict) or job.get("stopped"):
            continue
        key = str(job.get("project_id") or "") or "_staff"
        if key in latest:
            continue
        latest[key] = job
    out: list[dict] = []
    for job in latest.values():
        if job.get("login_wall"):
            kind = "login"
            label = "needs a login"
        elif job.get("diff_pending"):
            kind = "diff"
            label = "Accept or reject the diff"
        else:
            continue
        out.append(
            {
                "id": str(job.get("id") or ""),
                "kind": kind,
                "label": label,
                "project_id": str(job.get("project_id") or ""),
                "engine": str(job.get("engine") or "board"),
                "preset": str(job.get("preset") or ""),
                "url": str(job.get("url") or ""),
                "at": str(job.get("at") or ""),
            }
        )
        if len(out) >= limit:
            break
    return out


def route_for_node(message: str, node: str) -> list[str]:
    # Chat stays on Cos (board). Hermes Think is only when they ask to plan.
    # OpenCode / Research / Ops still fire from the message itself.
    _ = node
    return route_plan(message, None)


def _persist_hermes_session(project_id: str | None, worker_id: str | None, sid: str) -> None:
    if not project_id or not sid or worker_id:
        return
    try:
        patch_project_tools(project_id, {"hermes_session_id": sid})
    except ValueError:
        pass


def _clean_quote(raw: str | None) -> str:
    text = redact_chat_login(str(raw or "").strip())
    return re.sub(r"\s+", " ", text)[:400]


def handle(
    message: str,
    folder: str | None = None,
    preset: str | None = None,
    project_id: str | None = None,
    worker_id: str | None = None,
    on_delta=None,
    on_progress=None,
    run_id: str | None = None,
    quote: str | None = None,
) -> dict:
    node = "staff"
    if worker_id:
        node = "worker"
    elif project_id:
        node = "ceo"
    if PROGRAM.search(message or ""):
        inbox_id = project_id or work_target(None, "builder")
        if inbox_id:
            write_project_inbox(inbox_id, message)
    # Chat seat is auto: same composer hands Code / Think / Research / Ops
    # to the engines. Picking a work seat still forces that path.
    # Status always reads INDEX — even if Think / Research / Ops is pinned.
    if STATUS.search(message or "") and not URL.search(message or "") and not CODE.search(message or ""):
        steps = ["cos"]
    elif preset == "cos" or not preset or preset not in PRESETS:
        steps = route_for_node(message, node)
    else:
        steps = [preset]
    quote = _clean_quote(quote) or (
        search_quote(thread_key(project_id, worker_id), message) if wants_quote(message) else ""
    )
    cancel = None
    if run_id:
        from .live import cancel_event

        cancel = cancel_event(run_id)
    jobs: list[dict] = []
    carry = ""
    for index, step in enumerate(steps):
        payload = message
        if index and carry:
            payload = (
                f"{message}\n\n"
                f"PRIOR RESULT from {jobs[-1].get('engine')} "
                f"(use this; do not redo that work):\n{carry[-1200:]}"
            )
        aimed = work_target(project_id, step)
        if step != "cos" and aimed:
            ensure_ceo_engines(aimed)
        tools = project_tools(aimed if step != "cos" else project_id)
        resume_id = None
        if aimed and not worker_id:
            resume_id = str(tools.get("hermes_session_id") or "").strip() or None
        hermes_session = session_name(aimed, worker_id if project_id else None)
        if on_progress:
            lane_name = LANE_LABEL.get(step, step)
            who = node_label(aimed if step != "cos" else project_id, worker_id if project_id else None)
            if not project_id:
                who = "Chief of Staff"
            extra = " · resuming Telegram session" if resume_id and step in {"think", "research", "ops"} else ""
            try:
                _call_progress(on_progress, f"{who} · {lane_name}{extra}", step)
            except Exception:
                pass
        jobs.append(
            _handle_preset(
                payload,
                folder,
                step,
                aimed if step != "cos" else project_id,
                worker_id if project_id else None,
                hermes_session if step in {"think", "research", "ops"} else None,
                tools,
                quote,
                on_delta,
                cancel,
                run_id,
                resume_id if step in {"think", "research", "ops"} else None,
                on_progress,
            )
        )
        carry = jobs[-1].get("text") or ""
        if jobs[-1].get("stopped"):
            break
    last = dict(jobs[-1])
    last["handoff"] = [job.get("preset") for job in jobs]
    if len(jobs) > 1:
        last["text"] = "\n\n".join(
            f"[{job.get('engine')} · {job.get('preset')}]\n{job.get('text')}" for job in jobs
        )
        last["chain"] = [
            {"id": job.get("id"), "engine": job.get("engine"), "preset": job.get("preset")}
            for job in jobs
        ]
    rollup_pid = project_id or (None if last.get("talk") else last.get("project_id"))
    if rollup_pid and not last.get("talk"):
        rollup_staff(rollup_pid, worker_id if project_id else None, last.get("text") or "")
        last["index"] = read_project_index(str(rollup_pid))
    elif project_id:
        last["index"] = read_project_index(project_id)
    else:
        last["index"] = staff_briefing()
    last["next"] = index_field(last.get("index") or "", "Next")
    last["keep_going"] = keep_going_for(
        last.get("preset") or "cos",
        talk=bool(last.get("talk")),
        stopped=bool(last.get("stopped")),
        login_wall=bool(last.get("login_wall")),
        ok=not last.get("blocker"),
    )
    return last


def _handle_preset(
    message: str,
    folder: str | None,
    chosen: str,
    project_id: str | None = None,
    worker_id: str | None = None,
    session: str | None = None,
    tools: dict | None = None,
    quote: str = "",
    on_delta=None,
    cancel: threading.Event | None = None,
    run_id: str | None = None,
    resume_id: str | None = None,
    on_progress=None,
) -> dict:
    def patch_index_line(label: str, value: str) -> None:
        patch_scope(project_id, worker_id, label, value)

    engines = detect()
    if chosen not in PRESETS and chosen != "ask":
        chosen = "ask"
    job_id = uuid.uuid4().hex[:10]
    engine = "board"
    text = ""
    blocker = None
    work = _work_folder(folder, project_id)
    usage_model = "none"
    prompt_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    usd_estimate = 0.0
    diff_text = ""
    untracked: list[str] = []
    git_snap = None
    diff_pending = False
    index_text = read_project_index(project_id)
    brain_text = read_worker_brain(project_id, worker_id) or (index_text if project_id else read_brain("cos"))
    tools = tools or project_tools(project_id)
    seats = tools.get("seats") if isinstance(tools.get("seats"), dict) else {}
    skills = str(load_settings().get("hermes_skills") or "").strip() or None
    hermes_home_dir = str(tools.get("hermes_home") or "").strip() or None
    login_wall = False
    page_url = None
    stopped = False
    talk = False
    from .spend import classify_job, gate_paid_job

    if chosen in {"think", "builder", "research", "ops"}:
        allowed, reason, spend_now = gate_paid_job(chosen, project_id, tools)
        if not allowed:
            engine = "board"
            blocker = reason
            text = reason or "spend cap"
            patch_index_line("Blocker", blocker or "spend cap")
            cfg = load_config()
            receipt = _receipt_base(job_id, chosen, engine, message, work)
            receipt.update(
                {
                    "blocker": blocker,
                    "text": text,
                    "usd_estimate": 0.0,
                    "wallet": "included",
                    "cost_known": True,
                    "spend": spend_now,
                    "cap_remaining": spend_now.get("cap_remaining"),
                    "project_id": project_id,
                    "worker_id": worker_id,
                    "keep_going": False,
                }
            )
            write_job(receipt)
            receipt["index"] = read_project_index(project_id) if project_id else read_index()
            receipt["engines"] = engines
            receipt["config"] = {"work_dir": cfg["work_dir"], "first_run_done": cfg["first_run_done"]}
            return public_job(receipt)

    if chosen == "ask":
        text = (
            "Which path?\n"
            "- Status (the brief)\n"
            "- Code (OpenCode in a folder)\n"
            "- Research (fetch a URL, snapshot if Hermes is running)\n"
            "- Schedule (save an Ops ticket, attach cron in Hermes)"
        )
        engine = "board"
    elif chosen == "think":
        settings = load_settings()
        chosen_model = seated_or_auto(settings, "think", seats) or None
        _activate("Hermes Agent", tools, chosen_model)
        usage_model = chosen_model or "engine-default"
        talk = False
        if not engines["hermes"]["present"]:
            engine = "board"
            blocker = "Hermes Agent missing"
            text = (
                "This bot uses Hermes Agent. Install Hermes Agent, then try again.\n"
                f"{engines['hermes'].get('install_cmd') or engines['hermes']['install']}"
            )
            patch_index_line("Blocker", blocker)
        else:
            engine = "Hermes Agent"
            if talk:
                who = node_label(project_id, worker_id) if project_id else (worker_id or "Think")
                status = "\n".join(
                    f"{label}: {index_field(index_text, label) or '—'}"
                    for label in ("Now", "Last", "Next", "Blocker")
                )
                if project_id:
                    status = f"{status}\n{wiring_brief(project_id)}"
                packet = chat_packet(who if project_id else "Chief of Staff", status, message)
            else:
                packet = job_packet(
                    "worker" if worker_id else "think",
                    index_text,
                    brain_text,
                    message,
                    _packet_extra(
                        project_id,
                        quote=quote,
                        preset="think",
                        worker_id=worker_id,
                        hermes_home=hermes_home_dir,
                    ),
                )
            ran = hermes_chat(
                packet,
                cwd=work,
                model=chosen_model,
                toolsets=None,
                session=None if talk or resume_id else session,
                resume=None if talk else resume_id,
                skills=None if talk else skills,
                on_delta=on_delta,
                cancel=cancel,
                run_id=run_id,
                home=hermes_home_dir,
                talk=talk,
            )
            text = ran.get("text") or "(no output)"
            usage = ran.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens") or 0)
            cached_tokens = int(usage.get("cache_read_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            usd_estimate = float(usage.get("estimated_cost_usd") or 0)
            if usage.get("model"):
                usage_model = str(usage.get("model"))
            if not talk:
                _persist_hermes_session(project_id, worker_id, str(ran.get("session_id") or "").strip())
            if ran.get("stopped"):
                stopped = True
                blocker = "stopped"
                patch_index_line("Blocker", "stopped")
            elif not ran.get("ok"):
                blocker = f"hermes think exited {ran.get('code')}"
                patch_index_line("Blocker", blocker)
                patch_index_line("Last", _index_last(text, failed=True))
            elif talk:
                pass
            else:
                wall, wall_url = _capture_login_wall(text, page_url)
                if wall:
                    login_wall = True
                    page_url = wall_url
                    blocker = "login wall — approve a vault login or type it here"
                    patch_index_line("Blocker", blocker)
                else:
                    patch_index_line("Last", _index_last(text))
                    patch_index_line("Now", "Think finished")
                    patch_index_line("Next", "Ask Code to execute, or Chief of Staff for status")
                    patch_index_line("Blocker", "—")
    elif chosen == "cos":
        talk = True
        settings = load_settings()
        chosen_model = seated_or_auto(settings, "chat", seats) or recommended_chat_id() or None
        # Cos talk is Hermes. Muse Spark / OpenCode seat IDs are for Code — remap.
        if model_provider(chosen_model) in SKIP_HERMES_PROVIDERS or (
            chosen_model and ("muse-spark" in chosen_model.lower() or "contributor-free" in chosen_model.lower())
        ):
            chosen_model = (
                hermes_chat_model_for_provider("nous")
                or hermes_chat_model_for_provider("openrouter")
                or hermes_chat_model_for_provider("anthropic")
                or None
            )
        provider, model_id = split_model(chosen_model)
        status_ask = bool(STATUS.search(message or ""))
        skill_ask = bool(SKILL.search(message or ""))
        file_reply = "" if skill_ask or status_ask else (cos_file_reply(message or "") or "")
        if not file_reply and BROWSER_LOGIN.search(message or ""):
            file_reply = cos_browser_login_reply()
        use_llm = (
            bool(chosen_model)
            and bool(provider)
            and bool(model_id)
            and not status_ask
            and not skill_ask
            and not file_reply
            and bool(engines["hermes"]["present"])
        )
        if skill_ask:
            engine = "board"
            text = skills_reply()
        elif file_reply:
            engine = "board"
            text = file_reply
        if use_llm:
            from .spend import gate as spend_gate

            cap = tools.get("spend_cap_usd")
            if cap is None:
                cap = load_config()["spend_cap_usd"]
            spend_now = spend_summary(float(cap), load_config()["spend_cap_period"], project_id=project_id)
            paid = spend_gate("think", spend_now)
            if not paid["allow"]:
                use_llm = False
                text = status_reply(index_text, message, node_label(project_id, worker_id))
                if paid.get("reason"):
                    text = f"{text}\n\n{paid['reason']}"
                engine = "board"
        if use_llm:
            engine = "Hermes Agent"
            usage_model = chosen_model or "engine-default"
            who = node_label(project_id, worker_id) if project_id else "Chief of Staff"
            if project_id:
                status = "\n".join(
                    f"{label}: {index_field(index_text, label) or '—'}"
                    for label in ("Now", "Last", "Next", "Blocker")
                )
                status = f"{status}\n{wiring_brief(project_id)}"
                from .channel import session_hint

                hint = session_hint(hermes_home_dir, str(tools.get("hermes_session_id") or "") or None)
                if hint:
                    status = f"{status}\n\n{hint}"
            else:
                status = staff_status_reply()
            # Chat is a fresh oneshot. Do NOT --resume the Telegram Hermes
            # session here — that replays mid-tool / unrelated turns into this
            # reply. Recent Telegram is already in status via session_hint.
            packet = chat_packet(who, status, message if not quote else f"{message}\n\nReplying to this earlier turn:\n{quote}")
            ran: dict = {}
            attempts = _chat_attempts(tools, chosen_model)
            if not attempts:
                fallback_model = (
                    hermes_chat_model_for_provider("openrouter")
                    or hermes_chat_model_for_provider("nous")
                    or chosen_model
                )
                _activate("Hermes Agent", tools, fallback_model)
                attempts = [({}, fallback_model)] if fallback_model else []
            if on_progress:
                try:
                    _call_progress(on_progress, f"{who} · Chat", "cos")
                except Exception:
                    pass
            for account, model in attempts:
                if account.get("id"):
                    activate_account(str(account["id"]))
                else:
                    _activate("Hermes Agent", tools, model)
                ran = hermes_chat(
                    packet,
                    cwd=work,
                    model=model,
                    toolsets=None,
                    session=None,
                    resume=None,
                    skills=None,
                    on_delta=_quiet_delta(on_delta),
                    cancel=cancel,
                    run_id=run_id,
                    home=hermes_home_dir,
                    talk=True,
                )
                chosen_model = model
                if ran.get("stopped"):
                    break
                if wallet_empty(ran.get("text") or ""):
                    if account.get("id"):
                        mark_wallet_empty(str(account["id"]))
                    continue
                if ran.get("ok") and (ran.get("text") or "").strip() and ran.get("text") != "(no output)":
                    break
                continue
            text = ran.get("text") or "(no output)"
            usage = ran.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens") or 0)
            cached_tokens = int(usage.get("cache_read_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            usd_estimate = float(usage.get("estimated_cost_usd") or 0)
            if usage.get("model"):
                usage_model = str(usage.get("model"))
            else:
                usage_model = chosen_model or "engine-default"
            if ran.get("stopped"):
                stopped = True
                blocker = "stopped"
            elif wallet_empty(text):
                blocker = "keyring wallets empty"
                text = wallet_empty_reply()
                engine = "board"
            elif not ran.get("ok") or not (ran.get("text") or "").strip() or text == "(no output)":
                blocker = f"hermes chat exited {ran.get('code')}"
                detail = clean_hermes_fail_hint(ran)
                text = _cos_chat_fallback(project_id, worker_id, message, detail)
                engine = "board"
        elif not use_llm and not text:
            engine = "board"
            if not project_id and status_ask:
                text = staff_status_reply()
            else:
                text = status_reply(
                    index_text,
                    message,
                    node_label(project_id, worker_id) or "Chief of Staff",
                    wiring=wiring_brief(project_id),
                )
    elif chosen == "builder":
        if not engines["opencode"]["present"]:
            engine = "board"
            blocker = "OpenCode binary missing"
            text = (
                "Builder needs the official OpenCode binary.\n"
                f"Install: {engines['opencode']['install']}\n"
                "Board is Cos-only until then."
            )
            patch_index_line("Blocker", blocker)
        else:
            engine = "OpenCode"
            usage_model = "engine-default"
            git_snap = snapshot(work)
            model = seated_or_auto(load_settings(), "code", seats) or DEFAULT_CODE_MODEL
            extra = _packet_extra(project_id, quote=quote, preset="builder", worker_id=worker_id)
            prompt = (
                "OpenBot Chat dispatched this to OpenCode for this CEO. "
                "Edit the Code folder. Diffs come back to this chat for the operator.\n"
                "Local edits only. Do not git push, publish, pay, or change production. "
                "The operator Accepts or Rejects the diff — that is the action gate.\n\n"
                f"{message}"
            )
            if extra:
                prompt = f"{prompt}\n\n{extra}"
            attempts = _code_attempts(tools, model)
            if not attempts:
                _activate("OpenCode", tools, model)
                attempts = [({}, model)]
            code, out = 1, ""
            parsed = parse_opencode_events("")
            from .usage import error_message_from_raw

            for account, attempt_model in attempts:
                if account.get("id"):
                    activate_account(str(account["id"]))
                else:
                    _activate("OpenCode", tools, attempt_model)
                model = attempt_model
                code, out = run_opencode(
                    work,
                    prompt,
                    engines["opencode"].get("path"),
                    model,
                    on_delta=_quiet_delta(on_delta),
                    cancel=cancel,
                    run_id=run_id,
                    mcp_github=bool(tools.get("mcp_github")),
                    on_progress=on_progress,
                )
                parsed = parse_opencode_events(out)
                text = parsed.text or out or "(no output)"
                err = error_message_from_raw(out) or ""
                if code == 130:
                    break
                if wallet_empty(text) or wallet_empty(out) or wallet_empty(err):
                    if account.get("id"):
                        mark_wallet_empty(str(account["id"]))
                    continue
                break
            text = parsed.text or out or "(no output)"
            prompt_tokens = parsed.prompt_tokens
            cached_tokens = parsed.cached_tokens
            output_tokens = parsed.output_tokens
            usd_estimate = parsed.usd_estimate
            if parsed.model != "engine-default":
                usage_model = parsed.model
            else:
                usage_model = model
            diff_text = diff_against_head(work) if git_snap.get("is_repo") else ""
            untracked = new_untracked(work, git_snap) if git_snap.get("is_repo") else []
            diff_pending = bool(diff_text.strip() or untracked)
            if code == 130:
                stopped = True
            if wallet_empty(text) or wallet_empty(out):
                blocker = "keyring wallets empty"
                text = wallet_empty_reply()
                engine = "board"
                patch_index_line("Blocker", blocker)
                patch_index_line("Last", _index_last(text, failed=True))
            elif code != 0:
                blocker = f"opencode run exited {code}"
                if not parsed.text:
                    text = error_message_from_raw(out) or text
                patch_index_line("Blocker", blocker)
                patch_index_line("Last", _index_last(text, failed=True))
            else:
                patch_index_line("Last", _index_last(text))
                patch_index_line("Now", f"Builder job {job_id} in {work}")
                patch_index_line(
                    "Next",
                    "Review the diff card (Accept / Reject)" if diff_pending else "Ask for the next change",
                )
                patch_index_line("Blocker", "—")
    elif chosen == "research":
        url = first_url(message)
        settings = load_settings()
        if not url:
            engine = "board"
            text = "Paste a URL or say look at this site plus a link. Fetch first. Hermes snapshot is in the Hermes workspace."
            patch_index_line("Blocker", "Research needs a URL")
        else:
            page = fetch_page(url)
            if page.get("login_wall") and not staged_logins_ready(hermes_home_dir):
                engine = "board"
                login_wall = True
                page_url = url
                blocker = "login wall — approve a vault login or type it here"
                text = page.get("error") or blocker
                patch_index_line("Blocker", blocker)
            elif not engines["hermes"]["present"]:
                engine = "board"
                if not page.get("ok"):
                    blocker = page.get("error") or "fetch failed"
                    text = (
                        f"{blocker}\n"
                        "Install Hermes Agent to snapshot JS apps.\n"
                        f"{engines['hermes'].get('install_cmd') or engines['hermes']['install']}"
                    )
                    patch_index_line("Blocker", "Hermes Agent missing")
                else:
                    text = (
                        f"Fetched {page.get('url')} ({page.get('chars')} chars, backend {page.get('backend')}).\n"
                        "Hermes Agent is missing, so this is extract-only. Install it, then Research can snapshot.\n"
                        f"{engines['hermes'].get('install_cmd') or engines['hermes']['install']}\n\n"
                        f"{page.get('text')}"
                    )
                    patch_index_line("Last", _index_last(text))
                    patch_index_line("Now", f"Read {page.get('url')}")
                    patch_index_line("Next", "Install Hermes Agent for snapshot clicks")
                    patch_index_line("Blocker", "Hermes Agent missing")
                    blocker = "Hermes Agent missing"
            else:
                engine = "Hermes Agent"
                chosen_model = seated_or_auto(settings, "research", seats) or None
                _activate("Hermes Agent", tools, chosen_model)
                usage_model = chosen_model or "engine-default"
                extra = (
                    f"URL: {page.get('url') or url}\n"
                    f"FETCH backend: {page.get('backend') or 'fetch'}\n"
                    f"FETCH ok: {bool(page.get('ok'))}\n"
                )
                if page.get("ok"):
                    extra += (
                        "Use this extract first. Promote to snapshot tools only if the page is an app "
                        "or this extract is empty/useless.\n\n"
                        f"{page.get('text')}"
                    )
                    toolsets = "web"
                elif page.get("login_wall"):
                    extra += (
                        "This URL looks like a login form. Fill username and password from the VAULT LOGINS file. "
                        "Never print that file. If TOTP or CAPTCHA appears, stop with LOGIN_WALL and the page URL."
                    )
                    toolsets = "web"
                else:
                    extra += (
                        f"Extract failed: {page.get('error')}. "
                        "Use web extract / snapshot. Do not type passwords from chat."
                    )
                    toolsets = "web"
                packet = job_packet(
                    "research",
                    index_text,
                    brain_text or read_brain("research"),
                    message,
                    _packet_extra(
                        project_id,
                        extra,
                        quote,
                        preset="research",
                        worker_id=worker_id,
                        hermes_home=hermes_home_dir,
                    ),
                )
                ran = hermes_chat(
                    packet,
                    cwd=work,
                    model=chosen_model,
                    toolsets=toolsets,
                    session=None if resume_id else session,
                    resume=resume_id,
                    skills=skills,
                    on_delta=on_delta,
                    cancel=cancel,
                    run_id=run_id,
                    home=hermes_home_dir,
                )
                text = ran.get("text") or "(no output)"
                usage = ran.get("usage") or {}
                prompt_tokens = int(usage.get("input_tokens") or 0)
                cached_tokens = int(usage.get("cache_read_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                usd_estimate = float(usage.get("estimated_cost_usd") or 0)
                if usage.get("model"):
                    usage_model = str(usage.get("model"))
                _persist_hermes_session(project_id, worker_id, str(ran.get("session_id") or "").strip())
                if ran.get("stopped"):
                    stopped = True
                    blocker = "stopped"
                    patch_index_line("Blocker", "stopped")
                elif not ran.get("ok"):
                    blocker = f"hermes chat exited {ran.get('code')}"
                    if page.get("ok"):
                        text = (
                            f"{text}\n\nFetched extract (Hermes did not finish):\n"
                            f"{page.get('text')}"
                        )
                    patch_index_line("Blocker", blocker)
                    patch_index_line("Last", _index_last(text, failed=True))
                else:
                    wall, wall_url = _capture_login_wall(text, page.get("url") or url)
                    if wall:
                        login_wall = True
                        page_url = wall_url
                        blocker = "login wall — approve a vault login or type it here"
                        patch_index_line("Blocker", blocker)
                    else:
                        patch_index_line("Last", _index_last(text))
                        patch_index_line("Now", f"Research {page.get('url') or url}")
                        patch_index_line("Next", "Ask another URL, or open Hermes for snapshot clicks")
                        patch_index_line("Blocker", "—")
    elif chosen == "ops":
        ticket = write_ops_ticket(message)
        settings = load_settings()
        if not engines["hermes"]["present"]:
            engine = "board"
            blocker = "Hermes Agent missing"
            text = (
                "Saved an Ops ticket to inbox/ops.md.\n"
                "Install Hermes Agent, then Schedule will attach cron there. OpenBot does not invent a second scheduler.\n"
                f"{engines['hermes'].get('install_cmd') or engines['hermes']['install']}\n\n"
                f"{ticket}"
            )
            patch_index_line("Blocker", blocker)
            patch_index_line("Last", _index_last(text))
            patch_index_line("Now", "Ops ticket waiting")
            patch_index_line("Next", "Install Hermes Agent")
        else:
            engine = "Hermes Agent"
            chosen_model = seated_or_auto(settings, "ops", seats) or None
            _activate("Hermes Agent", tools, chosen_model)
            usage_model = chosen_model or "engine-default"
            schedule = parse_schedule(message)
            if schedule:
                created = cron_create(
                    schedule,
                    message,
                    f"openbot-{project_id or 'staff'}-{job_id}",
                    cwd=work,
                    home=hermes_home_dir,
                )
                text = (
                    f"Saved inbox/ops.md and asked Hermes cron to attach it.\n"
                    f"schedule: {schedule}\n\n"
                    f"{created.get('text')}\n\n"
                    f"{ticket}"
                )
                if not created.get("ok"):
                    blocker = f"hermes cron exited {created.get('code')}"
                    patch_index_line("Blocker", blocker)
                    patch_index_line("Last", _index_last(text, failed=True))
                else:
                    patch_index_line("Last", _index_last(text))
                    patch_index_line("Now", f"Ops cron {schedule}")
                    patch_index_line("Next", "Open Hermes to inspect or pause the job")
                    patch_index_line("Blocker", "—")
                    add_schedule(project_id, schedule, message, job_id, worker_id)
            else:
                packet = job_packet(
                    "ops",
                    index_text,
                    brain_text or read_brain("ops"),
                    message,
                    _packet_extra(
                        project_id,
                        "Create a Hermes cron job for this request. Do not run it now. "
                        "Reply with job id and schedule. Deliver locally. "
                        "Silent on success. Idempotent retries. Never send, publish, pay, or delete.",
                        quote,
                        preset="ops",
                        worker_id=worker_id,
                        hermes_home=hermes_home_dir,
                    ),
                )
                ran = hermes_chat(
                    packet,
                    cwd=work,
                    model=chosen_model,
                    toolsets=None,
                    session=None if resume_id else session,
                    resume=resume_id,
                    skills=skills,
                    on_delta=on_delta,
                    cancel=cancel,
                    run_id=run_id,
                    home=hermes_home_dir,
                )
                text = (
                    f"Saved inbox/ops.md.\n\n"
                    f"{ran.get('text')}\n\n"
                    f"{ticket}"
                )
                usage = ran.get("usage") or {}
                prompt_tokens = int(usage.get("input_tokens") or 0)
                cached_tokens = int(usage.get("cache_read_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                usd_estimate = float(usage.get("estimated_cost_usd") or 0)
                if usage.get("model"):
                    usage_model = str(usage.get("model"))
                _persist_hermes_session(project_id, worker_id, str(ran.get("session_id") or "").strip())
                if ran.get("stopped"):
                    stopped = True
                    blocker = "stopped"
                    patch_index_line("Blocker", "stopped")
                elif not ran.get("ok"):
                    blocker = f"hermes chat exited {ran.get('code')}"
                    patch_index_line("Blocker", blocker)
                    patch_index_line("Last", _index_last(text, failed=True))
                else:
                    patch_index_line("Last", _index_last(text))
                    patch_index_line("Now", "Ops cron requested in Hermes")
                    patch_index_line("Next", "Open Hermes to confirm the schedule")
                    patch_index_line("Blocker", "—")

    cfg = load_config()
    cap = tools.get("spend_cap_usd")
    if cap is None:
        cap = cfg["spend_cap_usd"]
    spend = spend_summary(float(cap), cfg["spend_cap_period"], project_id=project_id)
    wallet = classify_job(
        {"engine": engine, "usd_estimate": usd_estimate},
        spend.get("go") or {},
        spend.get("policy") or {},
    )
    cap_remaining = round(max(0.0, spend["cap_remaining"] - (usd_estimate if wallet == "payg" else 0.0)), 6)

    receipt = _receipt_base(job_id, chosen, engine, message, work)
    index_now = read_project_index(project_id) if project_id else read_index()
    next_line = index_field(index_now, "Next")
    receipt.update(
        {
            "engine": engine,
            "model": usage_model if engine != "board" else "none",
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "usd_estimate": usd_estimate,
            "wallet": wallet,
            "cost_known": wallet != "unknown",
            "cap_remaining": cap_remaining,
            "blocker": blocker,
            "diff": diff_text,
            "untracked": untracked,
            "diff_pending": diff_pending,
            "git_snapshot": git_snap,
            "tools_on": (not talk) and (
                chosen in {"builder", "research", "ops"}
                or bool(session and chosen == "think")
                or bool(tools.get("mcp_github"))
            ),
            "session": resume_id or session,
            "project_id": project_id,
            "worker_id": worker_id,
            "login_wall": login_wall,
            "url": page_url,
            "logins": public_logins(project_id) if login_wall else [],
            "stopped": stopped,
            "next": next_line,
            "talk": talk,
            "keep_going": keep_going_for(
                chosen,
                talk=talk,
                stopped=stopped,
                login_wall=login_wall,
                ok=blocker is None,
            ),
        }
    )
    receipt["gate"] = classify_gate(
        chosen,
        message,
        diff_pending=diff_pending,
        login_wall=login_wall,
        ok=blocker is None,
        talk=talk,
    )
    receipt["text"] = text
    close_work_job(receipt, text)
    write_job(receipt)
    spend_after = spend_summary(float(cap), cfg["spend_cap_period"], project_id=project_id)
    receipt["cap_remaining"] = spend_after["cap_remaining"]
    receipt["text"] = text
    receipt["engines"] = engines
    receipt["index"] = index_now
    receipt["spend"] = spend_after
    receipt["config"] = {
        "work_dir": cfg["work_dir"],
        "first_run_done": cfg["first_run_done"],
    }
    return public_job(receipt)


def public_job(receipt: dict | None) -> dict:
    if not receipt:
        return {}
    from .usage import sanitize_job_text

    out = dict(receipt)
    out.pop("git_snapshot", None)
    out.pop("engines", None)
    if "text" in out:
        out["text"] = sanitize_job_text(out.get("text"))
    if "message" in out:
        out["message"] = redact_chat_login(out.get("message") or "")
    return out


def decide_diff(job_id: str, accept: bool) -> dict:
    job = read_job(job_id)
    if job is None:
        return {"error": "job not found", "ok": False}
    if not job.get("diff_pending"):
        return {"error": "no pending diff", "ok": False, "job": job}
    folder = job.get("folder")
    pid = job.get("project_id") if isinstance(job.get("project_id"), str) else None
    wid = job.get("worker_id") if isinstance(job.get("worker_id"), str) else None

    def patch_lines(label: str, value: str) -> None:
        patch_scope(pid, wid, label, value)

    if accept:
        updated = update_job(
            job_id,
            {
                "diff_pending": False,
                "accepted": True,
                "rejected": False,
            },
        )
        patch_lines("Last", f"accepted diff {job_id}")
        patch_lines("Next", "Ask for the next change")
        patch_lines("Blocker", "—")
        rollup_staff(pid, wid, f"accepted diff {job_id}")
        log_approval(updated or job, True)
        return {
            "ok": True,
            "accepted": True,
            "job": public_job(updated),
            "index": read_project_index(pid) if pid else read_index(),
        }
    ok, detail = restore_snapshot(str(folder), job.get("git_snapshot") or {})
    if not ok:
        patch_lines("Blocker", f"reject restore failed ({job_id})")
        return {"ok": False, "error": detail, "job": public_job(job), "index": read_index()}
    updated = update_job(
        job_id,
        {
            "diff_pending": False,
            "accepted": False,
            "rejected": True,
            "diff": "",
            "untracked": [],
        },
    )
    patch_lines("Last", f"rejected diff {job_id}")
    patch_lines("Next", "Ask Builder again, or change the folder")
    patch_lines("Blocker", "—")
    rollup_staff(pid, wid, f"rejected diff {job_id}")
    log_approval(updated or job, False)
    return {
        "ok": True,
        "accepted": False,
        "rejected": True,
        "job": public_job(updated),
        "index": read_project_index(pid) if pid else read_index(),
    }
