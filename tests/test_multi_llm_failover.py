"""Multi-LLM Settings order: Go pool + never Anthropic."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class MultiLlmFailoverTests(unittest.TestCase):
    def test_markers(self):
        kr = (ROOT / "openbot" / "keyring.py").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("NEVER_PROVIDERS", kr)
        self.assertIn("OPENCODE_GO_API_KEYS", kr)
        self.assertIn("sync_opencode_go_pool_env", kr)
        self.assertIn("keyFailoverHint", js)
        self.assertIn("keyFailoverHint", html)
        self.assertIn('item.id !== "anthropic"', js)

    def test_ordered_skips_anthropic(self):
        from openbot import keyring as kr

        data = {
            "accounts": [
                {"id": "a1", "provider": "opencode", "label": "Go 1", "key": "k1"},
                {"id": "ant", "provider": "anthropic", "label": "Claude", "key": "sk-ant"},
                {"id": "or", "provider": "openrouter", "label": "OR", "key": "or1"},
            ],
            "fallback": ["a1", "ant", "or"],
            "active": {},
            "hermes_instances": [],
            "logins": [],
        }
        with patch.object(kr, "_load", return_value=data):
            ids = kr.ordered_account_ids(engine="Hermes Agent")
        self.assertEqual(ids, ["a1", "or"])
        self.assertNotIn("ant", ids)

    def test_go_pool_writes_comma_keys(self):
        from openbot import keyring as kr

        data = {
            "accounts": [
                {"id": "a1", "provider": "opencode", "label": "Go 1", "key": "k1"},
                {"id": "a2", "provider": "opencode", "label": "Go 2", "key": "k2"},
                {"id": "a3", "provider": "opencode", "label": "Go 3", "key": "k3"},
                {"id": "or", "provider": "openrouter", "label": "OR", "key": "or1"},
            ],
            "fallback": ["a1", "a2", "a3", "or"],
            "active": {},
            "hermes_instances": [],
            "logins": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            written = {}

            def fake_write(updates, home=None):
                written.update(updates)

            with patch.object(kr, "_load", return_value=data):
                with patch.object(kr, "_write_hermes_env", side_effect=fake_write):
                    with patch.object(kr, "upsert_env", side_effect=lambda u: written.update(u)):
                        pool = kr.sync_opencode_go_pool_env(home=home)
            self.assertEqual(pool, ["k1", "k2", "k3"])
            self.assertEqual(written["OPENCODE_GO_API_KEYS"], "k1,k2,k3")
            self.assertEqual(written["OPENCODE_GO_API_KEY"], "k1")
            self.assertNotIn("ANTHROPIC_API_KEY", written)

    def test_activate_anthropic_blocked(self):
        from openbot import keyring as kr

        data = {
            "accounts": [{"id": "ant", "provider": "anthropic", "label": "Claude", "key": "sk-ant"}],
            "fallback": ["ant"],
            "active": {},
            "hermes_instances": [],
            "logins": [],
        }
        with patch.object(kr, "_load", return_value=data):
            with self.assertRaises(ValueError):
                kr.activate_account("ant")


if __name__ == "__main__":
    unittest.main()
