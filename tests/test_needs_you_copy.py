"""Dogfood copy: Needs you / need a look → Your move / failed."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NeedsYouCopyTests(unittest.TestCase):
    def test_frontend(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Your move", js)
        self.assertIn("Blocked ·", js)
        self.assertIn("failed — open Results", js)
        self.assertIn("Open Schedule", js)
        self.assertIn("failed in Results — clear those to move", js)
        self.assertIn('row.label || "Decide"', js)
        self.assertNotIn("need a look", js)
        self.assertNotIn("Needs you", js)

    def test_cronwatch(self):
        src = (ROOT / "openbot" / "cronwatch.py").read_text(encoding="utf-8")
        self.assertIn("Open Schedule", src)
        self.assertIn("failed · {outcome", src)
        self.assertNotIn("need a look", src)
        self.assertNotIn("needs you ·", src)


if __name__ == "__main__":
    unittest.main()
