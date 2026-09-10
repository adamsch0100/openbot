"""#95 follow-up: indexSummary refreshes after digest."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class IndexSummaryAfterDigestTests(unittest.TestCase):
    def test_load_ceo_digest_calls_render_bot_meta(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        i = js.find("async function loadCeoDigest")
        self.assertGreater(i, 0)
        chunk = js[i : i + 1600]
        self.assertIn("renderBotMeta({ skipSpend: true })", chunk)
        self.assertGreaterEqual(chunk.count("renderBotMeta({ skipSpend: true })"), 2)


if __name__ == "__main__":
    unittest.main()
