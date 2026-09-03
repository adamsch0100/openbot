"""Research: fetch first. Screenshots stay opt-in. No third browser engine."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
PASSWORD_RE = re.compile(r"""type\s*=\s*['"]password['"]""", re.I)
TAG_RE = re.compile(r"<[^>]+>", re.S)
MAX_CHARS = 8000


def first_url(message: str) -> str | None:
    match = URL_RE.search(message or "")
    return match.group(0).rstrip(").,]") if match else None


def _to_text(raw: str) -> str:
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_page(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenBot/0.1 (local research fetch)", "Accept": "text/html,application/xhtml+xml"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(400_000).decode("utf-8", errors="replace")
            final = resp.geturl()
            status = resp.status
    except urllib.error.HTTPError as err:
        return {"ok": False, "url": url, "error": f"HTTP {err.code}", "login_wall": err.code in {401, 403}}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
        return {"ok": False, "url": url, "error": str(err), "login_wall": False}
    if PASSWORD_RE.search(body):
        return {
            "ok": False,
            "url": final,
            "login_wall": True,
            "error": "Password field on page. Approve a vault login on the board, or type it there — not in chat.",
        }
    text = _to_text(body)[:MAX_CHARS]
    return {
        "ok": True,
        "url": final,
        "status": status,
        "login_wall": False,
        "chars": len(text),
        "text": text,
        "backend": "fetch",
    }
