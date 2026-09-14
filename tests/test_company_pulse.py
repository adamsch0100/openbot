"""Company pulse + structured INDEX packets. No live Think against SAA."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openbot.bus as bus_mod
import openbot.org as org_mod
import openbot.store as store_mod
from openbot.hermes import job_packet
from openbot.org import company_pulse, index_for_packet, pulse_headline
from openbot.router import _packet_extra, builder_prompt
from openbot.store import write_job


SAA_DOCTRINE = "SAA_DOCTRINE_MARKER: city-by-city dominance for Fort Collins through Greeley."

SAA_INDEX = (
    "# SAA Homes\n\n"
    "Now: Desk owns cron cutover\n"
    "Last: Saved search alerts Healthy\n"
    "Next: Pause live Railway the same minute\n"
    "Blocker: —\n"
    "Goals: market ownership\n\n"
    "## Horizons\n"
    "Horizon-week: 1 live city or CHFA page that can take a lead · NoCO buyer/seller · via organic URLs · proof form HTTP 200\n"
    "Horizon-month: 8+ qualified inquiries\n"
    "Horizon-quarter: Top-8\n"
    "Horizon-half: Organic covers spend\n"
    "Horizon-year: Organic covers the SAA Hermes seat then profit\n"
    "Horizon-five: Schwartz and Associates is the name NoCO already trusts\n\n"
    "## Residual risks (honest)\n"
    "- GBP / login walls: skip + note\n\n"
    "## From Hermes\n\n"
    "You are Hermes, the autonomous growth engine for Schwartz and Associates (SAA Homes).\n"
    "Your mission is market ownership: every person in Northern Colorado who searches to buy or sell.\n"
    + ("Quality over spam. Real local expertise. " * 80)
    + "\n### Operating doctrine\n"
    "Hunt high-intent demand. Own every city. Fix then measure then compound.\n"
    + SAA_DOCTRINE
    + "\n"
)

CHANGELOG_INDEX = (
    "# INDEX\n\n"
    "## Engine changelog (Steward propose)\n"
    + ("- 2026-09-10: filler line that would eat a 2500 cap\n" * 40)
    + "Source of truth for this OttoBot instance.\n\n"
    "Now: v167 — Operator profile\n"
    "Last: v166 — Goals wrapper\n"
    "Next: Hard-refresh\n"
    "Blocker: Do not Accept parked restore\n\n"
    "## Vault\n"
    "- Keys live in secrets.local.json\n"
)

CRON_DIGEST = {
    "due": [{"title": "saved-search-alerts"}],
    "failed": [{"title": "indexation-patrol"}],
    "running": [],
    "result": {"title": "saved search alerts", "outcome": "Healthy"},
    "live_story": "Due now: saved-search-alerts.",
    "story": "Recently: saved search alerts.",
    "failed_count": 1,
    "enabled": 4,
}

CRON_BUNDLE = {
    "project_id": "saa-homes",
    "job_count": 4,
    "digest": CRON_DIGEST,
}


class IndexForPacketTests(unittest.TestCase):
    def test_four_liners_beat_changelog(self):
        packed = index_for_packet(CHANGELOG_INDEX)
        self.assertIn("Now: v167 — Operator profile", packed)
        self.assertLess(packed.find("Now:"), packed.find("Vault") if "Vault" in packed else len(packed))
        self.assertNotIn("Engine changelog", packed)
        self.assertNotIn("filler line that would eat a 2500 cap", packed)
        self.assertTrue(packed.startswith("Now:"), packed[:80])

    def test_saa_doctrine_survives_past_old_cap(self):
        self.assertGreater(len(SAA_INDEX), 2500)
        packed = index_for_packet(SAA_INDEX)
        self.assertIn("Now: Desk owns cron cutover", packed)
        self.assertIn("Horizon-week:", packed)
        self.assertIn("From Hermes", packed)
        self.assertIn(SAA_DOCTRINE, packed)
        self.assertLess(packed.find("Now:"), packed.find("From Hermes"))

    def test_job_packet_uses_structured_index(self):
        packet = job_packet("think", SAA_INDEX, "Now: worker", "Propose next city page")
        self.assertIn("INDEX:", packet)
        self.assertIn("Now: Desk owns cron cutover", packet)
        self.assertIn(SAA_DOCTRINE, packet)
        self.assertIn("Propose next city page", packet)


class PulseIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._org = {
            "org": org_mod.ORG,
            "profile": org_mod.PROFILE_PATH,
            "homes": org_mod.HERMES_HOMES,
        }
        self._store = {"jobs": store_mod.JOBS, "index": store_mod.INDEX, "brains": store_mod.BRAINS}
        self._bus = bus_mod.ORG
        org_mod.ORG = self.home / "org"
        org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
        org_mod.HERMES_HOMES = self.home / "hermes-homes"
        org_mod.ORG.mkdir(parents=True)
        bus_mod.ORG = org_mod.ORG
        store_mod.BRAINS = self.home / "brains"
        store_mod.INDEX = store_mod.BRAINS / "INDEX.md"
        store_mod.JOBS = self.home / "jobs"
        store_mod.BRAINS.mkdir(parents=True)
        store_mod.JOBS.mkdir()
        store_mod.INDEX.write_text(
            "Now: instance ok\nLast: —\nNext: —\nBlocker: —\n",
            encoding="utf-8",
        )
        dest = org_mod.ORG / "projects" / "saa-homes"
        dest.mkdir(parents=True)
        (dest / "INDEX.md").write_text(SAA_INDEX, encoding="utf-8")
        (dest / "inbox.md").write_text(
            "## ticket\nNow: queued\nLast: check CHFA page\n",
            encoding="utf-8",
        )
        work = self.home / "saahomes"
        work.mkdir()
        org_mod.PROFILE_PATH.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "saa-homes",
                            "name": "SAA Homes",
                            "role": "ceo",
                            "folder": str(work),
                            "site_url": "https://saahomes.com",
                            "workers": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        write_job(
            {
                "id": "job-saa-1",
                "at": "2026-09-12T12:00:00Z",
                "engine": "Hermes Agent",
                "project_id": "saa-homes",
                "preset": "think",
                "text": "CHFA page ships next",
            }
        )

    def tearDown(self):
        org_mod.ORG = self._org["org"]
        org_mod.PROFILE_PATH = self._org["profile"]
        org_mod.HERMES_HOMES = self._org["homes"]
        store_mod.JOBS = self._store["jobs"]
        store_mod.INDEX = self._store["index"]
        store_mod.BRAINS = self._store["brains"]
        bus_mod.ORG = self._bus
        self.tmp.cleanup()

    def test_pulse_includes_schedule_git_site_jobs(self):
        git = {
            "ok": True,
            "is_repo": True,
            "branch": "main",
            "remote": "https://github.com/adamsch0100/saahomes",
            "dirty": True,
            "github": True,
        }
        with patch("openbot.org.project_cron_bundle", return_value=CRON_BUNDLE) as cron, patch(
            "openbot.org.git_status", return_value=git
        ):
            text = company_pulse("saa-homes")
            cron.assert_called()
            self.assertEqual(cron.call_args.args[0], "saa-homes")
        self.assertIn("due 1", text)
        self.assertIn("failed 1", text)
        self.assertIn("last: saved search alerts", text)
        self.assertIn("CHFA page ships next", text)
        self.assertIn("check CHFA page", text)
        self.assertIn("Code: main · dirty", text)
        self.assertIn("https://github.com/adamsch0100/saahomes", text)
        self.assertIn("https://saahomes.com", text)
        self.assertIn("not live stats", text)
        self.assertIn("This week:", text)
        self.assertNotIn("invented ranking", text)

    def test_pulse_empty_is_honest(self):
        empty = {
            "project_id": "saa-homes",
            "job_count": 0,
            "digest": {"due": [], "failed": [], "running": [], "enabled": 0},
        }
        with patch("openbot.org.project_cron_bundle", return_value=empty), patch(
            "openbot.org.git_status",
            return_value={"ok": True, "is_repo": False},
        ):
            text = company_pulse("saa-homes")
        self.assertIn("Schedule: none attached", text)
        self.assertIn("https://saahomes.com", text)

    def test_staff_briefing_schedule_honesty(self):
        with patch("openbot.org.project_cron_bundle", return_value=CRON_BUNDLE):
            brief = org_mod.staff_briefing()
            status = org_mod.staff_status_reply()
            headline = pulse_headline("saa-homes")
        self.assertIn("SAA Homes CEO", brief)
        self.assertIn("Schedule:", brief)
        self.assertIn("due 1", brief)
        self.assertIn("failed 1", brief)
        self.assertIn("due 1", status)
        self.assertIn("due 1", headline)
        self.assertIn("failed 1", headline)

    def test_pulse_headline_quiet_saa_copy(self):
        digest = {
            "due": [],
            "failed": [],
            "running": [],
            "copy_stale": True,
            "enabled": 48,
        }
        with patch("openbot.org.saa_desk_owns", return_value=False):
            headline = pulse_headline("saa-homes", digest)
        self.assertIn("live Hermes owns schedule", headline)
        self.assertNotIn("due 0", headline)

    def test_pulse_headline_omits_zero_due_failed(self):
        digest = {
            "due": [],
            "failed": [{"title": "indexation-patrol"}],
            "running": [],
            "enabled": 4,
            "result": {"title": "saved search alerts"},
        }
        headline = pulse_headline("saa-homes", digest)
        self.assertIn("failed 1", headline)
        self.assertNotIn("due 0", headline)
        self.assertIn("last: saved search alerts", headline)

    def test_packet_extra_and_builder_prompt_carry_pulse_and_index(self):
        with patch("openbot.org.project_cron_bundle", return_value=CRON_BUNDLE), patch(
            "openbot.org.git_status",
            return_value={"ok": True, "is_repo": False},
        ):
            extra = _packet_extra("saa-homes", preset="think")
            prompt = builder_prompt("Fix the CHFA form", extra=extra, project_id="saa-homes")
        self.assertIn("PULSE:", extra)
        self.assertIn("due 1", extra)
        self.assertIn("PULSE:", prompt)
        self.assertIn("INDEX:", prompt)
        self.assertIn("Now: Desk owns cron cutover", prompt)
        self.assertIn(SAA_DOCTRINE, prompt)
        self.assertIn("Fix the CHFA form", prompt)

    def test_add_project_pulse_is_empty_honest(self):
        work = self.home / "acme-work"
        work.mkdir()
        data = org_mod.add_project(str(work), "Acme Pulse")
        pid = data.get("project_id")
        self.assertEqual(data.get("founding_status"), "needed")
        empty = {
            "project_id": pid,
            "job_count": 0,
            "digest": {"due": [], "failed": [], "running": [], "enabled": 0},
        }
        with patch("openbot.org.project_cron_bundle", return_value=empty):
            text = company_pulse(pid)
        self.assertIn("Schedule: none attached", text)
        self.assertIn("no week goal", text.lower())
        index = org_mod.read_project_index(pid)
        self.assertIn("compiled PULSE", index)
        self.assertIn("Never auto-cron", index)
        self.assertIn("Never auto-attach cron", data.get("founding_prompt") or "")
