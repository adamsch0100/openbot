"""This OttoBot desk owns SAA cron. OttoBot chat is the inbox — not Telegram."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class SaaDeskOwnsTests(unittest.TestCase):
    def test_markers(self):
        server = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/org/saa-desk", server)
        self.assertIn("def take_saa_desk", org)
        self.assertIn('"telegram": False', org)
        self.assertIn("OttoBot chat is the inbox", js)
        self.assertIn("Do not Restart this imported home", server)

    def test_default_false(self):
        from openbot import org

        with patch.object(org, "_load_saved", return_value={}):
            self.assertFalse(org.saa_desk_owns())

    def test_bundle_skips_overlay_when_desk_owns(self):
        from openbot.org import project_cron_bundle

        local = [{"id": "local1", "name": "form-pipeline-health"}]
        with patch("openbot.org.saa_desk_owns", return_value=True):
            with patch("openbot.org.project_tools", return_value={"hermes_home": "/tmp/saa"}):
                with patch("openbot.org.read_project_index", return_value="Next: —"):
                    with patch("openbot.live.snapshot", return_value=[]):
                        with patch("openbot.hermes.read_home_crons", return_value=local):
                            with patch("openbot.hermes.load_saa_overlay_cache") as overlay:
                                with patch("openbot.hermes.merge_saa_cron_rows") as merge:
                                    pack = project_cron_bundle("saa-homes")
        overlay.assert_not_called()
        merge.assert_not_called()
        self.assertEqual(pack["crons"][0]["id"], "local1")

    def test_take_saa_desk_does_not_restore_telegram(self):
        from openbot import org

        saved = {"projects": []}

        def load():
            return saved

        def save(data):
            blob = dict(data)
            saved.clear()
            saved.update(blob)

        with patch.object(org, "_load_saved", side_effect=load):
            with patch.object(org, "_save", side_effect=save):
                with patch("openbot.launch.resolve_ceo_hermes_home", return_value="/tmp/saa"):
                    with patch(
                        "openbot.hermes.gateway_start",
                        return_value={"ok": True, "running": True},
                    ) as start:
                        with patch(
                            "openbot.hermes.migrate_cron_delivery",
                            return_value={"ok": True, "migrated": ["abc"]},
                        ) as migrate:
                            with patch("openbot.keyring.preserve_merge_hermes_env") as preserve:
                                result = org.take_saa_desk(start_gateway=True, sync_live=False)
                                owns = org.saa_desk_owns()
        self.assertTrue(result["ok"])
        self.assertFalse(result["telegram"])
        self.assertTrue(owns)
        start.assert_called_once()
        migrate.assert_called_once()
        preserve.assert_not_called()
        self.assertIn("OttoBot chat", result["inbox"])
