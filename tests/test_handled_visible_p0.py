"""P0 Handled + Visible: ownership map, Next action queue, Results recover loop."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class HandledVisibleUiTests(unittest.TestCase):
    def test_ownership_helpers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function failOwnership", js)
        self.assertIn("function failKindFromBlob", js)
        self.assertIn("function failChromeHtml", js)
        self.assertIn("function failChoices", js)
        self.assertIn("function ownershipSort", js)
        self.assertIn("function handlingAliveLine", js)
        self.assertIn("function markFailHandling", js)
        # Honest map — never Auto-retry on 401/key
        own = js[js.find("function failOwnership") : js.find("function failOwnerRank")]
        key_i = own.index('if (kind === "key")')
        auto_gate = own.index('status: "Auto-retry"')
        # key branch must not return Auto-retry
        key_block = own[key_i : key_i + 450]
        self.assertIn('status: "CEO"', key_block)
        self.assertIn("Fix key in Settings", key_block)
        self.assertIn('next: "Your move (CEO) · Fix key in Settings."', key_block)
        self.assertNotIn('status: "Auto-retry"', key_block)
        self.assertIn("Never Auto-retry on 401", own)
        self.assertIn("gatewayScar", own)
        self.assertIn('kind === "script"', own)
        self.assertIn("Needs Adam", own)
        self.assertIn("Waiting Cos", own)

    def test_next_is_action_queue_not_due_dump(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Action queue ·", js)
        self.assertIn("ownership-sorted action queue", js)
        self.assertIn("HARD: ownership-sorted action queue", js)
        # fails first ahead of Due
        aq = js.index("Action queue · ${actionFails.length}")
        due = js.index("Due · ${soon.length}", aq)
        self.assertLess(aq, due)

    def test_results_recover_loop(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Recovering ·", js)
        self.assertIn("Blocked·Cos", js)
        self.assertIn("Needs Adam ·", js)
        self.assertIn("Resolved ·", js)
        # Cos org Results uses same chrome
        self.assertIn("Recovering · ${failJobs.length}", js)
        self.assertIn("failChromeHtml({", js)

    def test_doing_shows_handling(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Handling · ${recover.length}", js)
        self.assertIn("Handling · ${moving.length}", js)

    def test_card_chrome_and_ctas(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('cron-k">Outcome', js)
        self.assertIn('cron-k">Why', js)
        self.assertIn('cron-k">Next', js)
        self.assertIn('cron-k">Status', js)
        self.assertIn('id: "restore_script"', js)
        self.assertIn('id: "fix_key"', js)
        self.assertIn('id: "ask_cos"', js)
        self.assertIn('id: "restart_gateway"', js)
        self.assertIn('act === "ask_cos"', js)
        self.assertIn('act === "restore_script"', js)
        self.assertIn("Your move (CEO)", js)

    def test_schedule_roster_status_cta(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("cron-roster-glance", js)
        self.assertIn("own.status", js)
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("schedule-roster.failed > .need-actions", css)

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=143", html)
        self.assertIn("styles.css?v=143", html)


class HandledVisibleBackendTests(unittest.TestCase):
    def test_no_auto_retry_on_401(self):
        from openbot.hermes import cron_outcome, human_fail_reason

        reason = human_fail_reason("HTTP 401 unauthorized invalid api key")
        self.assertEqual(reason, "API key rejected (401)")
        outcome, nxt = cron_outcome("error", "", "401 unauthorized x-api-key")
        self.assertIn("API key rejected (401)", outcome)
        self.assertIn("Fix key", nxt)
        self.assertNotIn("Auto-retry", nxt)

    def test_gateway_still_auto_retry(self):
        from openbot.hermes import cron_outcome

        _, nxt = cron_outcome(
            "error",
            "",
            "Gateway shutdown (final-cleanup) killed the job's tool subprocess before the run finished.",
        )
        self.assertIn("Auto-retry", nxt)

    def test_script_ceo_restore(self):
        from openbot.hermes import cron_outcome

        _, nxt = cron_outcome("error", "", "Script-not-found: scripts/citation_submit.py")
        self.assertIn("Restore script", nxt)
        self.assertIn("Your move (CEO)", nxt)
        self.assertNotIn("Auto-retry", nxt)


if __name__ == "__main__":
    unittest.main()
