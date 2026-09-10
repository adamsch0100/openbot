"""Alive board: honest Doing/Next/Results + no On schedule lie + clarity P0 cards."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class AliveBoardP0Tests(unittest.TestCase):
    def test_frontend_honesty_markers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("digestKnown", js)
        self.assertIn("digestKnown.has(projectId)", js)
        self.assertIn("failed in Results — clear those to move", js)
        self.assertIn("due in Next", js)
        self.assertIn("/^On schedule\\b/i", js)

    def test_cronwatch_honest_next_not_blanket_on_schedule(self):
        src = (ROOT / "openbot" / "cronwatch.py").read_text(encoding="utf-8")
        self.assertIn("def _honest_next_line", src)
        self.assertNotIn(
            'patch_scope(project_id, None, "Next", "On schedule. Open What',
            src,
        )

    def test_honest_next_reports_dues(self):
        from openbot import cronwatch as cw

        due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        rows = [
            {
                "name": "daily-ranking-strike",
                "enabled": True,
                "last_status": "ok",
                "next_run_at": due,
            }
        ]
        with patch.object(cw, "read_home_crons", return_value=rows):
            with patch.object(cw, "project_tools", return_value={"hermes_home": "/tmp/h"}):
                line = cw._honest_next_line("saa-homes", hermes_home="/tmp/h")
        self.assertIn("Next:", line)
        self.assertNotIn("On schedule", line)

    def test_honest_next_reports_fails(self):
        from openbot import cronwatch as cw

        rows = [
            {
                "name": "conversion-surge",
                "enabled": True,
                "last_status": "error",
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_error": "timeout",
            }
        ]
        with patch.object(cw, "read_home_crons", return_value=rows):
            line = cw._honest_next_line("saa-homes", hermes_home="/tmp/h")
        self.assertIn("failed", line.lower())
        self.assertIn("Open Schedule", line)


class AliveBoardCronwatchTests(unittest.TestCase):
    """Clarity P0 peers helper + post card wiring (complementary to master home scan)."""

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
        self.assertIn("Open Schedule", failed)

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
            {"id": "a", "name": "ok-job", "last_status": "ok", "last_run_at": now.isoformat(), "next_run_at": due_at, "enabled": True},
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
        self.assertIn("due", next_line.lower())


class AliveBoardUiTests(unittest.TestCase):
    def test_board_js_locks_doing_honesty(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function whyIdleLine", js)
        self.assertIn("function honestIndexNext", js)
        self.assertIn("function honestWorkLine", js)
        self.assertIn("digestKnown", js)
        self.assertIn("Why idle: still loading schedule", js)
        self.assertIn("failed in Results — clear those to move", js)
        self.assertIn("n > 0", js)
        self.assertIn("counts.ready", js)
        self.assertIn("Checking…", js)
        self.assertIn("honestIndexNext(", js)
        self.assertIn("/^on schedule\\b/i", js)
        # Clarity P0 result cards
        self.assertIn("function humanFailReason", js)
        self.assertIn("function failFingerprint", js)
        self.assertIn("function failClustersHtml", js)
        self.assertIn("function gateLineKind", js)
        self.assertIn("Session busy", js)
        self.assertIn("Bare Done when idle", js)
        self.assertIn("row.subject || row.name", js)

    def test_ready_and_ceo_wire_still_agree(self):
        ready = (ROOT / "tests" / "test_ready.py").read_text(encoding="utf-8")
        self.assertIn("whyIdleLine", ready)


if __name__ == "__main__":
    unittest.main()
