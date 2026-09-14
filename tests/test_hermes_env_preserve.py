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

    def test_skips_telegram_when_restore_channels_false(self):
        from openbot.keyring import preserve_merge_hermes_env, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text("OPENCODE_GO_API_KEY=go-live\n", encoding="utf-8")
            (home / ".env.bak-openbot").write_text(
                "TELEGRAM_BOT_TOKEN=123:ABC\n",
                encoding="utf-8",
            )
            result = preserve_merge_hermes_env(home, restore_channels=False)
            self.assertTrue(result["ok"])
            self.assertEqual(result["restored"], [])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertNotIn("TELEGRAM_BOT_TOKEN", live)

    def test_restores_database_url_when_channels_off(self):
        from openbot.keyring import preserve_merge_hermes_env, _parse_env_lines, hermes_db_env_present

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text("OPENCODE_GO_API_KEY=go-live\n", encoding="utf-8")
            (home / ".env.bak-openbot").write_text(
                "TELEGRAM_BOT_TOKEN=123:ABC\nDATABASE_URL=postgres://saa-local/saa\n",
                encoding="utf-8",
            )
            result = preserve_merge_hermes_env(home, restore_channels=False)
            self.assertTrue(result["ok"])
            self.assertIn("DATABASE_URL", result["restored"])
            self.assertNotIn("TELEGRAM_BOT_TOKEN", result["restored"])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://saa-local/saa")
            self.assertEqual(live["OPENCODE_GO_API_KEY"], "go-live")
            self.assertNotIn("TELEGRAM_BOT_TOKEN", live)
            self.assertTrue(hermes_db_env_present(home))

    def test_write_keeps_database_url_when_updating_go_key(self):
        from openbot.keyring import _write_hermes_env, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text(
                "DATABASE_URL=postgres://saa-local/saa\nOPENCODE_GO_API_KEY=old\n",
                encoding="utf-8",
            )
            _write_hermes_env({"OPENCODE_GO_API_KEY": "new"}, home=home)
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://saa-local/saa")
            self.assertEqual(live["OPENCODE_GO_API_KEY"], "new")

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

    def test_merges_database_url_from_process_when_home_empty(self):
        import os
        from unittest.mock import patch

        from openbot.keyring import merge_transfer_env_from_process, _parse_env_lines, hermes_db_env_present

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text("OPENCODE_GO_API_KEY=go-live\n", encoding="utf-8")
            with patch.dict(os.environ, {"DATABASE_URL": "postgres://saa-local/saa"}, clear=False):
                result = merge_transfer_env_from_process(home)
            self.assertTrue(result["ok"])
            self.assertIn("DATABASE_URL", result["restored"])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://saa-local/saa")
            self.assertEqual(live["OPENCODE_GO_API_KEY"], "go-live")
            self.assertTrue(hermes_db_env_present(home))

    def test_process_merge_does_not_overwrite_live_database_url(self):
        import os
        from unittest.mock import patch

        from openbot.keyring import merge_transfer_env_from_process, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text("DATABASE_URL=postgres://already/here\n", encoding="utf-8")
            with patch.dict(os.environ, {"DATABASE_URL": "postgres://saa-local/saa"}, clear=False):
                result = merge_transfer_env_from_process(home)
            self.assertEqual(result["restored"], [])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://already/here")

    def test_replaces_private_database_url_with_public(self):
        import os
        from unittest.mock import patch

        from openbot.keyring import merge_transfer_env_from_process, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text(
                "DATABASE_URL=postgres://user:pass@postgres.railway.internal:5432/saa\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://user:pass@postgres.railway.internal:5432/saa",
                    "DATABASE_PUBLIC_URL": "postgres://user:pass@hopper.proxy.rlwy.net:1234/saa",
                },
                clear=False,
            ):
                result = merge_transfer_env_from_process(home)
            self.assertIn("DATABASE_URL", result["restored"])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://user:pass@hopper.proxy.rlwy.net:1234/saa")

    def test_replaces_localhost_database_url_with_public(self):
        import os
        from unittest.mock import patch

        from openbot.keyring import merge_transfer_env_from_process, _parse_env_lines

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".env").write_text(
                "DATABASE_URL=postgres://user:pass@localhost:5432/saa\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"DATABASE_URL": "postgres://user:pass@hopper.proxy.rlwy.net:1234/saa"},
                clear=False,
            ):
                result = merge_transfer_env_from_process(home)
            self.assertIn("DATABASE_URL", result["restored"])
            live = _parse_env_lines((home / ".env").read_text(encoding="utf-8"))
            self.assertEqual(live["DATABASE_URL"], "postgres://user:pass@hopper.proxy.rlwy.net:1234/saa")


if __name__ == "__main__":
    unittest.main()
