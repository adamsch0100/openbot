"""Preserve Hermes .env channel secrets across redeploy / wallet rewrite."""

import tempfile
import unittest
from pathlib import Path


class TestHermesEnvPreserve(unittest.TestCase):
    def test_restores_telegram_from_bak_openrouter(self):
        from openbot.keyring import preserve_merge_hermes_env, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text(
                "OPENCODE_GO_API_KEY=go-live\n", encoding="utf-8"
            )
            (home / ".env.env.bak-openrouter").write_text(
                "TELEGRAM_BOT_TOKEN=123:ABC\nOPENROUTER_API_KEY=or-old\n",
                encoding="utf-8",
            )
            result = preserve_merge_hermes_env(home)
            self.assertTrue(result["ok"])
            self.assertIn("TELEGRAM_BOT_TOKEN", result["restored"])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["TELEGRAM_BOT_TOKEN"], "123:ABC")
            self.assertEqual(live["OPENCODE_GO_API_KEY"], "go-live")
            # OpenRouter from backup is not a preserve key — leave alone unless missing intent
            self.assertNotIn("OPENROUTER_API_KEY", live)

    def test_does_not_overwrite_live_telegram(self):
        from openbot.keyring import preserve_merge_hermes_env, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text("TELEGRAM_BOT_TOKEN=live-token\n", encoding="utf-8")
            (home / ".env.bak").write_text("TELEGRAM_BOT_TOKEN=old-token\n", encoding="utf-8")
            result = preserve_merge_hermes_env(home)
            self.assertEqual(result["restored"], [])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["TELEGRAM_BOT_TOKEN"], "live-token")

    def test_write_keeps_telegram_when_updating_go_key(self):
        from openbot.keyring import _write_hermes_env, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text(
                "TELEGRAM_BOT_TOKEN=keep-me\nOPENCODE_GO_API_KEY=old\n",
                encoding="utf-8",
            )
            _write_hermes_env({"OPENCODE_GO_API_KEY": "new"}, home=home)
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["TELEGRAM_BOT_TOKEN"], "keep-me")
            self.assertEqual(live["OPENCODE_GO_API_KEY"], "new")
            self.assertTrue((home / ".env.bak-openbot").is_file())


if __name__ == "__main__":
    unittest.main()
