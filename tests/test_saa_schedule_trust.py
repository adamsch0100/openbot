"""P0 Schedule trust: live counts, NOW line, roster ordering, fail ownership."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SaaScheduleTrustUiTests(unittest.TestCase):
    def test_schedule_tab_and_helpers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-work="schedule"', html)
        self.assertIn("function scheduleTrustNowLine", js)
        self.assertIn("function prefersScheduleTrust", js)
        self.assertIn("function cronIsNeverRun", js)
        self.assertIn("function cronIsOverdue", js)
        self.assertIn("function cronRosterStatus", js)
        self.assertIn("function scheduleRosterSort", js)
        self.assertIn("function scheduleRosterRowHtml", js)
        self.assertIn("function cronFailNext", js)
        self.assertIn("Open Schedule", js)
        self.assertIn("Auto-retry — gateway will pick this up", js)
        self.assertIn("CEO handling · Restore script from bootstrap", js)
        self.assertIn("Script not found", js)
        self.assertIn("trustFailed", js)
        self.assertIn("schedule: enabledRows.length", js)
        # live compute — no hardcoded snapshot totals
        self.assertNotIn("58 total / 51 enabled", js)
        self.assertNotIn("55 total / 47 enabled", js)
        # #99 clarity helpers stay
        self.assertIn("function humanFailReason", js)
        self.assertIn("function failFingerprint", js)
        self.assertIn("function failClustersHtml", js)

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=153", html)
        self.assertIn("styles.css?v=153", html)

    def test_roster_status_priority_in_sort(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        # fail before late before never before ok
        fail_i = js.index('if (st === "fail") return 0;')
        late_i = js.index('if (st === "late") return 1;')
        never_i = js.index('if (st === "never") return 2;')
        self.assertLess(fail_i, late_i)
        self.assertLess(late_i, never_i)

    def test_now_line_shape(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("`${who} · ${failed} failed · ${never} never · Open Schedule`", js)


class SaaScheduleTrustBackendTests(unittest.TestCase):
    def test_hermes_fail_ownership(self):
        from openbot.hermes import cron_outcome, human_fail_reason

        reason = human_fail_reason(
            "Gateway shutdown (final-cleanup) killed the job's tool subprocess before the run finished."
        )
        self.assertEqual(reason, "Hermes gateway stopped mid-run")
        outcome, nxt = cron_outcome(
            "error",
            "",
            "Gateway shutdown (final-cleanup) killed the job's tool subprocess before the run finished.",
        )
        self.assertIn("Hermes gateway stopped mid-run", outcome)
        self.assertIn("Auto-retry", nxt)

        reason2 = human_fail_reason("RuntimeError: Script-not-found: scripts/alert-digest.sh")
        self.assertEqual(reason2, "Script not found")
        outcome2, nxt2 = cron_outcome(
            "error", "", "Script-not-found: scripts/citation_submit.py"
        )
        self.assertIn("Script not found", outcome2)
        self.assertIn("Your move", nxt2)
        self.assertIn("bootstrap", nxt2)
        self.assertNotIn("Fix key", nxt2)

    def test_cronwatch_open_schedule(self):
        from openbot.cronwatch import honest_next_line

        peers = [
            {
                "name": "geo-citation-audit",
                "enabled": True,
                "last_status": "error",
                "last_run_at": "2026-09-03T16:00:00+00:00",
                "last_error": "Gateway shutdown",
            },
            {
                "name": "city-audit-batch-3",
                "enabled": True,
                "last_status": "",
                "last_run_at": "",
            },
        ]
        line = honest_next_line(peers)
        self.assertIn("Open Schedule", line)
        self.assertIn("failed", line)
        self.assertIn("never", line)
        self.assertNotIn("open Results", line)


class SaaBootstrapScriptsStillPresent(unittest.TestCase):
    def test_alert_digest_bootstrap(self):
        base = ROOT / "bootstrap" / "saa-homes" / "scripts"
        self.assertTrue((base / "alert-digest.sh").is_file())
        self.assertTrue((base / "alert-digest-hourly.sh").is_file())


if __name__ == "__main__":
    unittest.main()
