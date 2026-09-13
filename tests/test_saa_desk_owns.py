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
        hermes = (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/org/saa-desk", server)
        self.assertIn("stop_live", server)
        self.assertIn("def take_saa_desk", org)
        self.assertIn("def stop_saa_live_box", hermes)
        self.assertIn("def write_saa_desk_marker", hermes)
        self.assertIn("must not wipe cutover", org)
        self.assertIn('"telegram": False', org)
        self.assertIn("OttoBot chat is the inbox", js)
        self.assertIn("This desk owns SAA cron", js)
        self.assertIn("Do not Restart this imported home", server)
        self.assertIn('["down", "-y"]', hermes)

    def test_default_false(self):
        from openbot import org

        with patch.object(org, "_load_saved", return_value={}):
            with patch("openbot.launch.resolve_ceo_hermes_home", return_value=""):
                self.assertFalse(org.saa_desk_owns())

    def test_ensure_org_keeps_saa_desk_owns(self):
        from openbot import org

        saved = {
            "saa_desk_owns": True,
            "projects": [{"id": "openbot", "name": "OttoBot", "primary": True, "folder": "/tmp/ob"}],
        }

        def load():
            return dict(saved)

        def save(data):
            blob = dict(data)
            saved.clear()
            saved.update(blob)

        with patch.object(org, "_load_saved", side_effect=load):
            with patch.object(org, "_save", side_effect=save):
                with patch.object(org, "load_config", return_value={"work_dir": "/tmp/ob"}):
                    with patch.object(org, "retire_archived_ceos", side_effect=lambda data: data):
                        with patch.object(org, "reattach_imported_ceos", side_effect=lambda data: data):
                            with patch.object(org, "ensure_support_project", side_effect=lambda data, work: data):
                                with patch.object(org, "_ensure_project_index"):
                                    with patch.object(org, "seed_org_contracts"):
                                        with patch.object(org, "public_org", side_effect=lambda data: data):
                                            with patch("openbot.memory.ensure_memory_files"):
                                                org.ensure_org()
        self.assertTrue(saved.get("saa_desk_owns"))

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
        order: list[str] = []

        def load():
            return saved

        def save(data):
            blob = dict(data)
            saved.clear()
            saved.update(blob)

        def sync(*_args, **_kwargs):
            order.append("sync")
            return {"ok": True, "updated": 1, "live": True}

        def stop():
            order.append("stop")
            return {"ok": True, "already_down": True, "running": False}

        def start(*_args, **_kwargs):
            order.append("start")
            return {"ok": True, "running": True}

        with patch.object(org, "_load_saved", side_effect=load):
            with patch.object(org, "_save", side_effect=save):
                with patch.object(org, "stamp_saa_desk_owns_index"):
                    with patch("openbot.hermes.write_saa_desk_marker"):
                        with patch("openbot.launch.resolve_ceo_hermes_home", return_value="/tmp/saa"):
                            with patch("openbot.hermes.sync_saa_live_crons", side_effect=sync) as syncer:
                                with patch("openbot.hermes.stop_saa_live_box", side_effect=stop) as stopper:
                                    with patch("openbot.hermes.gateway_start", side_effect=start) as start_gw:
                                        with patch(
                                            "openbot.hermes.migrate_cron_delivery",
                                            return_value={"ok": True, "migrated": ["abc"]},
                                        ) as migrate:
                                            with patch("openbot.keyring.preserve_merge_hermes_env") as preserve:
                                                result = org.take_saa_desk(
                                                    start_gateway=True, sync_live=True, stop_live=True
                                                )
                                                owns = org.saa_desk_owns()
        self.assertTrue(result["ok"])
        self.assertFalse(result["telegram"])
        self.assertTrue(owns)
        syncer.assert_called_once()
        stopper.assert_called_once()
        start_gw.assert_called_once()
        migrate.assert_called_once()
        preserve.assert_not_called()
        self.assertEqual(order, ["sync", "stop", "start"])
        self.assertIn("OttoBot chat", result["inbox"])
        self.assertTrue(result.get("live", {}).get("ok"))

    def test_take_saa_desk_aborts_if_live_still_up(self):
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
                with patch.object(org, "stamp_saa_desk_owns_index") as stamp:
                    with patch("openbot.hermes.read_saa_desk_marker", return_value=False):
                        with patch("openbot.launch.resolve_ceo_hermes_home", return_value="/tmp/saa"):
                        with patch("openbot.hermes.sync_saa_live_crons", return_value={"ok": True}):
                            with patch(
                                "openbot.hermes.stop_saa_live_box",
                                return_value={"ok": False, "error": "still answers SSH", "running": True},
                            ):
                                with patch("openbot.hermes.gateway_start") as start:
                                    result = org.take_saa_desk(start_gateway=True, stop_live=True)
                                    owns = org.saa_desk_owns()
        self.assertFalse(result["ok"])
        self.assertFalse(owns)
        start.assert_not_called()
        stamp.assert_not_called()
        self.assertIn("still answers SSH", result.get("error") or "")

    def test_stop_saa_live_box_refuses_this_board_project(self):
        from openbot import hermes

        with patch.object(hermes, "SAA_LIVE_PROJECT", "board-project"):
            with patch.dict("os.environ", {"RAILWAY_PROJECT_ID": "board-project"}, clear=False):
                result = hermes.stop_saa_live_box()
        self.assertFalse(result["ok"])
        self.assertIn("this OttoBot Railway project", result.get("error") or "")

    def test_stop_saa_live_box_already_down(self):
        from openbot import hermes

        with patch.object(hermes, "saa_live_target_error", return_value=""):
            with patch.object(hermes, "railway_cmd", return_value=["railway"]):
                with patch.object(hermes, "saa_live_box_reachable", return_value=False):
                    with patch.object(hermes, "_run_saa_live_cli") as down:
                        result = hermes.stop_saa_live_box()
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("already_down"))
        down.assert_not_called()

    def test_stop_saa_live_box_downs_then_confirms(self):
        from openbot import hermes
        from types import SimpleNamespace

        pings = [True, True, False]

        def reachable(*_args, **_kwargs):
            return pings.pop(0) if pings else False

        with patch.object(hermes, "saa_live_target_error", return_value=""):
            with patch.object(hermes, "railway_cmd", return_value=["railway"]):
                with patch.object(hermes, "saa_live_box_reachable", side_effect=reachable):
                    with patch.object(
                        hermes,
                        "_run_saa_live_cli",
                        return_value=SimpleNamespace(returncode=0, stdout="removed", stderr=""),
                    ) as down:
                        with patch.object(hermes.time, "sleep"):
                            result = hermes.stop_saa_live_box(wait=8)
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("already_down"))
        down.assert_called_once()
        self.assertEqual(down.call_args[0][0], ["down", "-y"])

    def test_cron_digest_local_owner_skips_telegram(self):
        from openbot.hermes import cron_digest

        stale = cron_digest([], local_owner=True)
        self.assertIn("This desk owns", stale["story"])
        self.assertNotIn("Telegram", stale["story"])
        self.assertNotIn("Telegram", stale["live_story"])
        copy = cron_digest([], local_owner=False)
        self.assertIn("Telegram", copy["story"])
