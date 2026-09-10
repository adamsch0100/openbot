"""#94 follow-up: org-now + indexSummary honesty."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RailOrgNowHonestyTests(unittest.TestCase):
    def test_markers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function briefHonestyLine", js)
        self.assertIn("briefHonestyLine(cleaned)", js)
        self.assertIn("workCounts(project.id)", js)
        self.assertIn("function workCounts(forProjectId)", js)
        self.assertIn("honestWorkLine(line, counts)", js)


if __name__ == "__main__":
    unittest.main()
