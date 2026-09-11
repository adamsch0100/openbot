"""Operator surface: named YOUR MOVE, one CTA, chat is talk."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OperatorSurfaceUiTests(unittest.TestCase):
    def test_your_move_names_ceo(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function prettyCeoName", js)
        self.assertIn("function isE2eNeed", js)
        self.assertIn("function adamRailChoice", js)
        self.assertIn(".slice(0, 1)", js[js.find("function operatorMoveRows") : js.find("function moveHeadLabel")])
        self.assertIn("ms > -2 * 36e5", js[js.find("function cronIsDueSoon") : js.find("function isScheduleFluff")])
        self.assertNotIn("ms > -7 * 864e5", js[js.find("function cronIsDueSoon") : js.find("function isScheduleFluff")])
        self.assertIn("lastSchedulePid", js)
        self.assertIn("function handlingInboxHtml", js)
        handling = js[js.find("function handlingInboxHtml") : js.find("function paintHelpPanel")]
        self.assertIn('return "";', handling)
        self.assertIn("cron-card failed handled compact", js)
        self.assertIn("function ceoHandlingStoryHtml", js)
        self.assertIn("is handling", js)
        login = js[js.find('if (kind === "login")') : js.find('if (kind === "cookie_export")')]
        self.assertLess(login.index("Approve"), login.index("Open page"))
        gw = js[js.find("function gatewayFailClusterHtml") : js.find("function paintWorkSurface")]
        self.assertIn("`${banner}${cronCardHtml", gw)
        self.assertIn("const pid = String(projectId || \"\");", js[js.find("async function openSchedule") : js.find("function fillProfile")])
        adam = js[js.find("function adamMustSee") : js.find("function operatorMoveRows")]
        self.assertIn('kind === "key"', adam)
        self.assertIn('kind === "wallet"', adam)
        self.assertIn("facebook_approval", adam)
        move = js[js.find("function operatorMoveRows") : js.find("function moveHeadLabel")]
        self.assertIn("adamMustSee(row)", move)
        self.assertIn("adamMustSee(need)", move)
        self.assertIn("Your move · ${names[0]}", js)
        self.assertNotIn("Your move (CEO)", js)

    def test_fail_choices_never_dump_fix_key_on_unknown(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        choices = js[js.find("function failChoices") : js.find("function cronFailNext")]
        self.assertIn("Never Fix key on script-missing", choices)
        self.assertIn('label: "Restore"', choices)
        unknown = choices[choices.rfind("unknown / hermes") :]
        self.assertIn('id: "retry"', unknown)
        self.assertNotIn('id: "fix_key"', unknown)
        self.assertIn("return out.slice(0, 2)", choices)

    def test_chat_hides_opaque_think_ops(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function chatLaneNoise", js)
        noise = js[js.find("function chatLaneNoise") : js.find("function cronJobIsNoise")]
        self.assertIn('preset === "ops"', noise)
        self.assertIn('preset === "think"', noise)
        self.assertIn("opaqueLaneOk", noise)
        self.assertIn("chatLaneNoise(job)", js[js.find("function renderJob") : js.find("function renderJob") + 400])
        turns = js[js.find("function isNoiseTurn") : js.find("function emptyStreamHtml")]
        self.assertIn("chatLaneNoise(job)", turns)
        self.assertIn("isE2ePing", turns)

    def test_e2e_smoke_is_chat_noise(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function isE2ePing", js)
        ping = js[js.find("function isE2ePing") : js.find("function isNoiseText")]
        self.assertIn("SMOKE\\d+_", ping)
        self.assertIn("Reply with exactly", ping)
        self.assertIn("setOrgNode(\"support\", \"\")", js)
        self.assertIn("Tickets · ${open.length}", js)

    def test_hermes_exit_is_not_key(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        kind = js[js.find("function failKindFromBlob") : js.find("function ceoMoveName")]
        self.assertIn("return \"hermes\"", kind)
        self.assertLess(kind.index("return \"key\""), kind.index("return \"hermes\""))

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=154", html)
        self.assertIn("styles.css?v=154", html)

    def test_never_run_once_and_one_cta(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function rosterPrimaryChoice", js)
        self.assertIn('label: "Run once"', js)
        roster = js[js.find("function scheduleRosterRowHtml") : js.find("function workCounts")]
        self.assertIn("${primaryCta}", roster)
        body = roster[roster.index("</summary>") :]
        self.assertNotIn("choiceButtonsHtml(failChoicesList", body)
        self.assertNotIn("choiceButtonsHtml(failChoices", body)

    def test_board_internals_fold_and_digest_fail(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Board internals · ${noiseRoster.length}", js)
        self.assertIn("function topDigestFailNeed", js)
        self.assertIn("function anyCeoHasFailedWork", js)
        fluff = js[js.find("function isScheduleFluff") : js.find("function honestWorkLine")]
        self.assertIn("/^Your move\\b/i.test(raw)", fluff)
        noise = js[js.find("function cronIsNoise") : js.find("function cronNextUseful")]
        self.assertIn("row.name || row.id || row.title", noise)
        self.assertIn('name.replace(/\\s+/g, "-").toLowerCase()', noise)

    def test_ask_cos_names_job_and_does_not_ride_code(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function failJobTitle", js)
        self.assertIn("function failAskWhy", js)
        ask = js[js.find('if (act === "ask_cos")') : js.find('if (act === "dismiss")')]
        self.assertIn("await setOrgNode(\"\", \"\")", ask)
        self.assertIn("forceNew: true", ask)
        self.assertIn("${who} is stuck on ${title}", ask)
        self.assertNotIn("job ${title}", ask)
        send = js[js.find("async function sendMessage") : js.find("async function sendMessage") + 400]
        self.assertIn("forceNew", send)

    def test_result_gore_and_cancelled_130(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function dedupeFailRows", js)
        self.assertIn("Cron Job:", js[js.find("function humanFailReason") : js.find("function jobIsFailed")])
        self.assertIn("exited 130", js[js.find("function failKindFromBlob") : js.find("function ceoMoveName")])
        self.assertIn('own.kind === "cancelled"', js[js.find("function failChoices") : js.find("function cronFailNext")])


class OperatorSurfaceBackendTests(unittest.TestCase):
    def test_fail_kind_script_vs_hermes_vs_key(self):
        from openbot.hermes import fail_kind_from_blob

        self.assertEqual(fail_kind_from_blob("HTTP 401 unauthorized x-api-key"), "key")
        self.assertEqual(fail_kind_from_blob("Script-not-found: scripts/alert-digest.sh"), "script")
        self.assertEqual(
            fail_kind_from_blob("Traceback File \"/usr/local/lib/hermes-agent/hermes\" Hermes chat exited 1"),
            "hermes",
        )
        self.assertEqual(fail_kind_from_blob("opencode run exited 130"), "cancelled")

    def test_human_fail_reason_strips_cron_result(self):
        from openbot.hermes import human_fail_reason

        reason = human_fail_reason(
            "RESULT Saved search alerts immediate Failed. # Cron Job: saved-search-alerts-immediate **Job ID:** 402427761418"
        )
        self.assertNotIn("Job ID", reason)
        self.assertNotIn("RESULT", reason)
        self.assertIn("failed", reason.lower())
        self.assertEqual(human_fail_reason("opencode run exited 130"), "Cancelled")

    def test_pending_approvals_fail_beats_continue(self):
        from unittest.mock import patch

        from openbot.router import pending_approvals

        jobs = [
            {
                "id": "cont",
                "at": "2026-09-10T21:00:00",
                "keep_going": True,
                "project_id": "saa-homes",
                "engine": "board",
                "preset": "think",
            },
            {
                "id": "fail",
                "at": "2026-09-10T20:00:00",
                "status": "error",
                "blocker": "API key rejected (401)",
                "project_id": "saa-homes",
                "engine": "Hermes Agent",
                "preset": "ops",
            },
            {
                "id": "abort",
                "at": "2026-09-10T22:00:00",
                "blocker": "opencode run exited 130",
                "project_id": "openbot",
                "engine": "OpenCode",
                "preset": "builder",
            },
        ]
        with patch("openbot.router.list_jobs", return_value=jobs), patch(
            "openbot.router.list_projects",
            return_value=[
                {"id": "saa-homes", "name": "SAA Homes"},
                {"id": "openbot", "name": "OpenBot"},
            ],
        ), patch("openbot.router.read_project_index", return_value="Now: —\nLast: —\nNext: —\nBlocker: —\n"):
            rows = pending_approvals()
        kinds = {row["project_id"]: row["kind"] for row in rows}
        self.assertEqual(kinds["saa-homes"], "failed")
        self.assertNotIn("openbot", kinds)

    def test_need_choices_failed_no_fix_model_dump(self):
        from openbot.router import need_choices

        script = need_choices({"kind": "failed", "why": "Script-not-found: scripts/foo.sh"})
        self.assertEqual(script[0]["id"], "restore_script")
        self.assertNotIn("fix_model", [c["id"] for c in script])
        self.assertNotIn("fix_key", [c["id"] for c in script])

        crash = need_choices({"kind": "failed", "why": "Hermes chat exited 1"})
        self.assertEqual(crash[0]["id"], "retry")
        self.assertNotIn("fix_model", [c["id"] for c in crash])
        self.assertNotIn("fix_key", [c["id"] for c in crash])

        key = need_choices({"kind": "failed", "why": "API key rejected (401)"})
        self.assertEqual(key[0]["id"], "fix_key")

    def test_cronwatch_does_not_keep_going_on_fail(self):
        src = (ROOT / "openbot" / "cronwatch.py").read_text(encoding="utf-8")
        self.assertIn('"keep_going": False', src)
        self.assertIn("Cron fails belong in Results", src)

    def test_hermes_exit_next_is_retry_not_key(self):
        from openbot.hermes import cron_outcome

        _, nxt = cron_outcome("error", "", "Hermes chat exited 1 traceback File \"/usr/local/lib/hermes-agent/hermes\"")
        self.assertIn("Retry", nxt)
        self.assertNotIn("Fix key", nxt)


if __name__ == "__main__":
    unittest.main()
