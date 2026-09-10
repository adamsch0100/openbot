"""Chat-as-home polish + wire auth align."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class ChatHomePolishTests(unittest.TestCase):
    def test_empty_stream_no_ready_fluff(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Ask what’s going on, or open a CEO.", js)
        self.assertNotIn("Ready when you are. Ask", js)
        self.assertIn("on this Railway board", js)
        self.assertIn("!isScheduleFluff(now)", js)
        chunk = js[js.find("function emptyStreamHtml"): js.find("function emptyStreamHtml") + 900]
        self.assertNotIn("empty-kicker", chunk)

    def test_align_wire_auth_with_urls(self):
        from openbot import org as org_mod

        tools = {
            "site_url": "https://saahomes.com",
            "github_repo": "adamsch0100/saa",
            "railway": "",
            "authorize_site": False,
            "mcp_github": False,
            "authorize_railway": False,
        }
        patched = {}

        def fake_patch(pid, patch, create_if_missing=False):
            patched.update(patch)
            tools.update(patch)
            return tools

        with patch.object(org_mod, "project_tools", return_value=tools):
            with patch.object(org_mod, "patch_project_tools", side_effect=fake_patch):
                org_mod.align_wire_auth_with_urls("saa-homes")
        self.assertTrue(patched.get("authorize_site"))
        self.assertTrue(patched.get("mcp_github"))
        self.assertNotIn("authorize_railway", patched)


if __name__ == "__main__":
    unittest.main()
