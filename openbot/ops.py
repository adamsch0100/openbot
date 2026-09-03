"""Ops tickets. Hermes cron lives in the Hermes workspace, not a second scheduler."""

from __future__ import annotations

from .store import ROOT, now_iso

INBOX = ROOT / "inbox"


def write_ops_ticket(message: str) -> str:
    INBOX.mkdir(exist_ok=True)
    path = INBOX / "ops.md"
    body = (
        "# Ops ticket\n\n"
        f"Now: schedule this\n"
        f"Last: {message.strip()[:400]}\n"
        f"Next: Open the Hermes workspace and attach a cron there.\n"
        f"Blocker: —\n"
        f"At: {now_iso()}\n\n"
        "JOB: Attach Hermes cron. Do not run the work in this chat.\n"
        "GATES: source → evidence → action. A cron never bypasses a gate.\n"
        "SILENCE: do not message on successful normal state. Notify only on "
        "threshold, missing source, failed retry, approval needed, or a material change.\n"
        "RETRIES: idempotent. Do not double-send, double-pay, or double-create. "
        "If partial work succeeds, keep it and report only the blocked remainder.\n"
        "FORBIDDEN: send, publish, pay, delete, sign, production. Park those for the operator.\n"
    )
    path.write_text(body, encoding="utf-8")
    return body
