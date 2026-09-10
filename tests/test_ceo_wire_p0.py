"""P0 CEO wire, work tabs honesty, risk consent, composer hatch."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CeoWireP0Tests(unittest.TestCase):
    def test_ceo_panel_authorize_and_pmill_site(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        server = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        router = (ROOT / "openbot" / "router.py").read_text(encoding="utf-8")

        self.assertIn("ceoAuthGithub", js)
        self.assertIn("ceoAuthRailway", js)
        self.assertIn("ceoRailway", js)
        self.assertIn("ceoConnectGithub", js)
        self.assertIn("https://pmill.ai", js)
        self.assertNotIn('placeholder="https://example.com"', js)
        self.assertIn("authorize_cookie_export", js)
        self.assertIn("authorize_facebook", js)
        self.assertIn("folderValue !== currentFolder", js)
        self.assertIn("Saved", js)

        self.assertIn("github_repo", server)
        self.assertIn("authorize_railway", server)
        self.assertIn("folder != current", server)

        self.assertIn("CEO_SEAT_PRESETS", org)
        self.assertIn("authorize_cookie_export", org)

        self.assertIn("cookie_export", router)
        self.assertIn("facebook_approval", router)
        self.assertIn("Nadia vault only", router)

        self.assertIn("whyIdleLine", js)
        self.assertIn("honestIndexNext", js)
        self.assertIn("cronFreshness", js)
        self.assertIn("counts.ready", js)
        self.assertIn('n > 0', js)
        self.assertIn("digestKnown", js)

        self.assertIn('id="routeHatch" hidden', html)
        self.assertIn("hatch.hidden = !forced", js)
        self.assertIn("max-width: 100%", css)
        self.assertIn("wire-on", css)


if __name__ == "__main__":
    unittest.main()
