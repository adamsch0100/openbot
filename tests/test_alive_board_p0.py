"""Alive board: honest Doing/Next/Results + no On schedule lie."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class AliveBoardP0Tests(unittest.TestCase):
    def test_frontend_honesty_markers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("digestKnown", js)
        self.assertIn("digestKnown.has(projectId)", js)
        self.assertIn("need a look in Results", js)
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
        from datetime import datetime, timezone, timedelta

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
        from datetime import datetime, timezone

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
        self.assertRegex(line, r"need[s]? a look")
        self.assertIn("Results", line)


if __name__ == "__main__":
    unittest.main()
