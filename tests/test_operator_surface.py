"""Operator surface: named YOUR MOVE, one CTA, chat is talk."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OperatorSurfaceUiTests(unittest.TestCase):
    def test_your_move_names_ceo(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function ceoMoveName", js)
        self.assertIn("function failMoveWho", js)
        self.assertIn("function operatorMoveRows", js)
        self.assertIn("function moveHeadLabel", js)
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

    def test_hermes_exit_is_not_key(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        kind = js[js.find("function failKindFromBlob") : js.find("function ceoMoveName")]
        self.assertIn("return \"hermes\"", kind)
        self.assertLess(kind.index("return \"key\""), kind.index("return \"hermes\""))

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=146", html)
        self.assertIn("styles.css?v=146", html)


class OperatorSurfaceBackendTests(unittest.TestCase):
    def test_fail_kind_script_vs_hermes_vs_key(self):
        from openbot.hermes import fail_kind_from_blob

        self.assertEqual(fail_kind_from_blob("HTTP 401 unauthorized x-api-key"), "key")
        self.assertEqual(fail_kind_from_blob("Script-not-found: scripts/alert-digest.sh"), "script")
        self.assertEqual(
            fail_kind_from_blob("Traceback File \"/usr/local/lib/hermes-agent/hermes\" Hermes chat exited 1"),
            "hermes",
        )

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
