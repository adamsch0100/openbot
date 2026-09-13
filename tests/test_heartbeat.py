"""Heartbeat proposals: why, review last labor, auto-labor gates. No live SAA Think."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openbot.bus as bus_mod
import openbot.org as org_mod
import openbot.store as store_mod
from openbot.decide import (
    HEARTBEAT_MARK,
    auto_labor_allowed,
    classify_proposal,
    ingest_think_result,
    last_labor_review,
    parse_proposal_from_text,
    proposal_packet_extra,
    prove_decision_loop,
    write_proposal,
)
from openbot.heartbeat import cron_is_heartbeat, ensure_heartbeat_routine, heartbeat_enabled, run_heartbeat_now
from openbot.org import patch_project_tools
import openbot.routines as routines_mod
from openbot.router import job_choices, need_choices, pending_approvals
from openbot.store import write_job


PROPOSAL_TEXT = """
Why: CHFA form 404 blocks the week Horizon
Horizon: 1 live city or CHFA page that can take a lead
Evidence: VERIFIED
Alternatives: Do not blast email; do not pause all cron
Review: none
Lane: code
Next: Restore the CHFA contact form HTTP 200
Auto: yes
Uncertainties: live Railway still owns some cron
Discuss: Is the 404 on production or only the overlay copy?
"""


class ParseProposalTests(unittest.TestCase):
    def test_parse_labels(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        self.assertIn("CHFA form 404", parsed["why"])
        self.assertEqual(parsed["evidence"].split()[0].upper(), "VERIFIED")
        self.assertEqual(parsed["lane"].lower(), "code")
        self.assertIn("Restore the CHFA", parsed["next"])
        self.assertIn("404 on production", parsed["discuss"])


class DecideIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._org = {
            "root": org_mod.ROOT,
            "org": org_mod.ORG,
            "profile": org_mod.PROFILE_PATH,
            "homes": org_mod.HERMES_HOMES,
        }
        self._store = {"jobs": store_mod.JOBS, "index": store_mod.INDEX, "brains": store_mod.BRAINS, "root": store_mod.ROOT}
        self._bus = {"org": bus_mod.ORG, "root": bus_mod.ROOT}
        self._routines_org = routines_mod.ORG
        store_mod.ROOT = self.home
        bus_mod.ROOT = self.home
        bus_mod.ORG = self.home / "org"
        org_mod.ROOT = self.home
        org_mod.ORG = self.home / "org"
        org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
        org_mod.HERMES_HOMES = self.home / "hermes-homes"
        routines_mod.ORG = self.home / "org"
        org_mod.ORG.mkdir(parents=True)
        store_mod.BRAINS = self.home / "brains"
        store_mod.INDEX = store_mod.BRAINS / "INDEX.md"
        store_mod.JOBS = self.home / "jobs"
        store_mod.BRAINS.mkdir()
        store_mod.JOBS.mkdir()
        store_mod.INDEX.write_text("Now: test\nLast: —\nNext: —\nBlocker: —\n", encoding="utf-8")
        dest = org_mod.ORG / "projects" / "saa-homes"
        dest.mkdir(parents=True)
        (dest / "INDEX.md").write_text(
            "# SAA Homes\n\nNow: desk\nLast: —\nNext: —\nBlocker: —\n"
            "Horizon-week: 1 live CHFA page · NoCO · via organic · proof form 200\n",
            encoding="utf-8",
        )
        org_mod.PROFILE_PATH.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "saa-homes",
                            "name": "SAA Homes",
                            "role": "ceo",
                            "folder": str(self.home / "work"),
                            "workers": [],
                            "auto_labor": False,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.home / "work").mkdir()

    def tearDown(self):
        org_mod.ROOT = self._org["root"]
        org_mod.ORG = self._org["org"]
        org_mod.PROFILE_PATH = self._org["profile"]
        org_mod.HERMES_HOMES = self._org["homes"]
        store_mod.JOBS = self._store["jobs"]
        store_mod.INDEX = self._store["index"]
        store_mod.BRAINS = self._store["brains"]
        store_mod.ROOT = self._store["root"]
        bus_mod.ORG = self._bus["org"]
        bus_mod.ROOT = self._bus["root"]
        routines_mod.ORG = self._routines_org
        self.tmp.cleanup()

    def test_ingest_writes_proposal_and_next(self):
        decided = ingest_think_result(
            "saa-homes",
            f"{HEARTBEAT_MARK} audit then propose",
            PROPOSAL_TEXT,
            job_id="job1",
        )
        self.assertEqual(decided.get("status"), "proposal")
        self.assertIn("CHFA form 404", decided["proposal"]["why"])
        index = org_mod.read_project_index("saa-homes")
        self.assertIn("Restore the CHFA", org_mod.index_field(index, "Next"))

    def test_auto_labor_off_without_pin(self):
        write_proposal("saa-homes", parse_proposal_from_text(PROPOSAL_TEXT))
        ok, reason = auto_labor_allowed("saa-homes")
        self.assertFalse(ok)
        self.assertIn("notify", reason)

    def test_auto_labor_blocks_unknown_and_irreversible(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        parsed["evidence"] = "UNKNOWN"
        write_proposal("saa-homes", parsed)
        with patch("openbot.org.project_tools", return_value={"auto_labor": True}):
            ok, reason = auto_labor_allowed("saa-homes")
        self.assertFalse(ok)
        self.assertIn("UNKNOWN", reason)
        parsed["evidence"] = "VERIFIED"
        parsed["next"] = "Publish the CHFA page live"
        write_proposal("saa-homes", parsed)
        with patch("openbot.org.project_tools", return_value={"auto_labor": True}):
            ok, reason = auto_labor_allowed("saa-homes")
        self.assertFalse(ok)
        self.assertIn("Accept gate", reason)

    def test_auto_labor_ok_when_pin_and_verified_code(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        write_proposal("saa-homes", parsed)
        with patch("openbot.org.project_tools", return_value={"auto_labor": True}):
            ok, reason = auto_labor_allowed("saa-homes")
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok")

    def test_last_labor_review_failed(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        parsed["at"] = "2026-09-12T10:00:00Z"
        write_proposal("saa-homes", parsed)
        write_job(
            {
                "id": "b1",
                "at": "2026-09-12T11:00:00Z",
                "project_id": "saa-homes",
                "preset": "builder",
                "engine": "OpenCode",
                "blocker": "OpenCode binary missing",
                "text": "failed",
            }
        )
        audit = last_labor_review("saa-homes")
        self.assertEqual(audit["review"], "failed")

    def test_last_labor_skips_think_and_counts_builder(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        parsed["at"] = "2026-09-12T10:00:00Z"
        parsed["job_id"] = "think1"
        write_proposal("saa-homes", parsed)
        write_job(
            {
                "id": "think1",
                "at": "2026-09-12T10:01:00Z",
                "project_id": "saa-homes",
                "preset": "think",
                "message": HEARTBEAT_MARK,
                "text": "proposed",
            }
        )
        write_job(
            {
                "id": "code1",
                "at": "2026-09-12T11:00:00Z",
                "project_id": "saa-homes",
                "preset": "builder",
                "engine": "OpenCode",
                "text": "form 200",
            }
        )
        audit = last_labor_review("saa-homes")
        self.assertEqual(audit["review"], "implemented")

    def test_packet_extra_carries_why_and_review(self):
        write_proposal("saa-homes", parse_proposal_from_text(PROPOSAL_TEXT))
        extra = proposal_packet_extra("saa-homes", f"{HEARTBEAT_MARK} weekday")
        self.assertIn("LAST LABOR REVIEW", extra)
        self.assertIn("OPEN PROPOSAL", extra)
        self.assertIn("CHFA form 404", extra)
        self.assertIn("HEARTBEAT LAW", extra)

    def test_ingest_skips_unlabeled_think(self):
        decided = ingest_think_result("saa-homes", "plain think", "Here is a plan without labels.", job_id="x")
        self.assertEqual(decided, {})

    def test_job_choices_proposal(self):
        choices = job_choices(
            {
                "proposal": {"lane": "code", "next": "fix form", "why": "404"},
                "keep_going": True,
                "project_id": "saa-homes",
            }
        )
        ids = [row["id"] for row in choices]
        self.assertIn("do_proposal", ids)
        self.assertIn("ask_cos_proposal", ids)
        self.assertIn("ask_me_proposal", ids)
        self.assertIn("skip_proposal", ids)

    def test_need_choices_heartbeat(self):
        ids = [row["id"] for row in need_choices({"kind": "heartbeat"})]
        self.assertEqual(ids[0], "attach_heartbeat")
        self.assertIn("run_heartbeat_now", ids)
        self.assertIn("dismiss", ids)

    def test_heartbeat_routine_not_auto_attached(self):
        info = ensure_heartbeat_routine("saa-homes", enabled=False)
        self.assertTrue(info.get("ok"))
        self.assertFalse(heartbeat_enabled("saa-homes"))
        self.assertFalse(cron_is_heartbeat("saved-search-alerts"))
        self.assertTrue(cron_is_heartbeat("openbot-routine-saa-homes-routine-heartbeat"))

    def test_pending_shows_heartbeat_when_goals_live(self):
        with patch("openbot.router.list_projects", return_value=[
            {"id": "saa-homes", "name": "SAA Homes", "index": (org_mod.ORG / "projects" / "saa-homes" / "INDEX.md").read_text(encoding="utf-8")}
        ]), patch("openbot.heartbeat.heartbeat_enabled", return_value=False), patch(
            "openbot.org.project_tools", return_value={"heartbeat_offer": ""}
        ):
            rows = pending_approvals()
        kinds = [row.get("kind") for row in rows]
        self.assertIn("heartbeat", kinds)

    def test_pending_shows_open_proposal(self):
        write_proposal("saa-homes", parse_proposal_from_text(PROPOSAL_TEXT))
        with patch("openbot.router.list_projects", return_value=[
            {"id": "saa-homes", "name": "SAA Homes", "index": (org_mod.ORG / "projects" / "saa-homes" / "INDEX.md").read_text(encoding="utf-8")}
        ]), patch("openbot.heartbeat.heartbeat_enabled", return_value=True), patch(
            "openbot.org.project_tools", return_value={"heartbeat_offer": "on"}
        ):
            rows = pending_approvals()
        kinds = [row.get("kind") for row in rows]
        self.assertIn("proposal", kinds)
        prop = next(row for row in rows if row.get("kind") == "proposal")
        self.assertIn("do_proposal", [c["id"] for c in prop.get("choices") or []])
        self.assertNotIn("heartbeat", kinds)

    def test_unset_policy_notifies_code(self):
        parsed = parse_proposal_from_text(PROPOSAL_TEXT)
        write_proposal("saa-homes", parsed)
        ok, reason = auto_labor_allowed("saa-homes", parsed)
        self.assertFalse(ok)
        self.assertIn("notify", reason)

    def test_code_auto_financial_notify_is_adjustable(self):
        patch_project_tools(
            "saa-homes",
            {
                "auto_policy": {
                    "code": "auto",
                    "research": "auto",
                    "ops": "notify",
                    "financial": "notify",
                }
            },
        )
        code = prove_decision_loop("saa-homes", PROPOSAL_TEXT)
        self.assertEqual(code["class"], "code")
        self.assertTrue(code["allowed"], code["reason"])
        self.assertEqual(code["preset"], "builder")
        price = prove_decision_loop(
            "saa-homes",
            "Why: Price is too low for the week Horizon\n"
            "Horizon: 1 live CHFA page\n"
            "Evidence: VERIFIED\n"
            "Alternatives: Leave price\n"
            "Review: none\n"
            "Lane: code\n"
            "Next: Change the listing price to 2500\n"
            "Auto: yes\n"
            "Uncertainties: none\n"
            "Discuss: Is this a price change Adam should see?\n",
        )
        self.assertEqual(price["class"], "financial")
        self.assertFalse(price["allowed"])
        self.assertIn("financial", price["reason"])
        patch_project_tools("saa-homes", {"auto_policy": {"code": "auto", "financial": "auto", "ops": "notify", "research": "auto"}})
        price_auto = prove_decision_loop(
            "saa-homes",
            "Why: Price is too low for the week Horizon\n"
            "Horizon: 1 live CHFA page\n"
            "Evidence: VERIFIED\n"
            "Alternatives: Leave price\n"
            "Review: none\n"
            "Lane: code\n"
            "Next: Change the listing price to 2500\n"
            "Auto: yes\n"
            "Uncertainties: none\n"
            "Discuss: Confirm the new price.\n",
        )
        self.assertTrue(price_auto["allowed"], price_auto["reason"])
        patch_project_tools(
            "saa-homes",
            {"auto_policy": {"code": "auto", "financial": "notify", "ops": "notify", "research": "auto"}},
        )
        pay_notify = prove_decision_loop(
            "saa-homes",
            "Why: Ads wallet is empty\n"
            "Horizon: 1 live CHFA page\n"
            "Evidence: VERIFIED\n"
            "Alternatives: Pause ads\n"
            "Review: none\n"
            "Lane: ops\n"
            "Next: Pay the Stripe invoice for ads\n"
            "Auto: yes\n"
            "Uncertainties: none\n"
            "Discuss: Should we spend?\n",
        )
        self.assertEqual(pay_notify["class"], "financial")
        self.assertFalse(pay_notify["allowed"])
        self.assertIn("financial", pay_notify["reason"])
        patch_project_tools(
            "saa-homes",
            {"auto_policy": {"code": "auto", "financial": "auto", "ops": "notify", "research": "auto"}},
        )
        pay_auto = prove_decision_loop(
            "saa-homes",
            "Why: Ads wallet is empty\n"
            "Horizon: 1 live CHFA page\n"
            "Evidence: VERIFIED\n"
            "Alternatives: Pause ads\n"
            "Review: none\n"
            "Lane: ops\n"
            "Next: Pay the Stripe invoice for ads\n"
            "Auto: yes\n"
            "Uncertainties: none\n"
            "Discuss: Should we spend?\n",
        )
        self.assertEqual(pay_auto["class"], "financial")
        self.assertTrue(pay_auto["allowed"], pay_auto["reason"])

    def test_ops_toggle(self):
        parsed = {
            "why": "Gateway is stale",
            "horizon": "1 live CHFA page",
            "evidence": "VERIFIED",
            "review": "none",
            "lane": "ops",
            "next": "Restart the Hermes gateway",
            "auto": "yes",
            "discuss": "Is restart enough?",
        }
        write_proposal("saa-homes", parsed)
        patch_project_tools("saa-homes", {"auto_policy": {"code": "auto", "research": "auto", "ops": "notify", "financial": "notify"}})
        ok, reason = auto_labor_allowed("saa-homes")
        self.assertFalse(ok)
        self.assertIn("ops", reason)
        patch_project_tools("saa-homes", {"auto_policy": {"code": "auto", "research": "auto", "ops": "auto", "financial": "notify"}})
        ok, reason = auto_labor_allowed("saa-homes")
        self.assertTrue(ok, reason)

    def test_run_now_does_not_attach_cron(self):
        with patch("openbot.heartbeat.threading.Thread"):
            info = run_heartbeat_now("saa-homes")
        self.assertTrue(info.get("ok"))
        self.assertEqual(info.get("action"), "run_now")
        self.assertFalse(heartbeat_enabled("saa-homes"))
        self.assertEqual(classify_proposal({"lane": "code", "next": "fix form", "why": "404"}), "code")
        self.assertEqual(classify_proposal({"lane": "ops", "next": "Pay the Stripe invoice", "why": "wallet"}), "financial")
        self.assertEqual(classify_proposal({"lane": "code", "next": "Change the listing price", "why": "too low"}), "financial")
        self.assertEqual(classify_proposal({"lane": "code", "next": "Publish the CHFA page live", "why": "go live"}), "code")
