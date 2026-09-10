"""P0 otto.png board path + P1 failed honesty markers."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OttoPngBoardPathTests(unittest.TestCase):
    def test_otto_is_board_path(self):
        from openbot.engine_proxy import BOARD_PATHS, _is_board_path, engine_target

        self.assertIn("/otto.png", BOARD_PATHS)
        self.assertTrue(_is_board_path("/otto.png"))
        self.assertTrue(_is_board_path("/otto.png?v=5"))
        self.assertTrue(_is_board_path("/otto.svg"))
        # Must not fall through to OpenCode
        self.assertIsNone(engine_target("/otto.png", ""))
        self.assertIsNone(engine_target("/logo.png", ""))


class FailedHonestyMarkers(unittest.TestCase):
    def test_js_helpers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function isScheduleFluff", js)
        self.assertIn("function honestWorkLine", js)
        self.assertIn("function jobIsFailed", js)
        self.assertIn("jobIsFailed(row)", js)
        self.assertIn("!cronIsFailed(row) && cronIsDueSoon(row)", js)
        self.assertIn("attach a schedule", js)


if __name__ == "__main__":
    unittest.main()
