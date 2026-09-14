"""Overnight board: credit, engines chip, receipts, settings findability, OttoBot host."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OvernightBoardUiTests(unittest.TestCase):
    def test_three_line_credit_footer_and_about(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("id=\"footerCredit\"", html)
        self.assertIn("id=\"enginesChip\"", html)
        self.assertIn("id=\"aboutCredit\"", html)
        self.assertIn("OttoBot uses Hermes Agent (MIT, Nous Research)", html)
        self.assertIn("and OpenCode (MIT, Anomaly).", html)
        self.assertIn("Not affiliated with, sponsored by, or endorsed by those projects.", html)
        self.assertIn("<br />", html[html.find("aboutCredit") : html.find("aboutCredit") + 400])

    def test_engines_chip_never_fakes_green(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function paintEnginesChip", js)
        chip = js[js.find("function paintEnginesChip") : js.find("function paintEnginesChip") + 1600]
        self.assertIn("missing", chip)
        self.assertIn("classList.toggle(\"warn\"", chip)
        self.assertIn("found.length === 2", chip)
        self.assertIn('el.textContent = missing.length ? full : "Engines"', chip)

    def test_receipt_shows_tokens_and_dollars(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        rec = js[js.find("function receiptLine") : js.find("function receiptLine") + 900]
        self.assertIn("prompt_tokens", rec)
        self.assertIn("output_tokens", rec)
        self.assertIn("tok", rec)
        self.assertIn("toFixed(4)", rec)
        self.assertIn("tokCount || cost", rec)
        self.assertNotIn("ran || cost", rec)

    def test_settings_order_and_labels(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        nav = html[html.find("drawer-nav") : html.find("drawer-body")]
        self.assertLess(nav.find("You"), nav.find("Keys &amp; wallets"))
        self.assertLess(nav.find("Keys &amp; wallets"), nav.find("Engines"))
        self.assertLess(nav.find('data-panel="engines"'), nav.find("Models"))
        self.assertLess(nav.find("Models"), nav.find("Spend / caps"))
        self.assertLess(nav.find("Spend / caps"), nav.find("Advanced"))
        self.assertIn('id="panel-engines"', html)
        self.assertIn("id=\"enginesHealth\"", html)
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('keys: "Keys & wallets"', js)
        self.assertIn('usage: "Spend / caps"', js)
        self.assertIn('engines: "Engines"', js)
        self.assertIn('setSettings(true, "keys")', js)
        self.assertIn('setSettings(true, "engines")', js)

    def test_chat_surface_says_cos_and_ottobot(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="chatWhere">Cos</div>', html)
        self.assertIn("Talking to Cos", html)
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('return "Cos"', js)
        self.assertIn('return inheritFromStaff ? "inherit Cos" : "Auto"', js)
        self.assertNotIn("inherit Chief of Staff", js)
        self.assertIn('classList.add("wall")', js)
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        self.assertIn('return "Cos"', org)

    def test_host_display_is_ottobot(self):
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        self.assertIn('HOST_CEO_NAME = "OttoBot"', org)
        self.assertIn("HOST_NAME_ALIASES", org)
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('openbot: "OttoBot"', js)
        self.assertNotIn('openbot: "OpenBot"', js)

    def test_cache_bust(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=181", html)
        self.assertIn("styles.css?v=181", html)

    def test_pulse_failed_zero_is_not_a_failed_job(self):
        import re

        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertEqual(js.count("function jobIsFailed"), 1)
        self.assertIn("function failCountNoise", js)
        self.assertIn(r"\bfailed\s*[:=]?\s*\d+", js)
        noise = re.compile(r"\bfailed\s*[:=]?\s*\d+", re.I)
        fail = re.compile(r"fail|error|traceback|exception", re.I)

        def body_failed(text: str) -> bool:
            return bool(fail.search(noise.sub(" ", text)))

        pulse = (
            "PULSE shows schedule due 0 · failed 0, one routine running "
            "(openbot routine e521843f) and master dirty at one known parked handoff; "
            "overnight Think check is clean — VERIFIED from PULSE, engine: Hermes Agent."
        )
        self.assertFalse(body_failed(pulse))
        self.assertTrue(body_failed("Failed - API key rejected (401)"))
        self.assertTrue(body_failed("Failed. Script not found"))
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        self.assertNotIn("keep going from Chief of Staff", org)
        from openbot.org import quiet_index_line

        self.assertEqual(quiet_index_line("keep going from Chief of Staff"), "keep going from Cos")
        router = (ROOT / "openbot" / "router.py").read_text(encoding="utf-8")
        self.assertIn("or Cos for status", router)
        self.assertNotIn("or Chief of Staff for status", router)

    def test_job_card_names_the_engine(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        meta = js[js.find("function jobMeta") : js.find("function isTalk")]
        self.assertIn("job.engine", meta)
        self.assertIn("PRESET_ENGINE[job.preset]", meta)
        self.assertIn('engine !== "board"', meta)
        org = (ROOT / "openbot" / "org.py").read_text(encoding="utf-8")
        self.assertIn("You are Cos.", org)
        self.assertIn("reports to Cos.", org)
        self.assertNotIn("You are Chief of Staff.", org)
        self.assertNotIn("reports to Chief of Staff.", org)


class OvernightHostAliasTests(unittest.TestCase):
    def test_add_ottobot_seats_host_id(self):
        from openbot.org import HOST_CEO_ID, HOST_CEO_NAME, HOST_NAME_ALIASES, node_label

        self.assertEqual(HOST_CEO_ID, "openbot")
        self.assertEqual(HOST_CEO_NAME, "OttoBot")
        self.assertIn("ottobot", HOST_NAME_ALIASES)
        self.assertEqual(node_label(None), "Cos")

    def test_chat_packet_names_ottobot_and_cos(self):
        from openbot.hermes import chat_packet, job_packet

        staff = chat_packet("Cos", "", "hello")
        self.assertIn("You are Cos on a local OttoBot board.", staff)
        ceo = chat_packet("OttoBot", "", "hello")
        self.assertIn("You are the OttoBot CEO on a local OttoBot board.", ceo)
        self.assertIn("You report to Cos", ceo)
        job = job_packet("think", "Now: ok", "", "plan")
        self.assertIn("OttoBot Chat", job)
        self.assertIn("Cos above them", job)

    def test_rollup_skips_smoke_cron(self):
        from unittest.mock import patch

        from openbot.org import rollup_staff

        with patch("openbot.org.patch_index_line") as patched:
            rollup_staff(
                "openbot",
                None,
                "**Cron smoke27-552014 result:** Routine `routine-e521843f` does not exist",
            )
            patched.assert_not_called()

    def test_rollup_last_only_skips_terminal_dump(self):
        from unittest.mock import patch

        from openbot.org import rollup_staff

        calls = []

        def capture(label, value):
            calls.append((label, value))

        dump = "\x1b[0m > build · big-pickle \x1b[0m$ git status && git log --oneline -10 On branch master"
        with patch("openbot.org.patch_index_line", side_effect=capture), patch(
            "openbot.org._load_saved",
            return_value={"projects": [{"id": "pmill-ai", "name": "Pmill.ai"}]},
        ):
            rollup_staff("pmill-ai", None, dump)
        labels = [row[0] for row in calls]
        self.assertEqual(labels, ["Last"])
        self.assertIn("Pmill.ai", calls[0][1])
        self.assertNotIn("git status", calls[0][1])
        self.assertNotIn("Now", labels)
        self.assertNotIn("Next", labels)

    def test_git_remote_strips_embedded_tokens(self):
        from openbot.gitutil import public_remote_url

        self.assertEqual(
            public_remote_url("https://bot:s3cret@example.invalid/repo.git"),
            "https://example.invalid/repo.git",
        )
        self.assertEqual(
            public_remote_url("https://github.com/adamsch0100/openbot.git"),
            "https://github.com/adamsch0100/openbot.git",
        )
        self.assertEqual(public_remote_url(""), "")


if __name__ == "__main__":
    unittest.main()
