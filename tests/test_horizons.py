"""CEO Goals board: INDEX horizons + owner notify."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openbot.org import (
    apply_horizons_to_text,
    dismiss_horizon_notice,
    parse_horizons,
    record_horizon_notice,
    write_project_horizons,
)
from openbot.router import need_choices


class HorizonParseTests(unittest.TestCase):
    def test_round_trip_after_goals(self):
        text = "# Acme\n\nNow: Ready.\nGoals: pay for itself first\n\nFolder: /tmp\n"
        out = apply_horizons_to_text(text, {"week": "Ship desk honesty", "year": "Own the category"})
        parsed = parse_horizons(out)
        self.assertEqual(parsed["week"], "Ship desk honesty")
        self.assertEqual(parsed["year"], "Own the category")
        self.assertIn("Horizon-five:", out)
        again = apply_horizons_to_text(out, {"week": "Ship desk honesty", "month": "ListLogic live"})
        self.assertEqual(parse_horizons(again)["month"], "ListLogic live")
        self.assertEqual(out.count("## Horizons"), 1)
        self.assertEqual(again.count("## Horizons"), 1)

    def test_need_choices(self):
        choices = need_choices({"kind": "horizon"})
        ids = [row.get("id") for row in choices]
        self.assertEqual(ids, ["open_goals", "dismiss_horizon"])


class HorizonNoticeTests(unittest.TestCase):
    def test_record_and_dismiss(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch("openbot.org.ORG", dest):
                notice = record_horizon_notice(
                    "saa-homes",
                    {"week": "old"},
                    {"week": "new", "month": "", "quarter": "", "half": "", "year": "", "five": ""},
                )
                self.assertIsNotNone(notice)
                self.assertFalse(notice.get("dismissed"))
                dismissed = dismiss_horizon_notice(notice["id"])
                self.assertTrue(dismissed.get("ok"))


class HorizonWriteTests(unittest.TestCase):
    def test_write_without_notify(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "saa-homes"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text("# SAA Homes\n\nGoals: —\n", encoding="utf-8")
            with patch("openbot.org.ORG", dest):
                result = write_project_horizons(
                    "saa-homes",
                    {"week": "Catch the 06:00 audit wave"},
                    notify=False,
                )
                self.assertEqual(result["horizons"]["week"], "Catch the 06:00 audit wave")
                self.assertIsNone(result.get("notice"))
                notices = dest / "horizon-notices.json"
                self.assertFalse(notices.is_file())


if __name__ == "__main__":
    unittest.main()
