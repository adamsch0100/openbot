"""Official Hermes Agent CLI. Do not invent a third runtime."""

from __future__ import annotations

import json
import os
import re
import select
import subprocess
import tempfile
import time
from pathlib import Path

from .detect import hermes_home, which

ANSI = re.compile(r"\x1b\[[0-9;]*m")
HERMES_TIMEOUT = 600
TALK_TIMEOUT = 90
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
    return cleaned


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
    with tempfile.TemporaryDirectory(prefix="openbot-hermes-") as tmp:
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
    """Validate that a string looks like a real job ID, not table chrome.
    
    Real job IDs:
    - At least 3 characters
    - Contain at least one alphanumeric
    - Not common table chrome words
    
    Use this guard before operating on job IDs from cron list output.
    """
    if not job_id or len(job_id) < 3:
        return False
    
    # Must have at least one alphanumeric
    if not any(c.isalnum() for c in job_id):
        return False
    
    # Reject known table chrome
    chrome = {"│", "├", "┤", "┬", "┴", "┼", "Schedule:", "Last", "Dispatch:", 
              "Delivery:", "Enabled:", "Status:", "ID", "Name", "Created"}
    if job_id in chrome:
        return False
    
    # Reject if it's all punctuation (like "---")
    if all(not c.isalnum() for c in job_id):
        return False
    
    return True


def _parse_cron_table(text: str) -> list[dict]:
    """Parse hermes cron list table output into structured jobs.
    
    Only extracts rows with valid job IDs, names, schedules.
    Ignores table chrome (borders, headers, separators).
    """
    if not text or "No cron" in text or "no cron" in text:
        return []
    
    jobs = []
    lines = text.strip().split("\n")
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Remove box drawing characters and vertical pipes for parsing
        # Common box chars: │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼ ─
        clean = re.sub(r"[│┌┐└┘├┤┬┴┼─║╔╗╚╝╠╣╦╩╬═]", " ", stripped)
        clean = clean.strip()
        
        if not clean:
            continue
        
        # Skip separator lines (all dashes, equals, or spaces)
        if set(clean) <= {"-", "=", " "}:
            continue
        
        # Parse table row: extract fields by position or split
        # Typical format: <id> <name> <schedule> [<enabled>] [<delivery>] [<last_run>]
        parts = clean.split()
        
        # Skip header lines (common patterns) - check first word is a standalone header
        if parts:
            first_word_upper = parts[0].upper()
            if first_word_upper in {"ID", "JOB", "NAME", "SCHEDULE", "STATUS", "ENABLED", "CREATED", "LAST", "DELIVERY"}:
                continue
        if "Schedule:" in clean and "Last" in clean:  # Header-like labels
            continue
        if len(parts) < 3:
            continue
        
        # First part should be a reasonable job ID
        job_id = parts[0]
        # Skip if it's clearly table chrome
        if job_id in {"Schedule:", "Last", "Dispatch:", "Delivery:", "Enabled:", "Status:", "ID", "Name"}:
            continue
        # Skip if it doesn't look like an ID (too short or all punctuation)
        if len(job_id) < 3 or not any(c.isalnum() for c in job_id):
            continue
        
        # Second part is name
        name = parts[1] if len(parts) > 1 else ""
        
        # Third+ parts are schedule
        # Clean up schedule: remove trailing status/delivery/enabled fields if present
        # Common pattern: "every 1h" or "0 9 * * *"
        schedule_parts = []
        for p in parts[2:]:
            # Stop if we hit status words
            if p.lower() in {"enabled", "disabled", "true", "false", "local", "telegram", "running", "idle"}:
                break
            schedule_parts.append(p)
        schedule = " ".join(schedule_parts)
        
        if not schedule:
            continue
        
        jobs.append({
            "id": job_id,
            "name": name,
            "schedule": schedule,
        })
    
    return jobs


def cron_runs(job_id: str | None = None, limit: int = 20, cwd: str | None = None) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    cmd = [binary, "cron", "runs", "--limit", str(max(1, min(int(limit), 500)))]
    if job_id:
        cmd.append(job_id)
    code, out = _run(cmd, cwd, 30)
    return {"ok": code == 0, "code": code, "text": out.strip() or ""}


def gateway_status(home: str | Path | None = None, timeout: int = 5) -> dict:
    """Check Hermes gateway status. Does NOT start gateway. Returns immediately."""
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "error": "Hermes Agent binary missing", "running": False}
    
    code, out = _run([binary, "gateway", "status"], None, timeout, home=home)
    text = out.strip()
    
    # Parse running status from output
    running = code == 0 and "running" in text.lower()
    
    return {
        "ok": code == 0,
        "code": code,
        "text": text or "(no output)",
        "running": running,
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
        
        # Guard: only migrate valid job IDs
        if not is_valid_job_id(job_id):
            failed.append({
                "id": job_id,
                "reason": "Invalid job ID (table chrome)",
            })
            continue
        
        if dry_run:
            # Dry run: just record what would be migrated
            migrated.append(job_id)
        else:
            # Real migration: update delivery setting
            # Note: `hermes cron update` command may vary; adjust as needed
            cmd = [binary, "cron", "update", job_id, "--deliver", "local"]
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
    
    # Parse skill names from `hermes skills list` output
    names = []
    for line in (out or "").splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token and not token.startswith("-") and token.lower() not in {"name", "skill", "skills"}:
            names.append(token[:80])
    
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
