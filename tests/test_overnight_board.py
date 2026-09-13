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
        chip = js[js.find("function paintEnginesChip") : js.find("function paintEnginesChip") + 1200]
        self.assertIn("missing", chip)
        self.assertIn("classList.toggle(\"warn\"", chip)
        self.assertIn("found.length === 2", chip)

    def test_receipt_shows_tokens_and_dollars(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        rec = js[js.find("function receiptLine") : js.find("function receiptLine") + 900]
        self.assertIn("prompt_tokens", rec)
        self.assertIn("output_tokens", rec)
        self.assertIn("tok", rec)
        self.assertIn("toFixed(4)", rec)

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
        self.assertIn("app.js?v=170", html)
        self.assertIn("styles.css?v=170", html)

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
        self.assertIn("keep going from Cos", org)
        self.assertNotIn("keep going from Chief of Staff", org)
        router = (ROOT / "openbot" / "router.py").read_text(encoding="utf-8")
        self.assertIn("or Cos for status", router)
        self.assertNotIn("or Chief of Staff for status", router)


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
