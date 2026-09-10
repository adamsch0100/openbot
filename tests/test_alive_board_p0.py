"""P0 Alive board: honest Doing, why-idle, no false On schedule."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class AliveBoardCronwatchTests(unittest.TestCase):
    def test_honest_next_skips_on_schedule_when_failed_or_due(self):
        from openbot.cronwatch import honest_next_line

        now = datetime.now(timezone.utc)
        due_at = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        later = (now + timedelta(days=3)).isoformat().replace("+00:00", "Z")

        self.assertTrue(honest_next_line([]).startswith("On schedule"))
        self.assertTrue(
            honest_next_line(
                [{"name": "daily-wrap", "enabled": True, "last_status": "ok", "next_run_at": later}]
            ).startswith("On schedule")
        )

        failed = honest_next_line(
            [
                {"name": "daily-wrap", "enabled": True, "last_status": "ok", "next_run_at": later},
                {"name": "form-pipeline-health", "enabled": True, "last_status": "error"},
            ]
        )
        self.assertNotIn("On schedule", failed)
        self.assertIn("failed", failed.lower())
        self.assertIn("Results", failed)

        due = honest_next_line(
            [
                {"name": "daily-wrap", "enabled": True, "last_status": "ok", "next_run_at": later},
                {"name": "indexation-patrol", "enabled": True, "last_status": "ok", "next_run_at": due_at},
            ]
        )
        self.assertNotIn("On schedule", due)
        self.assertIn("due", due.lower())
        self.assertIn("Next", due)

    def test_post_cron_card_uses_honest_next(self):
        from openbot import cronwatch

        now = datetime.now(timezone.utc)
        due_at = (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        peers = [
            {"id": "a", "name": "ok-job", "last_status": "ok", "last_run_at": now.isoformat(), "next_run_at": due_at},
            {"id": "b", "name": "due-job", "last_status": "ok", "next_run_at": due_at, "enabled": True},
        ]
        patched = []

        def capture(project_id, worker_id, field, value):
            patched.append((field, value))

        with patch.object(cronwatch, "write_job"), patch.object(cronwatch, "patch_scope", side_effect=capture), patch.object(
            cronwatch, "rollup_staff"
        ), patch.object(cronwatch, "append_turn"):
            cronwatch._post_cron_card(
                "saa-homes",
                {
                    "id": "a",
                    "name": "ok-job",
                    "last_status": "ok",
                    "last_result": "Healthy.",
                    "last_run_at": now.isoformat(),
                    "outcome": "Healthy.",
                    "next_action": "No action.",
                },
                peers=peers,
            )
        next_line = next(value for field, value in patched if field == "Next")
        self.assertNotIn("On schedule", next_line)
        self.assertIn("Next", next_line)


class AliveBoardUiTests(unittest.TestCase):
    def test_board_js_locks_doing_honesty(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function whyIdleLine", js)
        self.assertIn("function honestIndexNext", js)
        self.assertIn("Array.isArray(pack.crons)", js)
        self.assertIn("Why idle: still loading schedule", js)
        self.assertIn("Why idle: 1 failed job", js)
        self.assertIn("n > 0", js)
        self.assertIn("counts.ready", js)
        self.assertIn("Checking…", js)
        self.assertNotIn('`${label}<span class="n">${n}</span>`', js)
        self.assertIn("honestIndexNext(", js)
        self.assertIn("/^on schedule\\b/i", js)

    def test_ready_and_ceo_wire_still_agree(self):
        ready = (ROOT / "tests" / "test_ready.py").read_text(encoding="utf-8")
        self.assertIn("whyIdleLine", ready)


if __name__ == "__main__":
    unittest.main()
