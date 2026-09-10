"""P1: composer #workStatus is one short alive line — no NOW/NEXT/BLOCKER wall."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ComposerWorkStatusAliveTests(unittest.TestCase):
    def test_html_is_single_alive_line(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="workStatus"', html)
        self.assertIn('id="workStatusLive"', html)
        # Park INDEX wall out of composer chrome
        self.assertNotIn("work-status-index", html)
        self.assertNotIn('id="workNow"', html)
        self.assertNotIn('id="workNextLine"', html)
        self.assertNotIn('id="workBlocker"', html)
        self.assertNotIn("<dt>Now</dt>", html)
        self.assertNotIn("<dt>Next</dt>", html)
        self.assertNotIn("<dt>Blocker</dt>", html)

    def test_paint_work_status_is_single_line(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function composerAliveLine", js)
        self.assertIn("function paintWorkStatus", js)
        paint = js[js.find("function paintWorkStatus") : js.find("function paintWorkStatus") + 900]
        self.assertIn("composerAliveLine()", paint)
        self.assertNotIn('workNow', paint)
        self.assertNotIn("workNextLine", paint)
        self.assertNotIn("workBlocker", paint)
        self.assertNotIn("index_blocker", paint)
        # No INDEX field dump into composer
        self.assertNotIn('indexField(text, "Now")', paint)
        self.assertNotIn('indexField(text, "Next")', paint)
        self.assertNotIn('indexField(text, "Blocker")', paint)
        # Quiet idle — hide bare Done spam
        self.assertIn("/^Done\\b/i", paint)
        alive = js[js.find("function composerAliveLine") : js.find("function paintWorkStatus")]
        self.assertIn("Open Schedule", alive)
        self.assertIn("scheduleTrustNowLine", alive)
        self.assertIn("Quiet idle", alive)

    def test_schedule_trust_and_clarity_intact(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function scheduleTrustNowLine", js)
        self.assertIn("function prefersScheduleTrust", js)
        self.assertIn("function honestIndexNext", js)
        self.assertIn("honestIndexNext(", js)
        self.assertIn("function honestWorkLine", js)
        self.assertIn("function humanFailReason", js)
        self.assertIn("function failFingerprint", js)
        self.assertIn("function failClustersHtml", js)

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=150", html)
        self.assertIn("styles.css?v=150", html)


if __name__ == "__main__":
    unittest.main()
