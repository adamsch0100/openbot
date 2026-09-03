"""Official Hermes Agent CLI. Do not invent a third runtime."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from .detect import hermes_home, which

ANSI = re.compile(r"\x1b\[[0-9;]*m")
HERMES_TIMEOUT = 600
TALK_TIMEOUT = 45
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
    for line in (text or "").splitlines():
        stripped = ANSI.sub("", line).strip()
        if SESSION_NOISE.match(stripped) or stripped.lower().startswith("session_id:"):
            continue
        if TOOL_MARKUP.search(stripped):
            continue
        if stripped.startswith("```") and "tool" in stripped.lower():
            continue
        lines.append(ANSI.sub("", line))
    cleaned = "\n".join(lines).strip()
    cleaned = TOOL_MARKUP.sub("", cleaned).strip()
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


def _popen(cmd: list[str], cwd: str | None, home: str | Path | None = None, *, talk: bool = False):
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL if talk else subprocess.STDOUT,
        "cwd": cwd,
        "env": _hermes_env(home),
        "bufsize": 1,
        **_text_kwargs(),
    }
    return subprocess.Popen(cmd, **kwargs)


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
    if talk:
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
            "1" if talk else HERMES_MAX_TURNS,
            "--query-file",
            str(query),
        ]
        if talk:
            cmd.extend(["--ignore-rules", "--reasoning", "none", "--toolsets", "bot_room"])
        else:
            cmd.append("--yolo")
            if toolsets:
                cmd.extend(["--toolsets", toolsets])
            if skills:
                cmd.extend(["--skills", skills])
        if resume:
            cmd.extend(["--resume", resume])
        elif session and not talk:
            cmd.extend(["--continue", session, "--create-if-missing"])
        if provider and model_id:
            cmd.extend(["--provider", provider, "-m", model_id])
        elif model_id:
            cmd.extend(["-m", model_id])
        try:
            proc = _popen(cmd, str(root) if talk else cwd, home=home, talk=talk)
        except FileNotFoundError:
            return {"ok": False, "code": 127, "text": "hermes not on PATH", "usage": {}}
        if run_id:
            from .live import attach

            attach(run_id, proc)
        chunks: list[str] = []
        deadline = time.time() + timeout if timeout else None
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    proc.terminate()
                    return {
                        "ok": False,
                        "code": 130,
                        "text": clean_hermes_text("".join(chunks)) or "Stopped.",
                        "usage": {},
                        "stopped": True,
                    }
                if deadline and time.time() > deadline:
                    proc.kill()
                    return {
                        "ok": False,
                        "code": 124,
                        "text": clean_hermes_text("".join(chunks)) or "hermes timed out",
                        "usage": {},
                    }
                try:
                    line = proc.stdout.readline() if proc.stdout else ""
                except (UnicodeDecodeError, ValueError):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                if line:
                    chunks.append(line)
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
                time.sleep(0.05)
            code = proc.returncode or 0
        except OSError as err:
            return {"ok": False, "code": 1, "text": str(err), "usage": {}}
        raw = "".join(chunks).strip() or "(no output)"
        cleaned = clean_hermes_text(raw)
        if cleaned:
            text = cleaned
        elif TOOL_MARKUP.search(raw) or raw == "(no output)":
            text = ""
        else:
            text = raw[-24000:]
        return {
            "ok": code == 0 and bool(text.strip()),
            "code": code if text.strip() else (code or 1),
            "text": (text or "(no output)")[-24000:],
            "usage": {},
            "engine": "Hermes Agent",
            "session": resume or session,
            "session_id": parse_session_id(raw) or resume or "",
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


def cron_list(cwd: str | None = None) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    code, out = _run([binary, "cron", "list"], cwd, 30)
    return {"ok": code == 0, "code": code, "text": out.strip() or "(no cron jobs)"}


def cron_runs(job_id: str | None = None, limit: int = 20, cwd: str | None = None) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "code": 127, "text": "Hermes Agent binary missing"}
    cmd = [binary, "cron", "runs", "--limit", str(max(1, min(int(limit), 500)))]
    if job_id:
        cmd.append(job_id)
    code, out = _run(cmd, cwd, 30)
    return {"ok": code == 0, "code": code, "text": out.strip() or ""}


def skills_list(cwd: str | None = None) -> dict:
    binary = which("hermes")
    if not binary:
        return {"ok": False, "text": "Hermes Agent binary missing", "skills": []}
    code, out = _run([binary, "skills", "list"], cwd, 30)
    names = []
    for line in (out or "").splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token and not token.startswith("-") and token.lower() not in {"name", "skill", "skills"}:
            names.append(token[:80])
    return {"ok": code == 0, "text": out.strip(), "skills": names[:80]}


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
