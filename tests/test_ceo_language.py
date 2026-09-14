"""CEO-English board: strip packet dumps, stuck runs, honest status."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PacketStripTests(unittest.TestCase):
    def test_process_law_is_stripped(self):
        from openbot.hermes import clean_hermes_text

        blob = (
            "PROCESS LAW (board control — not a third engine): 1. LOOP: owner.\n"
            "TASK\n"
            "THINK using citation-hub-builder.\n"
            "STATUS\n"
            "Done.\n"
            "The citation-hub plan is written. Nothing published.\n"
        )
        cleaned = clean_hermes_text(blob)
        self.assertNotIn("PROCESS LAW", cleaned)
        self.assertNotIn("LOOP: owner", cleaned)
        self.assertIn("Nothing published", cleaned)

    def test_chat_ok_ping_is_empty(self):
        from openbot.hermes import clean_hermes_text

        self.assertEqual(clean_hermes_text("CHAT_OK"), "")
        self.assertEqual(clean_hermes_text("ping. solid."), "")


class FailEnglishTests(unittest.TestCase):
    def test_fail_reasons_are_human(self):
        from openbot.hermes import human_fail_reason

        self.assertEqual(human_fail_reason("API 401 unauthorized"), "The model key was rejected")
        self.assertEqual(human_fail_reason("hermes think exited 1"), "The worker stopped")
        self.assertEqual(
            human_fail_reason("Script-not-found: scripts/mention-scan.py"),
            "This job's script never arrived",
        )

    def test_restore_only_when_bootstrap_has_the_file(self):
        from openbot.hermes import script_restore_ok

        self.assertTrue(script_restore_ok("scripts/alert-digest.sh", "saa-homes"))
        self.assertFalse(script_restore_ok("scripts/mention-scan.py", "saa-homes"))


class StuckRunTests(unittest.TestCase):
    def test_twelve_hour_live_flag_is_stuck_not_running(self):
        from openbot.hermes import cron_digest

        now = datetime.now(timezone.utc)
        pack = cron_digest(
            [
                {
                    "id": "38041c7a6501",
                    "name": "geo-citation-audit",
                    "enabled": True,
                    "state": "scheduled",
                    "last_status": "ok",
                    "last_run_at": (now - timedelta(hours=12)).isoformat(),
                    "live": True,
                }
            ]
        )
        self.assertEqual(pack["running"], [])
        self.assertEqual(pack["stuck"][0]["name"], "geo-citation-audit")
        self.assertIn("looks stuck", pack["live_story"])
        self.assertIn("12h", pack["live_story"])

    def test_fresh_live_run_is_not_stuck(self):
        from openbot.hermes import cron_digest

        now = datetime.now(timezone.utc)
        pack = cron_digest(
            [
                {
                    "id": "38041c7a6501",
                    "name": "geo-citation-audit",
                    "enabled": True,
                    "state": "scheduled",
                    "last_status": "ok",
                    "last_run_at": (now - timedelta(minutes=20)).isoformat(),
                    "live": True,
                }
            ]
        )
        self.assertEqual(pack["stuck"], [])
        self.assertEqual(pack["running"][0]["name"], "geo-citation-audit")
        self.assertIn("Now running", pack["live_story"])


class StatusEnglishTests(unittest.TestCase):
    def test_status_filters_doctrine_next(self):
        from openbot.router import status_reply

        index = (
            "Now: keep jobs.json. Do not remake crons. Cos owns catch-up.\n"
            "Last: Cos + SAA desk status agree: keep transferred crons; no remake.\n"
            "Next: Ask Code to execute, or Chief of Staff for status\n"
            "Blocker: —\n"
            "Horizon-week: 1 live city or CHFA page that can take a lead\n"
        )
        reply = status_reply(index, "What is going on?", "SAA Homes")
        self.assertIn("This week:", reply)
        self.assertIn("CHFA", reply)
        self.assertNotIn("keep jobs.json", reply)
        self.assertNotIn("Ask Code to execute", reply)
        self.assertNotIn("PROCESS LAW", reply)

    def test_router_does_not_overwrite_next_after_think(self):
        src = (ROOT / "openbot" / "router.py").read_text(encoding="utf-8")
        self.assertNotIn("Ask Code to execute, or Chief of Staff for status", src)
        self.assertNotIn('patch_index_line("Now", "Think finished")', src)


class CatchupHonestyTests(unittest.TestCase):
    def test_old_gateway_scar_is_not_a_fresh_run(self):
        from openbot.hermes import cron_digest, saa_catchup_next

        now = datetime.now(timezone.utc)
        row = {
            "id": "38041c7a6501",
            "name": "geo-citation-audit",
            "enabled": True,
            "state": "scheduled",
            "last_status": "error",
            "last_error": "Gateway shutdown (final-cleanup)",
            "last_run_at": (now - timedelta(days=5)).isoformat(),
            "live": True,
            "fire_claim": {"at": now.isoformat()},
        }
        pack = cron_digest([row])
        self.assertEqual(pack["running"], [])
        self.assertTrue(any(item["id"] == "38041c7a6501" for item in pack["failed"]))
        self.assertNotIn("Now running", pack["live_story"])
        self.assertNotEqual(saa_catchup_next([row]), "38041c7a6501")

    def test_js_parks_gateway_and_pauses_on_stop(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function cronIsGhostClaim", js)
        self.assertIn("/api/crons/pause", js)
        self.assertIn("Parked. Retry once if you want it again", js)
        self.assertIn('STAFF_NAME = "Chief of Staff"', js)


class BoardUiTests(unittest.TestCase):
    def test_js_has_stuck_and_ceo_brief(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function cronIsStuck", js)
        self.assertIn("looks stuck", js)
        self.assertIn("stop_stuck", js)
        self.assertIn("This week:", js)
        self.assertIn("Up next:", js)
        self.assertIn("The model key was rejected. Open Settings.", js)
        self.assertIn("PROCESS LAW", js)
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=184", html)


if __name__ == "__main__":
    unittest.main()
