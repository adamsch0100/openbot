"""Founding ceremony, Horizon steers, Cos tell-routing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openbot.founding import (
    FOUNDING_MARK,
    HORIZON_SHAPE,
    KNOWN_HORIZONS,
    accept_founding,
    extract_horizons_from_text,
    founding_display,
    founding_prompt,
    founding_prompt_for,
    ingest_ceo_result,
    is_founding_message,
    is_steer_message,
    load_founding,
    mark_founding_needed,
    reject_founding,
    resolve_tell_target,
    route_cos_to_ceo,
)
from openbot.org import parse_horizons, horizon_week
from openbot.router import status_reply


FOUNDING_RESULT = """
Offer: city SEO pages that take a lead
Who: NoCO buyer ready to act
How: organic city + CHFA URLs
Proof: form HTTP 200 + GSC clicks
Never: auto-post, GBP login, mass-retry
Horizon-week: 1 live CHFA page · NoCO buyer · via organic URL · proof form 200
Horizon-month: 8 inquiries · NoCO ready-to-act · via city pages · proof form submits
Horizon-quarter: Top-8 on Tier S city queries · searchers · via city pages · proof GSC
Horizon-half: Organic covers seat spend · NoCO · via SEO · proof GSC vs tokens
Horizon-year: Organic covers the seat then profit · NoCO · via search · proof leads/week
Horizon-five: The name NoCO trusts · via compounding search · proof branded queries
Lanes: SEO skill + city cron
Next: Ship one live CHFA page
"""


class FoundingDetectTests(unittest.TestCase):
    def test_founding_prompt_marks_task(self):
        prompt = founding_prompt(name="Acme", idea="paid tenants wrapping Hermes + OpenCode", site="https://acme.example")
        self.assertIn(FOUNDING_MARK, prompt)
        self.assertIn("Do not write INDEX.md", prompt)
        self.assertIn(HORIZON_SHAPE, prompt)
        self.assertIn("paid tenants wrapping Hermes + OpenCode", prompt)
        self.assertIn("https://acme.example", prompt)
        self.assertIn("multi-tenant", prompt)
        self.assertTrue(is_founding_message(prompt))
        self.assertFalse(is_steer_message(prompt))

    def test_openbot_horizons_are_paid_tenants(self):
        blob = KNOWN_HORIZONS["openbot"]
        week = blob["week"].casefold()
        self.assertIn("tenant", week)
        self.assertIn("pay", week)
        self.assertNotIn("$7", blob["half"])
        self.assertIn("multi-tenant", blob["five"].casefold() + blob["quarter"].casefold())

    def test_extract_horizon_aliases(self):
        messy = (
            "**1 week:** 1 paying tenant · operators · via hosted board · proof login\n"
            "1 month: Paid seats · companies · via signup · proof MRR\n"
            "Horizon-quarter: Isolation · tenants · via product · proof A vs B\n"
            "6 months: Seat MRR covers spend · tenants · via subs · proof revenue\n"
            "1 year: Paid board companies run from · tenants · via CEOs · proof tenants\n"
            "5 years: Wrapper that gets paid · via seats · proof P&L\n"
        )
        parsed = extract_horizons_from_text(messy)
        self.assertEqual(len(parsed), 6)
        self.assertIn("paying tenant", parsed["week"])
        self.assertIn("Paid seats", parsed["month"])

    def test_founding_prompt_for_uses_saved_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "acme"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text("# Acme\n\nGoals: —\nHorizon-week: —\n", encoding="utf-8")
            with patch("openbot.org.ORG", dest), patch("openbot.founding.list_projects", return_value=[{"id": "acme", "name": "Acme"}]):
                mark_founding_needed("acme", idea="paid tenants wrapping Hermes", site="https://acme.example")
                prompt = founding_prompt_for("acme")
                blob = load_founding("acme")
                self.assertIn("paid tenants wrapping Hermes", blob.get("idea") or "")
                self.assertIn("paid tenants wrapping Hermes", prompt)
                self.assertIn("https://acme.example", prompt)
                self.assertIn("Ask Acme to propose Goals from:", founding_display("Acme", blob.get("idea") or ""))

    def test_founding_intent_falls_back_to_week_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "saa-homes"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text(
                "# SAA Homes\n\nGoals: —\n"
                "Horizon-week: 1 live CHFA page · NoCO · via organic · proof 200\n",
                encoding="utf-8",
            )
            with patch("openbot.org.ORG", dest), patch(
                "openbot.founding.list_projects", return_value=[{"id": "saa-homes", "name": "SAA Homes"}]
            ), patch("openbot.org.project_tools", return_value={}):
                from openbot.founding import founding_intent

                intent = founding_intent("saa-homes")
                self.assertIn("CHFA", intent.get("idea") or "")
                prompt = founding_prompt_for("saa-homes")
                self.assertIn("CHFA", prompt)

    def test_steer_detect(self):
        self.assertTrue(is_steer_message("rewrite the horizons for SAA"))
        self.assertTrue(is_steer_message("steer: 1 week goal is one live city page"))
        self.assertFalse(is_steer_message("what is going on"))
        self.assertFalse(is_steer_message("what's on the horizon"))
        self.assertFalse(is_steer_message(f"{FOUNDING_MARK}\nrewrite the horizons"))

    def test_extract_horizons(self):
        parsed = extract_horizons_from_text(FOUNDING_RESULT)
        self.assertEqual(len(parsed), 6)
        self.assertIn("CHFA", parsed["week"])

    def test_cos_tell_target(self):
        with patch("openbot.founding.list_projects", return_value=[{"id": "saa-homes"}]):
            hit = resolve_tell_target("tell SAA: tighten 1 week to one live CHFA page")
            self.assertEqual(hit[0], "saa-homes")
            self.assertIn("CHFA", hit[1])
            self.assertIsNone(resolve_tell_target("tell ListLogic: not seated"))
            self.assertIsNone(resolve_tell_target("hello SAA"))

    def test_status_leads_with_this_week(self):
        text = (
            "# SAA Homes\nNow: healthy\nNext: ship CHFA\n"
            "Horizon-week: 1 live CHFA page · NoCO · via organic · proof 200\n"
        )
        self.assertIn("CHFA", horizon_week(text))
        reply = status_reply(text, "What is going on?", "SAA Homes")
        self.assertTrue(reply.startswith("This week:"))
        self.assertIn("CHFA", reply)
        self.assertIn("healthy", reply)
        empty = status_reply("Now: ticket 1\nLast: builder\nNext: folder then diff\nBlocker: —", "What is going on?", "openbot")
        self.assertIn("Goals are empty", empty)
        self.assertIn("ticket 1", empty)


class FoundingParkTests(unittest.TestCase):
    def test_founding_parks_without_writing_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "acme"
            project.mkdir(parents=True)
            index = project / "INDEX.md"
            index.write_text("# Acme\n\nNow: Ready.\nGoals: —\n\nHorizon-week: —\n", encoding="utf-8")
            with patch("openbot.org.ORG", dest):
                parked = ingest_ceo_result("acme", f"{FOUNDING_MARK}\nfound this company", FOUNDING_RESULT)
                self.assertEqual(parked.get("status"), "draft")
                self.assertEqual(parse_horizons(index.read_text(encoding="utf-8"))["week"], "—")
                written = accept_founding("acme")
                self.assertIn("CHFA", written["horizons"]["week"])
                self.assertIn("CHFA", parse_horizons(index.read_text(encoding="utf-8"))["week"])
                rejected = reject_founding("acme")
                self.assertEqual(rejected.get("status"), "needed")

    def test_steer_merges_into_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "saa-homes"
            project.mkdir(parents=True)
            index = project / "INDEX.md"
            index.write_text(
                "# SAA Homes\n\nNow: Ready.\nGoals: —\n\n"
                "Horizon-week: keep me\nHorizon-month: keep month\n"
                "Horizon-quarter: —\nHorizon-half: —\nHorizon-year: —\nHorizon-five: —\n",
                encoding="utf-8",
            )
            with patch("openbot.org.ORG", dest):
                ingest_ceo_result(
                    "saa-homes",
                    "rewrite the horizons",
                    "Horizon-week: one live city page · NoCO · via organic · proof URL\n"
                    "Horizon-month: 8 inquiries · NoCO · via city pages · proof forms\n"
                    "Horizon-quarter: Top-8 · searchers · via city pages · proof GSC\n",
                )
                parsed = parse_horizons(index.read_text(encoding="utf-8"))
                self.assertIn("live city", parsed["week"])
                self.assertIn("8 inquiries", parsed["month"])

    def test_cos_tell_does_not_rewrite_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "saa-homes"
            project.mkdir(parents=True)
            index = project / "INDEX.md"
            index.write_text("# SAA Homes\n\nNow: keep me\nNext: original next\n", encoding="utf-8")
            with patch("openbot.founding.list_projects", return_value=[{"id": "saa-homes"}]):
                with patch("openbot.founding._project_dir", lambda pid: dest / "projects" / pid):
                    with patch("openbot.bus.create_handoff", return_value={"ok": True}):
                        msg = route_cos_to_ceo("tell SAA: tighten 1 week to one live CHFA page")
            self.assertIn("Routed to SAA Homes", msg or "")
            self.assertIn("original next", index.read_text(encoding="utf-8"))
            inbox = (project / "inbox.md").read_text(encoding="utf-8")
            self.assertIn("Cos steer:", inbox)
            self.assertIn("CHFA", inbox)


if __name__ == "__main__":
    unittest.main()
