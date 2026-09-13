"""SAA Homes cutover onto OttoBot Hermes — sync results, pause standalone, Accept UI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class WriteOverlayResultsTests(unittest.TestCase):
    def test_writes_last_result_markdown(self):
        from openbot.hermes import apply_cron_status_overlay, write_overlay_result_files

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            cron = home / "cron"
            cron.mkdir()
            (cron / "jobs.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "abc123deadbeef",
                                "name": "city-audit",
                                "last_status": "error",
                                "prompt": "keep",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            overlay = [
                {
                    "id": "abc123deadbeef",
                    "last_status": "ok",
                    "last_error": None,
                    "last_run_at": "2026-09-12T12:00:00+00:00",
                    "last_result": "## Result\nCity audit clean.",
                    "result_file": "20260912T120000.md",
                }
            ]
            n = apply_cron_status_overlay(home, overlay)
            self.assertEqual(n, 1)
            jobs = json.loads((cron / "jobs.json").read_text(encoding="utf-8"))["jobs"]
            self.assertEqual(jobs[0]["last_status"], "ok")
            self.assertEqual(jobs[0]["prompt"], "keep")
            out = home / "cron" / "output" / "abc123deadbeef" / "20260912T120000.md"
            self.assertTrue(out.is_file())
            self.assertIn("City audit clean", out.read_text(encoding="utf-8"))
            # second write is idempotent when body unchanged
            self.assertEqual(write_overlay_result_files(home, overlay), 0)


class TakeSaaDeskTests(unittest.TestCase):
    def test_syncs_then_pauses_standalone_then_starts_ottobot(self):
        from openbot import org

        order: list[str] = []

        def sync(home, *, live=False):
            order.append("sync")
            self.assertTrue(live)
            return {"ok": True, "updated": 3, "results_written": 2, "live": True, "jobs": 3}

        def migrate(home, dry_run=False):
            order.append("migrate")
            return {"ok": True, "migrated": ["a"], "dry_run": dry_run}

        def stop(timeout=45):
            order.append("stop")
            return {"ok": True, "code": 0, "text": "stopped", "live": True}

        def start(home, wait=False, timeout=30, force=False):
            order.append("start")
            return {"ok": True, "running": True, "started": True}

        with mock.patch("openbot.launch.resolve_ceo_hermes_home", return_value="/tmp/saa-home"), \
             mock.patch("openbot.hermes.sync_saa_live_crons", side_effect=sync), \
             mock.patch("openbot.hermes.migrate_cron_delivery", side_effect=migrate), \
             mock.patch("openbot.hermes.stop_saa_live_gateway", side_effect=stop), \
             mock.patch("openbot.hermes.gateway_start", side_effect=start), \
             mock.patch("openbot.org.set_saa_desk_owns", return_value={"ok": True}) as owns, \
             mock.patch("openbot.org.patch_scope"), \
             mock.patch("openbot.store.patch_index_line"):
            result = org.take_saa_desk(start_gateway=True, sync_live=True)

        self.assertTrue(result.get("ok"))
        self.assertEqual(order, ["sync", "migrate", "stop", "start"])
        self.assertFalse(result.get("telegram"))
        self.assertIn("OttoBot", result.get("inbox", ""))
        owns.assert_called_with(True)


class SaaCutoverUiTests(unittest.TestCase):
    def test_accept_cutover_controls(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        hermes = (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8")
        self.assertIn("saa-cutover-accept", js)
        self.assertIn("/api/org/saa-desk", js)
        self.assertIn("Cutover is an Accept", js)
        self.assertIn("Refresh live copy", js)
        self.assertIn("second scheduler", js)
        self.assertIn("Live SAA Hermes", js)
        self.assertIn("stop_saa_live_gateway", hermes)
        self.assertIn("write_overlay_result_files", hermes)



class EnsureOrgKeepsDeskOwnsTests(unittest.TestCase):
    def test_ensure_org_preserves_saa_desk_owns(self):
        from openbot import org
        with mock.patch.object(org, "_load_saved", return_value={"saa_desk_owns": True, "projects": []}):
            with mock.patch.object(org, "retire_archived_ceos", side_effect=lambda d: d):
                with mock.patch.object(org, "reattach_imported_ceos", side_effect=lambda d: d):
                    with mock.patch.object(org, "ensure_support_project", side_effect=lambda d, _w: d):
                        with mock.patch.object(org, "load_config", return_value={"work_dir": "/tmp/openbot-work"}):
                            with mock.patch.object(org, "_ensure_project_index"):
                                with mock.patch.object(org, "seed_org_contracts"):
                                    saved = {}
                                    def _save(data):
                                        saved.clear(); saved.update(data)
                                    with mock.patch.object(org, "_save", side_effect=_save):
                                        with mock.patch.object(org, "public_org", side_effect=lambda d: d):
                                            org.ensure_org()
                                    self.assertTrue(saved.get("saa_desk_owns"))


if __name__ == "__main__":
    unittest.main()
