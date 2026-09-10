"""SAA alert-digest scripts persist in repo bootstrap + sync into Hermes home."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class SaaBootstrapScriptsTests(unittest.TestCase):
    def test_scripts_in_repo(self):
        base = ROOT / "bootstrap" / "saa-homes" / "scripts"
        self.assertTrue((base / "alert-digest.sh").is_file())
        self.assertTrue((base / "alert-digest-hourly.sh").is_file())
        body = (base / "alert-digest.sh").read_text(encoding="utf-8")
        self.assertIn("alertDigest.js", body)

    def test_sync_writes_executable(self):
        from openbot.org import sync_ceo_hermes_scripts

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "saa-homes"
            home.mkdir()
            written = sync_ceo_hermes_scripts("saa-homes", home)
            self.assertIn("alert-digest.sh", written)
            target = home / "scripts" / "alert-digest.sh"
            self.assertTrue(target.is_file())
            self.assertIn("alertDigest.js", target.read_text(encoding="utf-8"))
            # idempotent
            again = sync_ceo_hermes_scripts("saa-homes", home)
            self.assertIn("alert-digest.sh", again)

    def test_add_ceo_form_markers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("menu-grid-2", js)
        self.assertIn("Name unlocks presets", js)
        self.assertIn("nadia:", js)
        self.assertIn("listlogic:", js)
        self.assertIn("menu-grid-2", css)
        self.assertIn("min(520px", css)


if __name__ == "__main__":
    unittest.main()
