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
        self.assertIn("function ceoHandlingStoryHtml", js)
        self.assertIn("Needs Adam · ${title}", js)
        self.assertIn("function markFailHandling", js)
        # Honest map — never Auto-retry on 401/key
        own = js[js.find("function failOwnership") : js.find("function failOwnerRank")]
        key_i = own.index('if (kind === "key")')
        auto_gate = own.index('status: "Auto-retry"')
        # key branch must not return Auto-retry
        key_block = own[key_i : key_i + 550]
        self.assertIn('status: "Needs Adam"', key_block)
        self.assertIn("Fix key in Settings", key_block)
        self.assertIn("CEO cannot retry this", key_block)
        self.assertNotIn('status: "Auto-retry"', key_block)
        self.assertIn("Never Auto-retry on 401", own)
        self.assertIn("gatewayScar", own)
        self.assertIn('kind === "script"', own)
        self.assertIn("Needs Adam", own)
        self.assertIn("Waiting Cos", own)
        # 401/key must precede gatewayScar so Fix key wins over Restart gateway
        key_before_gw = own.index('if (kind === "key")')
        gw_block = own.index("if (gatewayScar)")
        self.assertLess(key_before_gw, gw_block, "key ownership must win over gatewayScar")
        self.assertIn("Fix key wins even when Hermes Off", own)

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

    def test_doing_is_live_only(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("Handling · ${moving.length}", js)
        self.assertNotIn("Handling · ${recover.length}", js)
        self.assertIn('emptyWorkCopy("doing")', js)
        self.assertIn("Nothing running on ${who}", js)

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
        self.assertIn("Your move ·", js)
        self.assertIn("function ceoMoveName", js)
        self.assertIn("function operatorMoveRows", js)
        self.assertIn("function chatLaneNoise", js)

    def test_schedule_roster_status_cta(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("cron-roster-glance", js)
        self.assertIn("own.status", js)
        # Collapsed fail rows: Status + primary CTA in summary (not expand-only)
        self.assertIn("cron-roster-cta", js)
        self.assertIn("primaryCta", js)
        roster = js[js.find("function scheduleRosterRowHtml") : js.find("function workCounts")]
        self.assertIn("<summary class=\"cron-head\">", roster)
        self.assertIn("${primaryCta}", roster)
        self.assertIn('class="cron-roster-cta need-actions"', roster)
        # CTA is inside summary, before closing </summary>
        sum_i = roster.index("<summary class=\"cron-head\">")
        end_sum = roster.index("</summary>", sum_i)
        self.assertIn("${primaryCta}", roster[sum_i:end_sum])
        body = roster[end_sum:]
        self.assertNotIn("choiceButtonsHtml(failChoicesList", body)
        self.assertIn("function rosterPrimaryChoice", js)
        self.assertIn('label: "Run once"', js)
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("schedule-roster.failed > .need-actions", css)
        self.assertIn("cron-roster-cta", css)

    def test_401_beats_gateway_scar_fix_key(self):
        """401 Outcome must map to Fix key CTA even when gatewayScar/Hermes Off also true."""
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        own = js[js.find("function failOwnership") : js.find("function failOwnerRank")]
        key_i = own.index('if (kind === "key")')
        gw_i = own.index("if (gatewayScar)")
        self.assertLess(key_i, gw_i)
        key_block = own[key_i:gw_i]
        self.assertIn("Fix key in Settings", key_block)
        self.assertIn('status: "Needs Adam"', key_block)
        self.assertNotIn("Restart gateway", key_block)
        # failChoices still offers Fix key for kind=key
        choices = js[js.find("function failChoices") : js.find("function cronFailNext")]
        self.assertIn('own.kind === "key"', choices)
        self.assertIn('id: "fix_key", label: "Fix key"', choices)

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=154", html)
        self.assertIn("styles.css?v=154", html)



    def test_action_queue_includes_older_fails(self):
        """Next Action queue must not drop >48h fails — Fresh + Older with honest total."""
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("older-action-fails", js)
        self.assertIn("Older fails · ${olderFails.length}", js)
        self.assertIn("Fresh ${freshFails.length} · Older ${olderFails.length}", js)
        # workCounts counts ALL ownership fails (not 48h-only)
        wc = js[js.find("function workCounts") : js.find("function paintWorkTabs")]
        self.assertIn("actionFails = failed.slice()", wc)
        self.assertIn("count ALL ownership fails", wc)
        # Next builds fresh + older before Due
        hard = js.find("HARD: ownership-sorted action queue")
        self.assertGreater(hard, 0)
        nxt = js[hard : js.find('view === "schedule"', hard)]
        self.assertIn("freshFails", nxt)
        self.assertIn("olderFails", nxt)
        aq = nxt.index("Action queue · ${actionFails.length}")
        older = nxt.index("Older fails · ${olderFails.length}")
        due = nxt.index("Due · ${soon.length}")
        self.assertLess(aq, older)
        self.assertLess(older, due)

    def test_fix_key_deeplink_settings_keys(self):
        """Fix key must open Settings→Keys and must not re-open schedule over the drawer."""
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        # Handler block
        start = js.find('if (act === "fix_model" || act === "fix_key")')
        end = js.find('if (act === "restart_gateway")', start)
        block = js[start:end]
        self.assertIn('setSettings(true, "keys")', block)
        self.assertIn("panel-keys", block)
        self.assertIn("keyList", block)
        self.assertIn("scrollIntoView", block)
        self.assertIn("Do not re-open schedule", block)
        self.assertNotIn("openSchedule(", block)
        # Drawer stays above activity/rail
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        drawer = css[css.find(".drawer {") : css.find(".drawer {") + 220]
        self.assertIn("z-index: 40", drawer)

    def test_401_hermes_off_restart_secondary(self):
        """While Hermes Off, 401 cards keep Fix key primary + Restart gateway secondary."""
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        choices = js[js.find("function failChoices") : js.find("function cronFailNext")]
        key_i = choices.index('own.kind === "key"')
        key_block = choices[key_i : key_i + 420]
        self.assertIn('id: "fix_key", label: "Fix key"', key_block)
        self.assertIn("!gatewayRunning", key_block)
        self.assertIn('id: "restart_gateway", label: "Restart gateway"', key_block)
        # Fix key still precedes Restart in the push order
        self.assertLess(key_block.index("fix_key"), key_block.index("restart_gateway"))



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
        self.assertIn("Your move ·", nxt)
        self.assertNotIn("Fix key", nxt)
        self.assertNotIn("Auto-retry", nxt)


if __name__ == "__main__":
    unittest.main()
