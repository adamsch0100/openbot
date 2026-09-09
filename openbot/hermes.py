"""Official Hermes Agent CLI. Do not invent a third runtime."""

from __future__ import annotations

import json
import os
import re
import select
import shlex
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .detect import hermes_home, which

ANSI = re.compile(r"\x1b\[[0-9;]*m")
HERMES_TIMEOUT = 600
TALK_TIMEOUT = 25
TALK_RESUME_TIMEOUT = 180
HERMES_MAX_TURNS = "16"
USAGE_KEYS = (
    "estimated_cost_usd",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "model",
    "provider",
    "session_id",
    "completed",
    "failed",
)
PROVIDER_MAP = {
    "opencode": "opencode-zen",
    "zen": "opencode-zen",
    "openrouter": "openrouter",
    "nous": "nous",
    "anthropic": "anthropic",
    "openai": "openai-api",
    "google": "gemini",
    "gemini": "gemini",
    "xai": "xai",
    "x-ai": "xai",
}
MORNING = re.compile(r"\b(every|each)\s+morning\b|\bdaily at 9\b", re.I)
EVERY_N = re.compile(
    r"\bevery\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b",
    re.I,
)
EVERY_DAY = re.compile(r"\b(every day|each day|daily)\b", re.I)
SESSION_ID_RE = re.compile(r"session_id:\s*([A-Za-z0-9._:-]+)", re.I)
SESSION_NOISE = re.compile(
    r"^[↻→•\s]*(Session\s+.+|Starting fresh\.?|Resumed session.*|"
    r"Model restored from session:.*|"
    r"session_id:\s+\S+|RESULT\s*\(.*|"
    r"\(\d+\s+user messages?,\s+\d+\s+total messages?\)|"
    r"Warning: Unknown toolsets:.*|"
    r"No usable credentials found.*|"
    r".*OPENCODE_ZEN_API_KEY.*)$",
    re.I,
)
TOOL_MARKUP = re.compile(
    r"(?:<\|?(?:DSML|tool_?calls?|invoke|parameter)\|?[^>]*>|"
    r"</\|?(?:DSML|tool_?calls?|invoke|parameter)\|?[^>]*>|"
    r"function\s*calls?\s*begin|function\s*calls?\s*end)",
    re.I,
)
PACKET_LINE = re.compile(
    r"^(You are the |You are Chief of Staff|You report to Chief of Staff|"
    r"The (human )?operator |You dispatch |Ask, and you dispatch|"
    r"Your job is triage|Before doing substantial|"
    r"Do not hire a Bot|Reply like a person|You do not edit files|"
    r"No RESULT\.|Do not mention Now|Do not print session_id|"
    r"If RECENT TELEGRAM|Never ask the operator to paste|"
    r"If they ask to run all existing|OpenCode edits your|"
    r"You own the outcome|Chat is not memory|"
    r"Report a short RESULT|Name the engine that ran|"
    r"Never print passwords|Park send, publish|If TOTP|If VAULT LOGINS|"
    r"Write a short RESULT|STAFF \(files|INDEX:\s*$|BRAIN:\s*$|TASK:\s*$|"
    r"OPEN HANDOFFS:|VAULT LOGINS|The operator is talking|"
    r"The operator is in OpenBot Chat|The operator can also open|"
    r"Specialist lanes execute|Code: OpenCode in |Hermes: |"
    r"Bus: org/projects/|Telegram: |"
    r".+ CEO — reports to Chief of Staff)",
    re.I,
)
META_JUNK = re.compile(
    r"(?:!!!?\s*CONTRIBUTOR\s+TIER|This\s+is\s+Meta'?s?\s+contributor\s+tier|"
    r"This\s+model\s+is\s+in\s+Meta'?s?\s+contributor\s+tier)"
    r"[\s\S]*?(?=\n\n(?:Now|Last|Next|RESULT):|\n(?:Now|Last|Next|RESULT):|$)",
    re.I,
)
CRON_PROMPT_DUMP = re.compile(
    r"^#\s*Cron Job:[\s\S]*?(?=^##\s*Response\s*$|\Z)",
    re.I | re.M,
)

TOOL_ACTIVITY = re.compile(
    r"(?:^|\n)(?:→|•|\*)\s*(?:"
    r"run\s+terminal|"
    r"command\s+is\b|"
    r"tool\s*call|"
    r"(?:browser|web)_(?:navigate|extract|click|type|screenshot)|"
    r"file_(?:read|write|search)|"
    r"thinking|researching|analyzing|planning"
    r")",
    re.I | re.M,
)


def split_model(spec: str | None) -> tuple[str | None, str | None]:
    raw = (spec or "").strip()
    if not raw:
        return None, None
    if "/" not in raw:
        return None, raw
    prefix, _, model = raw.partition("/")
    mapped = PROVIDER_MAP.get(prefix.lower())
    if not mapped:
        return None, None
    return mapped, (model.strip() or None)


def parse_schedule(message: str) -> str | None:
    text = message or ""
    match = EVERY_N.search(text)
    if match:
        count = match.group(1)
        unit = match.group(2).lower()
        if unit.startswith("m"):
            return f"every {count}m"
        if unit.startswith("h"):
            return f"every {count}h"
        return f"every {count}d"
    if MORNING.search(text) or EVERY_DAY.search(text):
        return "0 9 * * *"
    return None


def parse_usage_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: data.get(key) for key in USAGE_KEYS if key in data}


def parse_session_id(text: str) -> str:
    match = SESSION_ID_RE.search(text or "")
    return match.group(1) if match else ""


def clean_hermes_text(text: str) -> str:
    lines: list[str] = []
    in_tool_block = False
    for line in (text or "").splitlines():
        stripped = ANSI.sub("", line).strip()
        if SESSION_NOISE.match(stripped) or stripped.lower().startswith("session_id:"):
            continue
        if re.search(r"<\|?DSML\|?tool_?calls?>", stripped, re.I):
            in_tool_block = True
            continue
        if in_tool_block:
            if re.search(r"</\|?DSML\|?tool_?calls?>", stripped, re.I):
                in_tool_block = False
            continue
        if TOOL_MARKUP.search(stripped) or re.search(r"<\|?/?DSML", stripped, re.I):
            continue
        if stripped.startswith("```") and "tool" in stripped.lower():
            continue
        if re.match(r"^(run\s+terminal|command\s+is\b|tool\s*call)", stripped, re.I):
            continue
        lines.append(ANSI.sub("", line))
    cleaned = "\n".join(lines).strip()
    cleaned = TOOL_MARKUP.sub("", cleaned).strip()
    cleaned = re.sub(r"<\|?/?DSML[^>]*>", "", cleaned, flags=re.I).strip()
    return _human_hermes_text(cleaned)


def _status_only(text: str) -> bool:
    rows = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return bool(rows) and all(re.match(r"^(Now|Last|Next|Blocker):", line, re.I) for line in rows)


def _human_hermes_text(text: str) -> str:
    cleaned = META_JUNK.sub("", text or "").strip()
    cleaned = re.sub(r"https?://dev\.meta\.ai/\S+", "", cleaned)
    cleaned = CRON_PROMPT_DUMP.sub("", cleaned).strip()
    response = re.search(r"^##\s*Response\s*$", cleaned, re.I | re.M)
    if response:
        body = cleaned[response.end() :].strip()
        if body and not re.match(r"^\[SILENT\]", body, re.I):
            cleaned = body
    result = re.search(r"^RESULT(?:\s*\([^)]*\))?\s*$", cleaned, re.I | re.M)
    if result:
        body = cleaned[result.end() :].strip()
        handoff = re.search(r"^HANDOFF\b", body, re.I | re.M)
        if handoff:
            body = body[: handoff.start()].strip()
        if body:
            cleaned = body
    if _status_only(cleaned):
        return cleaned
    kept: list[str] = []
    skipping = False
    for line in cleaned.splitlines():
        stripped = line.strip()
        if PACKET_LINE.match(stripped):
            skipping = bool(re.match(r"^(INDEX|BRAIN|TASK|STAFF|OPEN HANDOFFS|VAULT LOGINS):", stripped, re.I))
            continue
        if skipping:
            if not stripped:
                skipping = False
            continue
        if not stripped and not kept:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def chat_packet(name: str, status: str, task: str) -> str:
    who = (name or "Chief of Staff").strip() or "Chief of Staff"
    as_staff = who in {"Chief of Staff", "OpenBot"}
    parts = [
        "Reply like a person in chat. Short. Direct. Answer what they asked.",
        "You do not edit files yourself. If the board already routed work to an engine, do not invent diffs or pretend you ran tools.",
        "No RESULT. No tickets. No job cards. No session logs. No INDEX dump.",
        "Do not mention Now, Last, Next, Blocker, or Ticket unless they asked for status.",
        "Do not print session_id or Resumed session.",
        "If RECENT TELEGRAM is included, it is background only — answer the new board message, not an old thread.",
        "Never ask the operator to paste passwords, TOTP, API keys, or browser cookies into chat. Site logins go through the board vault (Keys → Site logins).",
        "If they ask to run all existing crons or get everything working, do not claim you fired the schedule. The live Hermes box already runs those jobs. This board will not stampede every cron from chat.",
    ]
    if as_staff:
        parts = [
            "You are Chief of Staff on a local OpenBot board.",
            "The human operator is above you. CEOs report to you.",
            "The operator can also open any CEO and talk to that CEO directly.",
            "You dispatch OpenCode (code) and Hermes Agent (Think, Research, Ops).",
            "Your job is triage, delegate, watch handoffs, collect, escalate — not specialist work.",
            "Before doing substantial work yourself, ask if a specialist should own it. If yes, say which lane.",
            "Do not hire a Bot for an app. Hire only when a repeating bottleneck needs an owner.",
        ] + parts
    else:
        title = who if who.lower().endswith("ceo") else f"{who} CEO"
        parts = [
            f"You are the {title} on a local OpenBot board.",
            "The operator is talking to you directly in this chat.",
            "You report to Chief of Staff, who runs the org above you.",
            "OpenCode edits your Code folder. Hermes Think / Research / Ops use your Hermes home.",
            "You own the outcome. Specialist lanes execute. Chat is not memory.",
        ] + parts
    brief = (status or "").strip()
    if brief:
        parts.extend(["", "STAFF (files, not chat):", brief[:3600]])
    parts.extend(["", (task or "").strip()])
    return "\n".join(parts)


def job_packet(preset: str, index: str, brain: str, task: str, extra: str = "") -> str:
    parts = [
        f"You are the {preset} engine on this CEO.",
        "The operator is in OpenBot Chat — with this CEO, or with Chief of Staff above them.",
        "Report a short RESULT back to this chat. Do not skip the operator.",
        "Chat is not memory. INDEX and this packet are the source of truth.",
        "Never print passwords, TOTP, or API keys in RESULT, chat, or INDEX.",
        "Name the engine that ran (Hermes Agent or OpenCode).",
        "",
        "INDEX:",
        (index or "(empty INDEX)")[:2500],
        "",
        "BRAIN:",
        (brain or "(empty brain)")[:1200],
        "",
        "TASK:",
        task.strip(),
    ]
    if extra:
        parts.extend(["", extra.strip()])
    parts.append(
        "Write a short RESULT with HANDOFF fields when you did specialist work. "
        "If TOTP, CAPTCHA, or a bank wall appears, stop with a line that is exactly LOGIN_WALL and the page URL. "
        "If VAULT LOGINS is in this packet, fill ordinary username/password fields from that file. Never print the file. "
        "Park send, publish, pay, delete, and sign."
    )
    return "\n".join(parts)


def _dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, _, value = raw.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and value:
            out[name] = value
    return out


def _hermes_env(home: str | Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    install = hermes_home()
    root = Path(home) if home else install
    env["HERMES_HOME"] = str(root)
    env["PATH"] = str(install / "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for name, value in _dotenv(install / ".env").items():
        env[name] = value
    if root.resolve() != install.resolve():
        for name, value in _dotenv(root / ".env").items():
            env[name] = value
    zen = env.get("OPENCODE_ZEN_API_KEY") or env.get("OPENCODE_API_KEY") or env.get("OPENCODE_GO_API_KEY")
    if zen:
        env.setdefault("OPENCODE_ZEN_API_KEY", zen)
        env.setdefault("OPENCODE_API_KEY", zen)
        env.setdefault("OPENCODE_GO_API_KEY", zen)
    return env


def _text_kwargs() -> dict:
    kwargs: dict = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _run(cmd: list[str], cwd: str | None, timeout: int, home: str | Path | None = None) -> tuple[int, str]:
    kwargs: dict = {
        "capture_output": True,
        "timeout": timeout,
        "check": False,
        "cwd": cwd,
        "env": _hermes_env(home),
        **_text_kwargs(),
    }
    try:
        proc = subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        return 127, "hermes not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "hermes timed out"
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out[-24000:]


def _needs_training_tier_confirm(model: str | None) -> bool:
    low = str(model or "").lower()
    return "contributor" in low or "muse-spark" in low


def _popen(
    cmd: list[str],
    cwd: str | None,
    home: str | Path | None = None,
    *,
    talk: bool = False,
    stdin_text: str | None = None,
):
    kwargs: dict = {
        "stdin": subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE if talk else subprocess.STDOUT,
        "cwd": cwd,
        "env": _hermes_env(home),
        "bufsize": 1,
        **_text_kwargs(),
    }
    proc = subprocess.Popen(cmd, **kwargs)
    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except OSError:
            pass
    return proc


def ensure_noninteractive_model_ack(home: str | Path | None = None) -> None:
    """Contributor-tier models (Muse Spark, etc.) refuse unattended CLI without this ack."""
    binary = which("hermes")
    if not binary:
        return
    root = Path(home).expanduser() if home else hermes_home()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    marker = root / ".openbot-training-tier-ack"
    if marker.is_file():
        return
    code, out = _run(
        [binary, "config", "set", "security.allow_data_training_tiers_noninteractive", "true"],
        None,
        45,
        home=root,
    )
    if code == 0:
        try:
            marker.write_text("ok\n", encoding="utf-8")
        except OSError:
            pass
        return
    # Fallback: patch config.yaml if hermes config set is unavailable.
    path = root / "config.yaml"
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return
    if "allow_data_training_tiers_noninteractive" in text:
        try:
            marker.write_text("ok\n", encoding="utf-8")
        except OSError:
            pass
        return
    block = (
        "\nsecurity:\n"
        "  allow_data_training_tiers_noninteractive: true\n"
    )
    if re.search(r"(?m)^security:\s*$", text):
        text = re.sub(
            r"(?m)^security:\s*$",
            "security:\n  allow_data_training_tiers_noninteractive: true",
            text,
            count=1,
        )
    else:
        text = (text.rstrip() + block) if text.strip() else block.lstrip()
    try:
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        marker.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass


def chat(
    prompt: str,
    *,
    cwd: str | None = None,
    model: str | None = None,
    toolsets: str | None = None,
    session: str | None = None,
    resume: str | None = None,
    timeout: int = HERMES_TIMEOUT,
    skills: str | None = None,
    on_delta=None,
    on_progress=None,
    cancel=None,
    run_id: str | None = None,
    home: str | Path | None = None,
    talk: bool = False,
) -> dict:
    binary = which("hermes")
    if not binary:
        return {
            "ok": False,
            "code": 127,
            "text": "Hermes Agent binary missing",
            "usage": {},
        }
    provider, model_id = split_model(model)
    ensure_noninteractive_model_ack(home)
    if talk:
        # Match Telegram's clean delivery: final answer only, no tool DSML
        # on stdout. hermes -z + --safe-mode is the board Chat path.
        timeout = TALK_RESUME_TIMEOUT if resume else min(timeout or TALK_TIMEOUT, TALK_TIMEOUT)
        if not provider or not model_id:
            return {
                "ok": False,
                "code": 2,
                "text": "Chat needs a seated model with a provider prefix. Open Models and pick Chat.",
                "usage": {},
            }
    with tempfile.TemporaryDirectory(prefix="openbot-hermes-", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        usage_path = root / "usage.json"
        if talk:
            # Talk mode: hermes -z scripted one-shot (final reply only, no tool previews).
            # Valid flags: --yolo, --ignore-rules, --usage-file, --provider, --model
            cmd = [
                binary,
                "-z",
                prompt,
                "--yolo",
                "--ignore-rules",
                "--usage-file",
                str(usage_path),
            ]
        else:
            # Job mode: full multi-turn session with toolsets and skills.
            # hermes chat does NOT support --usage-file (only hermes -z does).
            query = root / "query.txt"
            query.write_text(prompt, encoding="utf-8")
            cmd = [
                binary,
                "chat",
                "--oneshot",
                "--quiet",
                "--source",
                "openbot",
                "--max-turns",
                HERMES_MAX_TURNS,
                "--query-file",
                str(query),
                "--yolo",
            ]
            if toolsets:
                cmd.extend(["--toolsets", toolsets])
            if skills:
                cmd.extend(["--skills", skills])
            if resume:
                cmd.extend(["--resume", resume])
            elif session:
                cmd.extend(["--continue", session, "--create-if-missing"])
        if provider and model_id:
            cmd.extend(["--provider", provider, "-m", model_id])
        elif model_id:
            cmd.extend(["-m", model_id])
        try:
            confirm = "y\n" if _needs_training_tier_confirm(model) else None
            proc = _popen(
                cmd,
                str(root) if talk else cwd,
                home=home,
                talk=talk,
                stdin_text=confirm,
            )
        except FileNotFoundError:
            return {"ok": False, "code": 127, "text": "hermes not on PATH", "usage": {}}
        if run_id:
            from .live import attach

            attach(run_id, proc)
        chunks: list[str] = []
        deadline = time.time() + timeout if timeout else None
        last_progress = time.time()
        heartbeat_sent = False
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    proc.terminate()
                    return {
                        "ok": False,
                        "code": 130,
                        "text": clean_hermes_text("".join(chunks)) or "Stopped.",
                        "usage": parse_usage_file(usage_path),
                        "stopped": True,
                    }
                now = time.time()
                if deadline and now > deadline:
                    proc.kill()
                    return {
                        "ok": False,
                        "code": 124,
                        "text": clean_hermes_text("".join(chunks)) or "hermes timed out",
                        "usage": parse_usage_file(usage_path),
                    }
                # Heartbeat: emit "working" chip if >5s without activity
                if on_progress and not talk and (now - last_progress) > 5.0 and not heartbeat_sent:
                    try:
                        on_progress("Hermes · working")
                        heartbeat_sent = True
                    except Exception:
                        pass
                # Non-blocking read with 1s timeout so heartbeat can fire
                if proc.stdout and os.name != "nt":
                    # Unix: use select for non-blocking read
                    ready, _, _ = select.select([proc.stdout], [], [], 1.0)
                    if ready:
                        try:
                            line = proc.stdout.readline()
                        except (UnicodeDecodeError, ValueError):
                            line = ""
                    else:
                        line = ""
                else:
                    # Windows: no select on file objects, use short readline timeout
                    try:
                        line = proc.stdout.readline() if proc.stdout else ""
                    except (UnicodeDecodeError, ValueError):
                        line = ""
                    if not line:
                        time.sleep(0.05)
                if line:
                    chunks.append(line)
                    # Detect tool activity and emit progress
                    stripped = ANSI.sub("", line).strip()
                    if on_progress and not talk and stripped:
                        tool_match = None
                        if re.search(r"run\s+terminal", stripped, re.I):
                            tool_match = "terminal"
                        elif re.search(r"command\s+is\b", stripped, re.I):
                            tool_match = "command"
                        elif re.search(r"tool\s*call", stripped, re.I):
                            tool_match = "tool"
                        elif re.search(r"(?:browser|web)_(?:navigate|extract|click|type|screenshot)", stripped, re.I):
                            tool_match = "browser"
                        elif re.search(r"file_(?:read|write|search)", stripped, re.I):
                            tool_match = "file"
                        elif re.search(r"\b(?:thinking|researching|analyzing|planning)\b", stripped, re.I):
                            tool_match = stripped.split()[0] if stripped else "working"
                        if tool_match:
                            try:
                                on_progress(f"Hermes · {tool_match}")
                                last_progress = now
                                heartbeat_sent = False
                            except Exception:
                                pass
                    if on_delta:
                        visible = clean_hermes_text(line)
                        if visible:
                            try:
                                on_delta(visible if visible.endswith("\n") else visible + "\n")
                            except Exception:
                                pass
                    continue
                if proc.poll() is not None:
                    rest = proc.stdout.read() if proc.stdout else ""
                    if rest:
                        chunks.append(rest)
                        if on_delta:
                            visible = clean_hermes_text(rest)
                            if visible:
                                try:
                                    on_delta(visible)
                                except Exception:
                                    pass
                    break
            code = proc.returncode or 0
        except OSError as err:
            return {"ok": False, "code": 1, "text": str(err), "usage": {}}
        err_text = ""
        if talk and proc.stderr:
            try:
                err_text = (proc.stderr.read() or "").strip()
            except (OSError, ValueError):
                err_text = ""
        raw = "".join(chunks).strip() or "(no output)"
        cleaned = clean_hermes_text(raw)
        if cleaned:
            text = cleaned
        elif TOOL_MARKUP.search(raw) or re.search(r"<\|?/?DSML", raw or "", re.I) or raw == "(no output)":
            text = ""
        else:
            text = raw[-24000:]
        if not text.strip() and err_text:
            text = clean_hermes_text(err_text) or err_text[-1200:]
        usage = parse_usage_file(usage_path)
        return {
            "ok": code == 0 and bool((cleaned or "").strip()),
            "code": code if (cleaned or "").strip() else (code or 1),
            "text": (text or "(no output)")[-24000:],
            "usage": usage,
            "engine": "Hermes Agent",
            "session": resume or session,
            "session_id": str(usage.get("session_id") or parse_session_id(raw) or resume or ""),
            "raw_log": raw,
        }


def cron_create(
    schedule: str,
    prompt: str,
    name: str,
    cwd: str | None = None,
    home: str | Path | None = None,
) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    cmd = [binary, "cron", "create", schedule, prompt, "--name", name, "--deliver", "local"]
    code, out = _run(cmd, cwd, 60, home=home)
    if code != 0:
        cmd = [binary, "cron", "create", schedule, prompt, "--name", name]
        code, out = _run(cmd, cwd, 60, home=home)
    return {"ok": code == 0, "code": code, "text": out.strip() or "(no output)", "schedule": schedule}


def import_backup(zip_path: str | Path, home: str | Path) -> dict:
    """Official `hermes import` into an isolated HERMES_HOME. Never the default home."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    archive = Path(zip_path).expanduser()
    dest = Path(home)
    dest.mkdir(parents=True, exist_ok=True)
    code, out = _run([binary, "import", str(archive), "--force"], None, 600, home=dest)
    return {
        "ok": code == 0,
        "code": code,
        "text": (out or "").strip() or "(no output)",
        "home": str(dest),
    }


def cron_list(cwd: str | None = None, home: str | Path | None = None) -> dict:
    """List Hermes cron jobs. Prefers JSON output; falls back to robust table parsing."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing", "jobs": [], "crons": []}
    
    # Try JSON output first (if supported)
    code, out = _run([binary, "cron", "list", "--json"], cwd, 30, home=home)
    if code == 0 and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, list):
                return {"ok": True, "code": 0, "text": out.strip(), "jobs": data}
            elif isinstance(data, dict) and "jobs" in data:
                return {"ok": True, "code": 0, "text": out.strip(), "jobs": data.get("jobs", [])}
        except json.JSONDecodeError:
            pass
    
    # Fallback: try regular list and parse table carefully
    code, out = _run([binary, "cron", "list"], cwd, 30, home=home)
    text = out.strip() or "(no cron jobs)"
    
    # Parse table robustly: only extract real job data
    jobs = _parse_cron_table(text)
    
    return {"ok": code == 0, "code": code, "text": text, "jobs": jobs}


def is_valid_job_id(job_id: str) -> bool:
    """Validate that a string looks like a real job ID (hex-like), not label words.
    
    Real Hermes job IDs are hex-like strings (12+ hex chars).
    Reject label words like "Name:", "Schedule:", "Next", "Execution:", "Skills:".
    
    Use this guard before operating on job IDs from cron list output.
    """
    if not job_id or len(job_id) < 12:
        return False
    
    # Reject common label words that appear in multi-line cron output
    label_words = {
        "Name:", "Schedule:", "Next", "Execution:", "Skills:", "Deliver:",
        "Repeat:", "Workdir:", "Dispatch:", "Last", "Status:", "ID", "Created",
        "│", "├", "┤", "┬", "┴", "┼", "[active]", "[paused]"
    }
    if job_id in label_words or job_id.endswith(":"):
        return False
    
    # Must be primarily hex-like (allow some punctuation for real IDs like "job-abc123")
    hex_count = sum(1 for c in job_id if c in "0123456789abcdefABCDEF")
    if hex_count < 8:  # At least 8 hex chars
        return False
    
    return True


def _parse_cron_table(text: str) -> list[dict]:
    """Parse hermes cron list output into structured jobs.
    
    Real Hermes format is MULTI-LINE blocks:
    
      7cb2a72c1cc8 [active]
        Name:      form-pipeline-health
        Schedule:  0 14 * * *
        Repeat:    ∞
        Next run:  2026-09-06T14:00:00+00:00
        Deliver:   origin
    
    Job ID = hex ID on the [active]/[paused] line.
    Name/Schedule/Deliver are indented labeled fields.
    NEVER treat "Name:", "Schedule:", "Next", "Execution:", "Skills:" as IDs.
    """
    if not text or "No cron" in text or "no cron" in text:
        return []
    
    jobs = []
    lines = text.strip().split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Look for job ID line: "<hex-id> [active]" or "<hex-id> [paused]"
        # These lines are NOT indented (or only lightly indented with 2 spaces)
        if ("[active]" in line or "[paused]" in line) and not line.startswith("    "):
            # Extract job ID (everything before [active]/[paused])
            parts = line.split()
            job_id = None
            for part in parts:
                if part.startswith("["):
                    break
                if is_valid_job_id(part):
                    job_id = part
                    break
            
            if not job_id:
                i += 1
                continue
            
            # Now parse the indented fields that follow
            name = None
            schedule = None
            deliver = None
            
            i += 1
            while i < len(lines):
                field_line = lines[i]
                
                # Check if this line belongs to the current job block
                # Job block fields are indented with at least 4 spaces
                if field_line.strip() and not field_line.startswith("    "):
                    # This line is not indented enough = new job block starting
                    break
                
                stripped = field_line.strip()
                if not stripped:
                    # Empty line - continue but don't break
                    i += 1
                    continue
                
                # Parse "Label: value" format
                if ":" in stripped:
                    label, _, value = stripped.partition(":")
                    label = label.strip()
                    value = value.strip()
                    
                    if label.lower() == "name":
                        name = value
                    elif label.lower() == "schedule":
                        schedule = value
                    elif label.lower() == "deliver":
                        deliver = value
                
                i += 1
            
            # Only add if we have at least name and schedule
            if name and schedule:
                jobs.append({
                    "id": job_id,
                    "name": name,
                    "schedule": schedule,
                    "deliver": deliver,
                })
        else:
            i += 1
    
    return jobs


def cron_runs(
    job_id: str | None = None,
    limit: int = 20,
    cwd: str | None = None,
    home: str | Path | None = None,
) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    cmd = [binary, "cron", "runs", "--limit", str(max(1, min(int(limit), 500)))]
    if job_id:
        cmd.append(job_id)
    code, out = _run(cmd, cwd, 30, home=home)
    return {"ok": code == 0, "code": code, "text": out.strip() or ""}


def cron_run(job_id: str, home: str | Path | None = None) -> dict:
    """Official `hermes cron run`. Queues that job on the next scheduler tick."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    jid = str(job_id or "").strip()
    if not is_valid_job_id(jid):
        return {"ok": False, "code": 400, "text": "bad job id"}
    code, out = _run([binary, "cron", "run", "--accept-hooks", jid], None, 60, home=home)
    return {"ok": code == 0, "code": code, "text": out.strip() or "(no output)", "id": jid}


SAA_LIVE_PROJECT = os.environ.get("OPENBOT_SAA_HERMES_PROJECT", "87dc0fc7-9858-4e63-8c89-d9af0533b470")
SAA_LIVE_SERVICE = os.environ.get("OPENBOT_SAA_HERMES_SERVICE", "SAA Homes Hermes")
SAA_LIVE_ENV = os.environ.get("OPENBOT_SAA_HERMES_ENV", "production")
SAA_CRON_SKIP = frozenset({
    "7bdaa3b6fb9e",  # conversion-surge
    "1ee83ff221a4",  # competitor-content-watch
    "0f3bc267a48e",  # city-audit-batch-4
})
SAA_GO_MODEL = "deepseek-v4-flash"
SAA_GO_PROVIDER = "opencode-go"
SAA_CRON_PIN_GO = frozenset({
    "dadd8574d37f",  # citation-submission-layer1
    "72d59f31d8d4",  # batch-2-citystatsband-blogs
    "2148be2f2516",  # erie-video-blog-strengthen
    "a68690276a73",  # batch1-tier-s-remaining-fixes
})
# Gateway-owned catch-up only. Do not SSH-fire. Skip jobs stay paused.
SAA_CATCHUP_IDS = (
    "38041c7a6501",  # geo-citation-audit
    "77bfe1c9f7a1",  # content-gap-offense
    "dadd8574d37f",  # citation-submission-layer1
    "3e0cbb9af8f6",  # keyword-opportunity-engine
    "6fc2243d4eb1",  # city-audit-batch-2
    "b5896a99b0a7",  # monthly-market-blog
    "56999ea3827f",  # monthly-market-digital-press
    "72d59f31d8d4",  # batch-2-citystatsband-blogs
    "2148be2f2516",  # erie-video-blog-strengthen
    "a68690276a73",  # batch1-tier-s-remaining-fixes
    "2eb1f17f9599",  # city-audit-batch-3
)
_SAA_OVERLAY_KEYS = (
    "last_status",
    "last_error",
    "last_run_at",
    "next_run_at",
    "fire_claim",
    "state",
    "enabled",
)
_SAA_OVERLAY_MARK_START = "OVERLAY_JSON_START"
_SAA_OVERLAY_MARK_END = "OVERLAY_JSON_END"
_SAA_OVERLAY_REMOTE = r"""
import glob, json, os
from datetime import datetime, timezone
path = "/opt/data/cron/jobs.json"
data = json.loads(open(path, encoding="utf-8").read())
now = datetime.now(timezone.utc)
out = []
for job in data.get("jobs") or []:
    if not isinstance(job, dict) or not job.get("id"):
        continue
    jid = str(job.get("id"))
    sched = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    status = str(job.get("last_status") or "")
    when = str(job.get("last_run_at") or "")
    fresh = False
    if when:
        try:
            stamp = datetime.fromisoformat(when.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            fresh = (now - stamp.astimezone(timezone.utc)).total_seconds() <= 48 * 3600
        except ValueError:
            fresh = False
    row = {
        "id": jid,
        "name": str(job.get("name") or jid),
        "last_status": job.get("last_status"),
        "last_error": job.get("last_error"),
        "last_run_at": job.get("last_run_at"),
        "next_run_at": job.get("next_run_at"),
        "fire_claim": job.get("fire_claim"),
        "state": job.get("state"),
        "enabled": job.get("enabled"),
        "model": job.get("model"),
        "provider": job.get("provider"),
        "schedule": str(job.get("schedule_display") or sched.get("display") or sched.get("expr") or ""),
    }
    need = fresh or ("error" in status.lower()) or ("fail" in status.lower())
    folder = "/opt/data/cron/output/" + jid
    files = sorted(glob.glob(folder + "/*.md"), reverse=True) if need else []
    if files:
        row["last_result"] = open(files[0], encoding="utf-8", errors="replace").read()[:4000]
        row["result_file"] = os.path.basename(files[0])
    out.append(row)
print("OVERLAY_JSON_START")
print(json.dumps({"jobs": out}))
print("OVERLAY_JSON_END")
"""
_overlay_miss_logged = False


def railway_ssh_identity() -> str:
    env_path = os.environ.get("OPENBOT_RAILWAY_SSH_IDENTITY", "").strip()
    if env_path:
        return env_path
    key = os.environ.get("OPENBOT_RAILWAY_SSH_KEY", "").strip()
    if key:
        path = Path("/tmp/openbot-railway-ssh")
        body = key.replace("\\n", "\n") if "BEGIN" in key else key
        if (not path.is_file()) or path.read_text(encoding="utf-8", errors="replace") != body:
            path.write_text(body, encoding="utf-8")
            os.chmod(path, 0o600)
        return str(path)
    return str(Path.home() / ".ssh" / "id_ed25519_railway")


def apply_cron_status_overlay(home: str | Path | None, overlay: list[dict]) -> int:
    """Copy live last_status fields onto a board home. Does not rewrite prompts."""
    if not home:
        return 0
    path = Path(home) / "cron" / "jobs.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return 0
    by_id = {
        str(row.get("id") or ""): row
        for row in overlay
        if isinstance(row, dict) and row.get("id")
    }
    updated = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        src = by_id.get(str(job.get("id") or ""))
        if not src:
            continue
        for key in _SAA_OVERLAY_KEYS:
            if key in src:
                job[key] = src.get(key)
        updated += 1
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return updated


def railway_cmd() -> list[str]:
    found = shutil.which("railway")
    if found and not str(found).lower().endswith(".cmd"):
        return [found]
    js = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@railway" / "cli" / "bin" / "railway.js"
    if js.is_file():
        return ["node", str(js)]
    linux = Path("/usr/local/bin/railway")
    if linux.is_file():
        return [str(linux)]
    if found:
        return [found]
    return []


def saa_ssh_payload(remote: list[str]) -> str:
    """Quote argv so Railway's `bash -c <joined>` keeps python -c / redirects intact."""
    return " ".join(shlex.quote(part) for part in remote)


def saa_live_ssh(
    remote: list[str],
    timeout: int = 30,
    stdin: str | None = None,
) -> subprocess.CompletedProcess:
    binary = railway_cmd()
    if not binary:
        raise FileNotFoundError("railway")
    identity = railway_ssh_identity()
    cmd = [
        *binary,
        "ssh",
        "--identity-file",
        identity,
        "--project",
        SAA_LIVE_PROJECT,
        "--environment",
        SAA_LIVE_ENV,
        "--service",
        SAA_LIVE_SERVICE,
        "--",
        saa_ssh_payload(remote),
    ]
    payload = stdin
    if payload is not None:
        payload = payload.replace("\r\n", "\n").replace("\r", "\n")
    ran = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        input=None if payload is None else payload.encode("utf-8"),
    )
    return subprocess.CompletedProcess(
        ran.args,
        ran.returncode,
        (ran.stdout or b"").decode("utf-8", "replace"),
        (ran.stderr or b"").decode("utf-8", "replace"),
    )


def saa_overlay_cache_path() -> Path:
    from .store import ROOT

    return ROOT / "saa-live-overlay.json"


def load_saa_overlay_cache() -> list[dict]:
    path = saa_overlay_cache_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    return [row for row in jobs if isinstance(row, dict) and row.get("id")]


def save_saa_overlay_cache(overlay: list[dict]) -> None:
    if not overlay:
        return
    path = saa_overlay_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "jobs": overlay,
    }
    path.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")


def _overlay_jobs_from_text(text: str) -> list[dict]:
    raw = str(text or "")
    start = raw.find(_SAA_OVERLAY_MARK_START)
    end = raw.find(_SAA_OVERLAY_MARK_END)
    if start >= 0 and end > start:
        raw = raw[start + len(_SAA_OVERLAY_MARK_START) : end]
    brace = raw.find("{")
    if brace < 0:
        return []
    try:
        data = json.loads(raw[brace:])
    except json.JSONDecodeError:
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    out = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        out.append(job)
    return out


def _mark_overlay_live(overlay: list[dict], live_ids: set[str] | None = None) -> list[dict]:
    ids = live_ids if live_ids is not None else set()
    if live_ids is None and overlay and railway_cmd():
        try:
            ran = saa_live_ssh(["hermes", "cron", "runs", "--limit", "25"], timeout=40)
            ids = set(parse_hermes_running_job_ids((ran.stdout or "") + "\n" + (ran.stderr or "")))
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            ids = set()
    out = []
    for row in overlay or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["live"] = str(item.get("id") or "") in ids
        out.append(item)
    return out


def dump_saa_live_cron_overlay() -> list[dict]:
    cached = load_saa_overlay_cache()
    overlay = cached
    if railway_cmd():
        try:
            wrote = saa_live_ssh(["tee", "/tmp/saa-overlay-dump.py"], timeout=20, stdin=_SAA_OVERLAY_REMOTE)
            if wrote.returncode == 0:
                ran = saa_live_ssh(["python3", "/tmp/saa-overlay-dump.py"], timeout=60)
                dumped = _overlay_jobs_from_text((ran.stdout or "") + "\n" + (ran.stderr or ""))
                if dumped:
                    overlay = dumped
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            overlay = cached
        overlay = _mark_overlay_live(overlay)
        if overlay:
            save_saa_overlay_cache(overlay)
            return overlay
    return overlay or cached


def overlay_to_cron_rows(overlay: list[dict]) -> list[dict]:
    """Shape live overlay jobs like read_home_crons so the board can count them."""
    out = []
    for row in overlay or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(_cron_row_payload(row, str(row.get("last_result") or "")))
    return out


def merge_saa_cron_rows(local: list[dict], overlay: list[dict]) -> list[dict]:
    live_rows = overlay_to_cron_rows(overlay)
    if not live_rows:
        return local
    by_local = {str(row.get("id") or ""): row for row in local or []}
    seen: set[str] = set()
    out: list[dict] = []
    for row in live_rows:
        jid = str(row.get("id") or "")
        seen.add(jid)
        loc = by_local.get(jid) or {}
        if not str(row.get("last_result") or "").strip() and loc.get("last_result"):
            merged = dict(row)
            result = str(loc.get("last_result") or "")
            merged["last_result"] = result
            outcome, nxt = cron_outcome(merged.get("last_status") or "", result, merged.get("last_error") or "")
            merged["outcome"] = outcome
            merged["next_action"] = nxt
            out.append(merged)
        else:
            out.append(row)
    for row in local or []:
        jid = str(row.get("id") or "")
        if jid and jid not in seen:
            out.append(row)
    return out


def sync_saa_live_crons(home: str | Path | None) -> dict:
    overlay = dump_saa_live_cron_overlay()
    if not overlay:
        return {"ok": False, "updated": 0, "error": "live overlay empty"}
    updated = apply_cron_status_overlay(home, overlay) if home else 0
    return {"ok": True, "updated": updated, "live": True, "jobs": len(overlay)}


def overlay_saa_live_background(interval: int | None = None) -> None:
    """Keep the SAA Homes board copy of jobs.json in step with live Hermes."""
    global _overlay_miss_logged
    delay = interval if interval is not None else int(os.environ.get("OPENBOT_SAA_OVERLAY_INTERVAL", "12") or "12")
    time.sleep(3)
    while True:
        try:
            from .org import project_tools

            home = str((project_tools("saa-homes") or {}).get("hermes_home") or "").strip()
            sync_saa_live_crons(home)
        except FileNotFoundError:
            if not _overlay_miss_logged:
                print("[openbot] saa live overlay: railway CLI missing; using cached live jobs", flush=True)
                _overlay_miss_logged = True
        except Exception as err:
            print(f"[openbot] saa live overlay: {err}", flush=True)
        time.sleep(max(8, delay))


def saa_live_cron_run(job_id: str) -> dict:
    """Start a job on live Railway SAA Hermes, detached from the SSH session."""
    jid = str(job_id or "").strip()
    if not is_valid_job_id(jid):
        return {"ok": False, "code": 400, "text": "bad job id"}
    if jid in SAA_CRON_SKIP:
        return {"ok": False, "code": 400, "text": "skipped", "id": jid}
    script = (
        "#!/bin/sh\n"
        f"setsid -f hermes cron run --accept-hooks {jid} "
        f">/tmp/cron-{jid}.log 2>&1 < /dev/null\n"
        "echo QUEUED\n"
        "exit 0\n"
    )
    path = f"/tmp/fire-{jid}.sh"
    try:
        wrote = saa_live_ssh(["tee", path], timeout=20, stdin=script)
        if wrote.returncode != 0:
            err = ((wrote.stderr or "") + "\n" + (wrote.stdout or "")).strip()
            return {
                "ok": False,
                "code": wrote.returncode,
                "text": err[-400:] or "tee failed",
                "id": jid,
            }
        ran = saa_live_ssh(["sh", path], timeout=20)
    except (subprocess.TimeoutExpired, OSError) as err:
        return {"ok": False, "code": 1, "text": str(err)[:200], "id": jid}
    out = ((ran.stdout or "") + "\n" + (ran.stderr or "")).strip()
    queued = "QUEUED" in out
    return {
        "ok": ran.returncode == 0 and queued,
        "code": ran.returncode,
        "text": out[-400:] or "(no output)",
        "id": jid,
        "live": True,
    }


def pin_saa_live_jobs_json(data: dict) -> list[str]:
    """Pin leftover empty-model jobs to OpenCode Go flash. Does not touch prompts or Telegram deliver."""
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    changed: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        jid = str(job.get("id") or "")
        if jid not in SAA_CRON_PIN_GO:
            continue
        if str(job.get("model") or "") and str(job.get("provider") or ""):
            continue
        job["model"] = SAA_GO_MODEL
        job["provider"] = SAA_GO_PROVIDER
        changed.append(jid)
    return changed


def pause_saa_live_skips() -> dict:
    """Pause spend/skip jobs on live Railway. Does not migrate Telegram off origin."""
    paused: list[str] = []
    errors: list[str] = []
    for jid in sorted(SAA_CRON_SKIP):
        try:
            ran = saa_live_ssh(["hermes", "cron", "pause", jid], timeout=40)
        except (subprocess.TimeoutExpired, OSError) as err:
            errors.append(f"{jid}:{err}")
            continue
        if ran.returncode == 0:
            paused.append(jid)
        else:
            errors.append(jid)
    return {"ok": not errors, "paused": paused, "errors": errors, "live": True}


def pin_saa_live_go_jobs() -> dict:
    """Write Go flash onto leftover empty-model jobs in live jobs.json."""
    script = (
        "import json\n"
        "path='/opt/data/cron/jobs.json'\n"
        "pins=" + json.dumps(sorted(SAA_CRON_PIN_GO)) + "\n"
        "model=" + json.dumps(SAA_GO_MODEL) + "\n"
        "provider=" + json.dumps(SAA_GO_PROVIDER) + "\n"
        "data=json.loads(open(path,encoding='utf-8').read())\n"
        "changed=[]\n"
        "for job in data.get('jobs') or []:\n"
        "    jid=str(job.get('id') or '')\n"
        "    if jid not in pins:\n"
        "        continue\n"
        "    if str(job.get('model') or '') and str(job.get('provider') or ''):\n"
        "        continue\n"
        "    job['model']=model\n"
        "    job['provider']=provider\n"
        "    changed.append(jid)\n"
        "open(path,'w',encoding='utf-8').write(json.dumps(data, indent=2)+'\\n')\n"
        "print('PINNED', ','.join(changed))\n"
    )
    path = "/tmp/pin-saa-go.py"
    try:
        wrote = saa_live_ssh(["tee", path], timeout=20, stdin=script)
        if wrote.returncode != 0:
            return {"ok": False, "pinned": [], "text": "tee failed", "live": True}
        ran = saa_live_ssh(["python3", path], timeout=40)
    except (subprocess.TimeoutExpired, OSError) as err:
        return {"ok": False, "pinned": [], "text": str(err)[:200], "live": True}
    out = ((ran.stdout or "") + "\n" + (ran.stderr or "")).strip()
    pinned = []
    if "PINNED" in out:
        rest = out.split("PINNED", 1)[-1].strip()
        pinned = [part for part in rest.split(",") if part]
    return {
        "ok": ran.returncode == 0 and "PINNED" in out,
        "pinned": pinned,
        "text": out[-400:],
        "live": True,
    }


def align_saa_live_cron_config() -> dict:
    """Pause skip jobs and pin leftover empty-model jobs on live Hermes. No redeploy."""
    paused = pause_saa_live_skips()
    pinned = pin_saa_live_go_jobs()
    return {
        "ok": bool(paused.get("ok") and pinned.get("ok")),
        "paused": paused.get("paused") or [],
        "pinned": pinned.get("pinned") or [],
        "live": True,
    }


def nudge_saa_job_due(data: dict, job_id: str, when: str) -> bool:
    """Point one live job at now so the gateway scheduler owns it. Does not touch prompts or deliver."""
    jid = str(job_id or "").strip()
    if not jid or jid in SAA_CRON_SKIP:
        return False
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return False
    for job in jobs:
        if not isinstance(job, dict) or str(job.get("id") or "") != jid:
            continue
        if job.get("enabled") is False or str(job.get("state") or "") == "paused":
            return False
        job["next_run_at"] = when
        job["fire_claim"] = None
        return True
    return False


def saa_live_nudge_due(job_id: str) -> dict:
    """Ask the live gateway to run this job on the next tick. Do not hermes cron run over SSH."""
    jid = str(job_id or "").strip()
    if not is_valid_job_id(jid):
        return {"ok": False, "code": 400, "text": "bad job id"}
    if jid in SAA_CRON_SKIP:
        return {"ok": False, "code": 400, "text": "skipped", "id": jid}
    when = datetime.now(timezone.utc).isoformat()
    script = (
        "import json\n"
        "path='/opt/data/cron/jobs.json'\n"
        "jid=" + json.dumps(jid) + "\n"
        "when=" + json.dumps(when) + "\n"
        "skip=" + json.dumps(sorted(SAA_CRON_SKIP)) + "\n"
        "data=json.loads(open(path,encoding='utf-8').read())\n"
        "ok=False\n"
        "for job in data.get('jobs') or []:\n"
        "    if str(job.get('id') or '')!=jid:\n"
        "        continue\n"
        "    if jid in skip or job.get('enabled') is False or str(job.get('state') or '')=='paused':\n"
        "        break\n"
        "    job['next_run_at']=when\n"
        "    job['fire_claim']=None\n"
        "    ok=True\n"
        "    break\n"
        "if ok:\n"
        "    open(path,'w',encoding='utf-8').write(json.dumps(data, indent=2)+'\\n')\n"
        "print('NUDGED' if ok else 'SKIP')\n"
    )
    path = f"/tmp/nudge-{jid}.py"
    try:
        wrote = saa_live_ssh(["tee", path], timeout=20, stdin=script)
        if wrote.returncode != 0:
            return {"ok": False, "code": wrote.returncode, "text": "tee failed", "id": jid}
        ran = saa_live_ssh(["python3", path], timeout=40)
    except (subprocess.TimeoutExpired, OSError) as err:
        return {"ok": False, "code": 1, "text": str(err)[:200], "id": jid}
    out = ((ran.stdout or "") + "\n" + (ran.stderr or "")).strip()
    return {
        "ok": ran.returncode == 0 and "NUDGED" in out,
        "code": ran.returncode,
        "text": out[-400:] or "(no output)",
        "id": jid,
        "live": True,
        "due": when,
    }


def saa_catchup_next(overlay: list[dict]) -> str:
    """Next leftover job the live gateway should own. Empty if caught up or a run is in flight."""
    rows = [row for row in overlay if isinstance(row, dict)]
    if any(row.get("live") is True for row in rows):
        return ""
    by_id = {str(row.get("id") or ""): row for row in rows}
    for jid in SAA_CATCHUP_IDS:
        if jid in SAA_CRON_SKIP:
            continue
        row = by_id.get(jid) or {}
        if row.get("enabled") is False or str(row.get("state") or "") == "paused":
            continue
        if _claim_is_live(row) and not _claim_is_stale(row):
            return ""
        status = str(row.get("last_status") or "").strip().lower()
        if status in {"", "never", "error", "fail", "failed"}:
            return jid
    return ""


def _cron_is_prompt_dump(text: str) -> bool:
    raw = str(text or "")
    return bool(
        re.search(r"^#\s*Cron Job:", raw, re.I | re.M)
        and re.search(r"^##\s*Prompt\b", raw, re.I | re.M)
        and not re.search(r"^##\s*Response\s*$", raw, re.I | re.M)
    )


def _cron_report_body(text: str) -> str:
    raw = str(text or "")
    if _cron_is_prompt_dump(raw):
        return ""
    match = re.search(r"^## Response\s*$", raw, re.M)
    body = raw[match.end() :].strip() if match else raw.strip()
    return body


CRON_TITLES = {
    "form-pipeline-health": "Site and form check",
    "conversion-surge": "Conversion fixes",
    "monthly-market-blog": "Monthly market blog",
    "geo-citation-audit": "Citation audit",
    "indexation-patrol": "Indexation patrol",
    "daily-ranking-strike": "Daily rankings",
    "competitor-content-watch": "Competitor watch",
    "daily-done-digest": "Daily wrap-up",
    "seo-execute-queue": "SEO fix queue",
    "weekly-war-room": "Weekly war room",
    "city-deep-dive-rotation": "City deep dive",
    "content-gap-offense": "Content gaps",
    "backlink-outreach-research": "Backlink research",
    "schema-technical-audit": "Schema audit",
    "internal-link-architecture": "Internal links",
    "gbp-local-pack-audit": "Google Business Profile",
    "blog-content-calendar": "Blog calendar",
    "market-dominance-review": "Market review",
    "social-weekly-content": "Weekly social pack",
    "weekly-operator-schedule": "Weekly operator plan",
    "lead-attribution-brief": "Lead attribution",
    "idx-listings-hourly-sync": "Hourly listing sync",
    "idx-listings-daily-full-sync": "Daily listing sync",
}


def cron_title(name: str) -> str:
    raw = str(name or "").strip()
    if raw in CRON_TITLES:
        return CRON_TITLES[raw]
    return re.sub(r"[-_]+", " ", raw).strip().capitalize() or "Scheduled check"


def cron_outcome(status: str, result: str, error: str = "") -> tuple[str, str]:
    """Plain outcome + next action from a cron status and report body."""
    body = _cron_report_body(result)
    err = re.sub(r"\s+", " ", str(error or "")).strip()
    blob = f"{body} {status} {err}"
    st = str(status or "").strip().lower()
    if re.search(r"\[silent\]", body, re.I):
        return "Healthy. Nothing new to report.", "No action. It will run again on schedule."
    if re.search(r"error|fail", st):
        if re.search(r"gateway shutdown", blob, re.I):
            return (
                "Failed. The Hermes gateway stopped mid-run.",
                "Retry this job on the live box. Do not fire the whole set.",
            )
        if re.search(r"\b401\b", blob):
            return (
                "Failed. A live endpoint returned 401.",
                "Fix the credential for that job, then retry it alone.",
            )
        hint = err[:160] or "The last run did not finish."
        return f"Failed. {hint}", "Open this job, then retry or fix the cause."
    if not body:
        if st in {"ok", "success", "completed", "succeeded"}:
            return "Healthy on the live box.", "No action. It will run again on schedule."
        return "Ran, but this board does not have the full report yet.", "Wait for the next copy, or check Telegram."
    first = re.sub(r"\s+", " ", body.splitlines()[0])[:140]
    return first, "Read the note below, then do the next step it names."


def _parse_cron_when(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


_CRON_RUNNING = re.compile(r"running|in.?progress|started|firing|claimed", re.I)
_CRON_PAUSED = re.compile(r"paused|disabled", re.I)
_CRON_DONE = re.compile(r"^(ok|error|fail|failed|unknown|skipped|success)$", re.I)


def _claim_at(row: dict) -> datetime | None:
    claim = row.get("fire_claim")
    if isinstance(claim, dict):
        return _parse_cron_when(str(claim.get("at") or ""))
    return None


def _claim_is_live(row: dict) -> bool:
    """A fire_claim newer than last_run_at is a retry in flight. last_status stays the previous run."""
    if row.get("enabled") is False:
        return False
    claim = row.get("fire_claim")
    if not claim and not row.get("claimed"):
        return False
    claim_at = _claim_at(row)
    last = _parse_cron_when(str(row.get("last_run_at") or ""))
    if claim_at and last:
        return claim_at > last
    if claim_at and last is None:
        return True
    return False


def _claim_is_stale(row: dict, max_age: float = 20 * 60) -> bool:
    """SSH-owned claims that never got last_run_at should not block gateway catch-up."""
    claim_at = _claim_at(row)
    if not claim_at:
        return False
    return (datetime.now(timezone.utc) - claim_at).total_seconds() > max_age


def _cron_digest_item(row: dict, enabled: bool) -> dict:
    report = re.sub(r"\s+", " ", str(row.get("last_result") or "")).strip()
    return {
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or row.get("id") or "cron"),
        "title": cron_title(str(row.get("name") or "")),
        "last_run_at": str(row.get("last_run_at") or ""),
        "next_run_at": str(row.get("next_run_at") or ""),
        "last_status": str(row.get("last_status") or ""),
        "state": str(row.get("state") or ""),
        "schedule": str(row.get("schedule") or ""),
        "outcome": str(row.get("outcome") or ""),
        "next_action": str(row.get("next_action") or ""),
        "last_result": report[:4000],
        "last_error": re.sub(r"\s+", " ", str(row.get("last_error") or "")).strip()[:240],
        "model": str(row.get("model") or ""),
        "provider": str(row.get("provider") or ""),
        "enabled": enabled,
        "live": _cron_is_running(row),
        "fire_claim": row.get("fire_claim") if isinstance(row.get("fire_claim"), dict) else None,
    }


_HERMES_RUN_JOB = re.compile(r"job=([0-9a-f]{8,})", re.I)


def parse_hermes_running_job_ids(text: str) -> list[str]:
    """Job ids Hermes lists as running. last_status on jobs.json stays the previous run."""
    ids: list[str] = []
    seen: set[str] = set()
    for line in str(text or "").splitlines():
        if not re.search(r"\brunning\b", line, re.I):
            continue
        match = _HERMES_RUN_JOB.search(line)
        if not match:
            continue
        jid = match.group(1)
        if jid in seen:
            continue
        seen.add(jid)
        ids.append(jid)
    return ids


def _cron_is_running(row: dict) -> bool:
    if row.get("enabled") is False:
        return False
    if row.get("live") is True:
        return True
    state = str(row.get("state") or "")
    if _CRON_PAUSED.search(state):
        return False
    if _claim_is_live(row):
        return True
    status = str(row.get("last_status") or "").strip()
    if _CRON_DONE.match(status):
        return False
    if _CRON_RUNNING.search(state) or _CRON_RUNNING.search(status):
        return True
    return bool(row.get("claimed"))


def cron_digest(rows: list[dict], *, hours: int = 48, next_ask: str = "", live_runs: list[dict] | None = None) -> dict:
    """Last two days plus what is running / due now. No click-through required."""
    now = datetime.now(timezone.utc)
    window = timedelta(hours=max(6, int(hours)))
    failed: list[dict] = []
    recent: list[dict] = []
    healthy: list[dict] = []
    stale: list[dict] = []
    running: list[dict] = []
    due: list[dict] = []
    just_finished: list[dict] = []
    next_up: dict | None = None
    next_up_when: datetime | None = None
    latest: dict | None = None
    latest_when: datetime | None = None
    upcoming_rows: list[tuple[datetime, dict]] = []
    enabled = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        on = row.get("enabled") is not False
        if on:
            enabled += 1
        status = str(row.get("last_status") or "").lower()
        state = str(row.get("state") or "")
        paused = (not on) or bool(_CRON_PAUSED.search(state))
        when = _parse_cron_when(str(row.get("last_run_at") or ""))
        nxt_when = _parse_cron_when(str(row.get("next_run_at") or ""))
        fresh = bool(when and now - when <= window)
        item = _cron_digest_item(row, on)
        live = _cron_is_running(row)
        if live:
            running.append(item)
        elif when and now - when <= timedelta(minutes=15) and not _CRON_RUNNING.search(status):
            just_finished.append(item)
        if when and (latest_when is None or when > latest_when):
            latest_when = when
            latest = item
        if on and not paused and nxt_when:
            upcoming_rows.append((nxt_when, item))
        if on and not paused and not live and nxt_when:
            delta = nxt_when - now
            if delta <= timedelta(minutes=30):
                due.append(item)
            if nxt_when > now and (next_up_when is None or nxt_when < next_up_when):
                next_up_when = nxt_when
                next_up = item
            elif nxt_when <= now and next_up is None:
                next_up = item
                next_up_when = nxt_when
        if on and re.search(r"error|fail", status) and not live:
            failed.append(item)
        elif fresh and re.search(r"healthy|\[silent\]", f"{row.get('outcome') or ''} {row.get('last_result') or ''}", re.I):
            healthy.append(item)
        elif fresh:
            recent.append(item)
        elif on:
            stale.append(item)
    ask = re.sub(r"\s+", " ", str(next_ask or "")).strip()
    if ask in {"", "—"}:
        ask = ""
    bits = []
    if healthy or recent:
        names = [row["title"] for row in (healthy + recent)[:3]]
        bits.append("Recently: " + ", ".join(names) + ".")
    else:
        bits.append(
            "This board’s schedule copy is older than two days. "
            "The live Hermes box still runs the jobs — Telegram gets today’s work."
        )
    if failed:
        bits.append("Last copy still failed: " + ", ".join(row["title"] for row in failed[:3]) + ".")
    upcoming_rows.sort(key=lambda pair: pair[0])
    upcoming = [item for _, item in upcoming_rows]
    if next_up is None and upcoming:
        next_up = upcoming[0]
    result_row = just_finished[0] if just_finished else None
    if result_row is None and latest and not any(row.get("id") == latest.get("id") for row in running):
        result_row = latest
    if result_row is None:
        result_row = latest
    results: list[dict] = []
    seen_results: set[str] = set()
    for item in ([result_row] if result_row else []) + just_finished + healthy + recent:
        rid = str(item.get("id") or "")
        if not rid or rid in seen_results:
            continue
        seen_results.add(rid)
        results.append(item)
    if ask and not re.search(r"open hermes to confirm", ask, re.I):
        bits.append("What moves this forward: " + ask)
    elif healthy or recent:
        bits.append("No operator step from the schedule.")
    chat_live = [row for row in (live_runs or []) if isinstance(row, dict)]
    live_bits = []
    if running:
        live_bits.append("Now running: " + ", ".join(row["title"] for row in running[:3]) + ".")
    if chat_live:
        live_bits.append("This chat is answering now.")
    if due and not running:
        live_bits.append("Due now: " + ", ".join(row["title"] for row in due[:3]) + ".")
    if just_finished and not running:
        live_bits.append("Just finished: " + ", ".join(row["title"] for row in just_finished[:3]) + ".")
    if not live_bits:
        if next_up:
            live_bits.append(f"Nothing running on this copy. Next up: {next_up['title']}.")
        else:
            live_bits.append("Nothing running on this copy.")
        if not (healthy or recent):
            live_bits.append("Live Hermes + Telegram still own today’s jobs.")
        else:
            live_bits.append("A finished job will land in this chat and in What’s happening.")
    return {
        "story": " ".join(bits),
        "live_story": " ".join(live_bits),
        "failed": failed,
        "recent": (healthy + recent)[:12],
        "stale": stale[:6],
        "running": running,
        "due": due[:8],
        "just_finished": just_finished[:8],
        "next_up": next_up,
        "upcoming": upcoming,
        "latest": latest,
        "result": result_row,
        "results": results[:8],
        "copy_stale": not (healthy or recent or running or just_finished),
        "enabled": enabled,
        "failed_count": len(failed),
        "recent_count": len(healthy) + len(recent),
    }


_CRON_MD_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})[_T](\d{2})-(\d{2})-(\d{2})")


def _cron_md_stamp(path: Path) -> datetime | None:
    match = _CRON_MD_STAMP.match(path.stem)
    if not match:
        return None
    try:
        day = datetime.fromisoformat(match.group(1)).date()
        stamp = datetime(
            day.year,
            day.month,
            day.day,
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    return stamp


def _latest_cron_markdown(home: Path, job_id: str, last_run: datetime | None = None, limit: int = 4000) -> str:
    folder = home / "cron" / "output" / str(job_id)
    if not folder.is_dir():
        return ""
    files = sorted(folder.glob("*.md"), key=lambda path: path.name, reverse=True)
    if not files:
        return ""
    chosen = files[0]
    if last_run is not None:
        stamp = _cron_md_stamp(chosen)
        if stamp is None or abs((stamp - last_run).total_seconds()) > 6 * 3600:
            return ""
    try:
        text = chosen.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if _cron_is_prompt_dump(text):
        return ""
    return text[:limit]


def _cron_row_payload(row: dict, result: str = "") -> dict:
    jid = str(row.get("id") or "")
    status = str(row.get("last_status") or "").strip()
    err = str(row.get("last_error") or "").strip()
    report = str(result or row.get("last_result") or "")
    when = _parse_cron_when(str(row.get("last_run_at") or ""))
    fresh = bool(when and datetime.now(timezone.utc) - when <= timedelta(hours=48))
    if status or report or err:
        if fresh or re.search(r"error|fail", status, re.I) or report:
            outcome, nxt = cron_outcome(status, report or err, err)
        else:
            outcome, nxt = (
                "Last check is older than two days.",
                "No action unless something failed.",
            )
    else:
        outcome, nxt = "", ""
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    name = str(row.get("name") or jid)
    live_now = _cron_is_running(row)
    claim = row.get("fire_claim") if isinstance(row.get("fire_claim"), dict) else None
    schedule = str(row.get("schedule_display") or row.get("schedule") or sched.get("expr") or "")
    if isinstance(row.get("schedule"), dict):
        schedule = str(row.get("schedule_display") or sched.get("display") or sched.get("expr") or "")
    return {
        "id": jid,
        "name": name,
        "title": cron_title(name),
        "schedule": schedule,
        "enabled": row.get("enabled") is not False,
        "state": str(row.get("state") or ""),
        "claimed": live_now,
        "live": live_now,
        "fire_claim": claim,
        "last_run_at": str(row.get("last_run_at") or ""),
        "next_run_at": str(row.get("next_run_at") or ""),
        "last_status": status,
        "last_error": err,
        "last_result": report,
        "result_file": str(row.get("result_file") or ""),
        "model": str(row.get("model") or ""),
        "provider": str(row.get("provider") or ""),
        "outcome": outcome,
        "next_action": nxt,
    }


def read_home_crons(home: str | Path | None, *, results: bool = False) -> list[dict]:
    """Read Hermes jobs.json. results=True attaches last markdown. Never opens sqlite."""
    if not home:
        return []
    root = Path(home)
    path = root / "cron" / "jobs.json"
    if not path.is_file():
        return []
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = blob.get("jobs") if isinstance(blob, dict) else blob
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        jid = str(row.get("id"))
        status = str(row.get("last_status") or "").strip()
        when = _parse_cron_when(str(row.get("last_run_at") or ""))
        fresh = bool(when and datetime.now(timezone.utc) - when <= timedelta(hours=48))
        need_md = bool(results and (fresh or re.search(r"error|fail", status, re.I)))
        result = _latest_cron_markdown(root, jid, last_run=when) if need_md else ""
        out.append(_cron_row_payload(row, result))
    return out


def _in_container() -> bool:
    return Path("/.dockerenv").exists() or bool(os.environ.get("RAILWAY_ENVIRONMENT"))


def _popen_detached(cmd: list[str], home: str | Path | None = None):
    """Spawn Hermes so a Docker/Railway parent can exit without killing the gateway."""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": _hermes_env(home),
        "start_new_session": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    return subprocess.Popen(cmd, **kwargs)


def gateway_process_running(text: str) -> bool:
    """True only when Hermes reports a live gateway. 'not running' contains 'running'."""
    low = (text or "").lower()
    if "not running" in low:
        return False
    return "is running" in low


def gateway_status(home: str | Path | None = None, timeout: int = 5) -> dict:
    """Check Hermes gateway status. Does NOT start gateway. Returns immediately.
    
    Never throws or returns 502. On timeout or error, returns running=False with error string.
    """
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "error": "Hermes Agent binary missing", "running": False}
    
    try:
        code, out = _run([binary, "gateway", "status"], None, timeout, home=home)
        text = out.strip()
        
        # Parse running status from output
        running = code == 0 and gateway_process_running(text)
        
        return {
            "ok": code == 0,
            "code": code,
            "text": text or "(no output)",
            "running": running,
            "error": None if code == 0 else text[:200],
        }
    except Exception as err:
        # Hard timeout or subprocess error: return running=False, never throw
        return {
            "ok": False,
            "code": 124,
            "text": "",
            "running": False,
            "error": f"Gateway status check failed: {str(err)[:200]}",
        }


def gateway_start(home: str | Path | None = None, wait: bool = False, timeout: int = 30) -> dict:
    """Start Hermes gateway daemon. Returns immediately if wait=False (lazy start)."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "error": "Hermes Agent binary missing", "running": False}
    
    # Check if already running
    status = gateway_status(home, timeout=5)
    if status.get("running"):
        return {
            "ok": True,
            "code": 0,
            "text": "Gateway already running",
            "running": True,
            "started": False,
        }
    
    if _in_container():
        cmd = [binary, "gateway", "run"]
        try:
            proc = _popen_detached(cmd, home)
            time.sleep(1.5)
            status_check = gateway_status(home, timeout=5)
            running = bool(status_check.get("running"))
            return {
                "ok": running,
                "code": 0 if running else 1,
                "text": "hermes gateway run (container)",
                "running": running,
                "started": running,
                "pid": proc.pid if hasattr(proc, "pid") else None,
            }
        except Exception as err:
            return {
                "ok": False,
                "code": 1,
                "error": str(err),
                "running": False,
                "started": False,
            }

    cmd = [binary, "gateway", "start"]
    if wait:
        # Synchronous start (wait for completion)
        code, out = _run(cmd, None, timeout, home=home)
        text = out.strip()
        running = code == 0
        return {
            "ok": code == 0,
            "code": code,
            "text": text or "(no output)",
            "running": running,
            "started": running,
        }
    else:
        # Async start (spawn and return immediately)
        try:
            proc = _popen(cmd, None, home=home)
            # Give it a moment to start, then check status
            time.sleep(0.5)
            status_check = gateway_status(home, timeout=5)
            return {
                "ok": True,
                "code": 0,
                "text": "Gateway start initiated",
                "running": status_check.get("running", False),
                "started": True,
                "pid": proc.pid if hasattr(proc, "pid") else None,
            }
        except Exception as err:
            return {
                "ok": False,
                "code": 1,
                "error": str(err),
                "running": False,
                "started": False,
            }


def gateway_stop(home: str | Path | None = None, timeout: int = 10) -> dict:
    """Stop Hermes gateway daemon gracefully."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "error": "Hermes Agent binary missing"}
    
    code, out = _run([binary, "gateway", "stop"], None, timeout, home=home)
    text = out.strip()
    
    return {
        "ok": code == 0,
        "code": code,
        "text": text or "(no output)",
    }


def migrate_cron_delivery(home: str | Path | None = None, dry_run: bool = False) -> dict:
    """Migrate Hermes cron jobs from deliver=origin to deliver=local.
    
    Uses is_valid_job_id guard to prevent operating on table chrome.
    """
    result = cron_list(home=home)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": "Failed to list cron jobs",
            "migrated": [],
            "failed": [],
        }
    
    jobs = result.get("jobs", [])
    migrated = []
    failed = []
    
    binary = which("hermes")
    if not binary:
        return {
            "ok": False,
            "error": "Hermes Agent binary missing",
            "migrated": [],
            "failed": [],
        }
    
    for job in jobs:
        job_id = job.get("id", "")
        deliver = job.get("deliver", "")
        
        # Guard: only migrate valid job IDs
        if not is_valid_job_id(job_id):
            failed.append({
                "id": job_id,
                "reason": "Invalid job ID (table chrome)",
            })
            continue
        
        # Only migrate jobs with deliver=origin (skip already-local jobs)
        if deliver and deliver.lower() != "origin":
            continue
        
        if dry_run:
            # Dry run: just record what would be migrated
            migrated.append(job_id)
        else:
            # Real migration: edit delivery setting using correct CLI command
            cmd = [binary, "cron", "edit", job_id, "--deliver", "local"]
            code, out = _run(cmd, None, 30, home=home)
            if code == 0:
                migrated.append(job_id)
            else:
                failed.append({
                    "id": job_id,
                    "reason": out.strip()[:200] or "Update failed",
                })
    
    return {
        "ok": len(failed) == 0,
        "migrated": migrated,
        "failed": failed,
        "total": len(jobs),
        "dry_run": dry_run,
    }


SKILL_LIST_SKIP = frozenset({
    "name",
    "skill",
    "skills",
    "installed",
    "available",
    "bundled",
    "description",
    "status",
    "source",
})


def parse_skill_list(text: str) -> list[str]:
    """Parse `hermes skills list` into skill slugs. Skip table chrome like Installed."""
    names: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if not token or token.startswith("-") or set(token) <= {"-", "="}:
            continue
        if token.lower() in SKILL_LIST_SKIP:
            continue
        if not re.match(r"^[a-z0-9][a-z0-9._-]{0,79}$", token):
            continue
        if token in seen:
            continue
        seen.add(token)
        names.append(token[:80])
    return names


def skills_list(cwd: str | None = None) -> dict:
    """List Hermes skills with descriptions and popular recommendations."""
    binary = which("hermes")
    if not binary:
        return {
            "ok": False,
            "text": "Hermes Agent binary missing",
            "skills": [],
            "popular": []
        }
    code, out = _run([binary, "skills", "list"], cwd, 30)
    
    names = parse_skill_list(out)
    
    # Skill descriptions (fallback when Hermes doesn't provide metadata)
    skill_descriptions = {
        "github": "Query GitHub repos, issues, and PRs",
        "github-pr-workflow": "Create and manage GitHub pull requests",
        "web-search": "Search the web for current information",
        "terminal": "Execute shell commands in the workspace",
        "file-operations": "Read, write, and search files",
        "browser": "Navigate and extract content from websites",
        "python-execution": "Run Python code and scripts",
        "code-analysis": "Analyze code structure and dependencies",
        "documentation": "Generate and update documentation",
        "testing": "Run and analyze test suites",
        "database": "Query and manage databases",
        "api-client": "Make HTTP requests to APIs",
        "image-processing": "Analyze and transform images",
        "data-analysis": "Process and visualize data",
        "scheduling": "Set up cron jobs and timers",
        "notification": "Send alerts and notifications",
        "memory": "Store and retrieve persistent data",
        "research": "Deep research and summarization",
        "planning": "Break down tasks and create plans",
        "review": "Code review and quality checks",
    }
    
    # Build skills list with descriptions
    skills_with_desc = []
    for name in names[:80]:
        desc = skill_descriptions.get(name, "Hermes Agent skill")
        skills_with_desc.append({
            "name": name,
            "description": desc
        })
    
    # Popular skills recommended for Think/Research/Ops
    popular = [
        "web-search",
        "browser",
        "github",
        "terminal",
        "file-operations",
        "research",
        "planning",
    ]
    # Filter to only skills that are actually installed
    popular_installed = [s for s in popular if s in names]
    
    return {
        "ok": code == 0,
        "text": out.strip(),
        "skills": skills_with_desc,
        "popular": popular_installed
    }


def mcp_catalog(cwd: str | None = None) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "text": "Hermes Agent binary missing", "items": []}
    code, out = _run([binary, "mcp", "catalog"], cwd, 30)
    items = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name = line.split()[0]
        items.append({"id": name, "label": line[:160]})
    return {"ok": code == 0, "text": out.strip(), "items": items[:80]}
