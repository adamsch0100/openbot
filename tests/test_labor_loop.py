"""Labor loop: Support tickets, hard gate, drafts, retired CEOs."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import openbot.bus as bus_mod
import openbot.config as config_mod
import openbot.org as org_mod
import openbot.playskills as skills_mod
import openbot.store as store_mod
import openbot.tickets as tickets_mod
from openbot.bus import (
    connector_mode,
    create_gate_approval,
    decide_approval,
    evidence_has_source,
    expire_approvals,
    list_approvals,
    list_drafts,
    move_draft,
    should_park_irreversible,
    write_draft,
    write_evidence_record,
)
from openbot.hermes_import import _refuse_retired
from openbot.org import RETIRED_CEO_IDS, SUPPORT_CEO_ID, ensure_support_project, retire_archived_ceos
from openbot.router import _effective_skills, pending_approvals
from openbot.store import clean_memory_text
from openbot.tickets import (
    classify_kind,
    create_ticket,
    draft_announce,
    ingest_x_mentions,
    on_diff_decided,
    public_ticket,
    route_to_builder,
    working_on,
)


class LaborLoopIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._store = {
            "root": store_mod.ROOT,
            "brains": store_mod.BRAINS,
            "jobs": store_mod.JOBS,
            "index": store_mod.INDEX,
        }
        self._org = {
            "root": org_mod.ROOT,
            "org": org_mod.ORG,
            "profile": org_mod.PROFILE_PATH,
            "homes": org_mod.HERMES_HOMES,
        }
        self._bus_org = bus_mod.ORG
        self._bus_root = bus_mod.ROOT
        self._bus_log = bus_mod.ACTION_LOG
        self._tickets_org = tickets_mod.ORG
        self._skills_org = skills_mod.ORG
        self._skills_root = skills_mod.SKILLS_ROOT
        self._settings = config_mod.SETTINGS_PATH

        store_mod.ROOT = self.home
        store_mod.BRAINS = self.home / "brains"
        store_mod.JOBS = self.home / "jobs"
        store_mod.INDEX = self.home / "brains" / "INDEX.md"
        store_mod.BRAINS.mkdir(parents=True, exist_ok=True)
        store_mod.JOBS.mkdir(parents=True, exist_ok=True)
        store_mod.INDEX.write_text("Now: test\nLast: —\nNext: —\nBlocker: —\n", encoding="utf-8")
        config_mod.SETTINGS_PATH = self.home / "openbot.local.json"
        org_mod.ROOT = self.home
        org_mod.ORG = self.home / "org"
        org_mod.PROFILE_PATH = self.home / "org" / "profile.json"
        org_mod.HERMES_HOMES = self.home / "hermes-homes"
        org_mod.ORG.mkdir(parents=True, exist_ok=True)
        bus_mod.ROOT = self.home
        bus_mod.ORG = org_mod.ORG
        bus_mod.ACTION_LOG = org_mod.ORG / "ACTION_LOG.md"
        tickets_mod.ORG = org_mod.ORG
        skills_mod.ORG = org_mod.ORG
        skills_mod.SKILLS_ROOT = org_mod.ORG / "skills"
        (org_mod.ORG / "projects" / "support").mkdir(parents=True, exist_ok=True)
        (org_mod.ORG / "projects" / "support" / "INDEX.md").write_text(
            "# Support\n\nNow: Ready.\nLast: —\nNext: —\nBlocker: —\n",
            encoding="utf-8",
        )
        (org_mod.ORG / "projects" / "openbot").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        store_mod.ROOT = self._store["root"]
        store_mod.BRAINS = self._store["brains"]
        store_mod.JOBS = self._store["jobs"]
        store_mod.INDEX = self._store["index"]
        org_mod.ROOT = self._org["root"]
        org_mod.ORG = self._org["org"]
        org_mod.PROFILE_PATH = self._org["profile"]
        org_mod.HERMES_HOMES = self._org["homes"]
        bus_mod.ROOT = self._bus_root
        bus_mod.ORG = self._bus_org
        bus_mod.ACTION_LOG = self._bus_log
        tickets_mod.ORG = self._tickets_org
        skills_mod.ORG = self._skills_org
        skills_mod.SKILLS_ROOT = self._skills_root
        config_mod.SETTINGS_PATH = self._settings
        self.tmp.cleanup()


class RetiredOrgTests(LaborLoopIsolation):
    def test_retire_keeps_nadia_and_listlogic(self):
        saved = {
            "projects": [
                {"id": "openbot", "name": "openbot", "primary": True},
                {"id": "nadia", "name": "Nadia"},
                {"id": "listlogic", "name": "ListLogic"},
                {"id": "saa-homes", "name": "SAA Homes"},
                {"id": "nadia-marketing", "name": "Nadia Marketing"},
            ]
        }
        out = retire_archived_ceos(saved)
        ids = {str(row.get("id")) for row in out.get("projects") or []}
        self.assertEqual(ids, {"openbot", "nadia", "listlogic", "saa-homes"})
        self.assertNotIn("nadia", RETIRED_CEO_IDS)
        self.assertNotIn("listlogic", RETIRED_CEO_IDS)
        self.assertIn("nadia-marketing", RETIRED_CEO_IDS)
        self.assertIn("app", RETIRED_CEO_IDS)
        self.assertNotIn("nadia-marketing", ids)
        from openbot.org import MANUAL_SEAT_CEO_IDS

        self.assertIn("nadia", MANUAL_SEAT_CEO_IDS)
        self.assertIn("listlogic", MANUAL_SEAT_CEO_IDS)

    def test_hosted_app_folder_is_not_a_ceo(self):
        from openbot.org import _host_identity, ensure_org

        saved = {
            "projects": [
                {"id": "app", "name": "app", "primary": True, "folder": "/app"},
                {"id": "openbot", "name": "INDEX", "primary": False},
                {"id": "nadia-marketing", "name": "Nadia Marketing"},
                {"id": "saa-homes", "name": "SAA Homes"},
                {"id": "support", "name": "Support"},
            ]
        }
        pid, name = _host_identity("/app", saved)
        self.assertEqual(pid, "openbot")
        self.assertEqual(name, "OpenBot")
        org_mod.PROFILE_PATH.write_text(json.dumps({"projects": saved["projects"], "folder": "/app"}), encoding="utf-8")
        with patch("openbot.org.load_config", return_value={"work_dir": "/app"}):
            listed = {str(row.get("id")): str(row.get("name")) for row in ensure_org()["projects"]}
        self.assertEqual(listed.get("openbot"), "OpenBot")
        self.assertIn("saa-homes", listed)
        self.assertIn("support", listed)
        self.assertNotIn("app", listed)
        self.assertNotIn("nadia-marketing", listed)

    def test_ensure_support_added(self):
        saved = {"projects": [{"id": "openbot", "name": "openbot", "primary": True}]}
        out = ensure_support_project(saved, str(self.home))
        ids = {str(row.get("id")) for row in out.get("projects") or []}
        self.assertIn(SUPPORT_CEO_ID, ids)
        index = org_mod.ORG / "projects" / "support" / "INDEX.md"
        text = index.read_text(encoding="utf-8")
        self.assertIn("Stopline", text)
        self.assertIn("Never Accept", text)

    def test_public_org_lists_support_ceo(self):
        profile = {
            "name": "OPENBOT",
            "role": "cos",
            "folder": str(self.home),
            "projects": [
                {"id": "openbot", "name": "openbot", "role": "ceo", "folder": str(self.home), "primary": True, "workers": []},
                {"id": "support", "name": "Support", "role": "ceo", "folder": str(self.home), "primary": False, "workers": []},
            ],
        }
        org_mod.PROFILE_PATH.write_text(json.dumps(profile), encoding="utf-8")
        listed = {str(row.get("id")) for row in org_mod.public_org()["projects"]}
        self.assertIn("openbot", listed)
        self.assertIn(SUPPORT_CEO_ID, listed)
        self.assertIn(SUPPORT_CEO_ID, {row["id"] for row in org_mod.list_projects()})

    def test_add_project_nadia_listlogic_seat_prefs(self):
        nadia = org_mod.seat_preset_for_name("Nadia")
        self.assertEqual(nadia.get("site_url"), "https://e8solutions.ai")
        self.assertEqual(nadia.get("github_repo"), "adamsch0100/fub-hermes")
        self.assertEqual(nadia.get("goals"), "paid seats · pay for itself first")
        listlogic = org_mod.seat_preset_for_name("ListLogic")
        self.assertEqual(listlogic.get("site_url"), "https://listlogic.homes")
        self.assertEqual(listlogic.get("github_repo"), "adamsch0100/saahomes")
        self.assertEqual(listlogic.get("goals"), "paid activations · pay for itself first")

    def test_empty_ceo_index_is_p_and_l(self):
        text = org_mod._empty_index("Acme", "/tmp/acme")
        self.assertIn("How this CEO operates", text)
        self.assertIn("No CFO/COO bots", text)
        self.assertIn("Never auto-post", text)
        self.assertIn("Run this company", text)

    def test_add_project_allows_nadia_and_listlogic(self):
        nadia = org_mod.add_project(str(self.home), "Nadia")
        self.assertEqual(nadia.get("project_id"), "nadia")
        listlogic = org_mod.add_project(str(self.home), "ListLogic")
        self.assertEqual(listlogic.get("project_id"), "listlogic")
        with self.assertRaises(ValueError):
            _refuse_retired("Nadia Marketing")
        with self.assertRaises(ValueError):
            org_mod.add_project(str(self.home), "Nadia Marketing")

    def test_add_project_unarchives_index(self):
        dest = org_mod._project_dir("nadia")
        dest.mkdir(parents=True)
        (dest / "INDEX.md").write_text(
            "# nadia (archived)\n\n"
            "Now: Retired from this OpenBot board. Folder kept on disk.\n"
            "Last: Removed from routing.\n"
            "Next: Re-add as a CEO only if the operator brings this product back.\n"
            "Blocker: —\n\n"
            "This CEO is not in the live org. Keep Cos, OpenBot, SAA Homes, and Support.\n\n"
            "# Nadia\n\nNow: Seated on OttoBot.\n",
            encoding="utf-8",
        )
        org_mod.add_project(str(self.home), "Nadia")
        text = (dest / "INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn("Retired from this OpenBot board", text)
        self.assertIn("# Nadia", text)

    def test_add_project_pmill_seat_prefs(self):
        prefs = org_mod.seat_preset_for_name("Pmill")
        self.assertEqual(prefs.get("site_url"), "https://pmill.ai")
        self.assertEqual(prefs.get("github_repo"), "adamsch0100/pmillsports")
        self.assertEqual(prefs.get("railway"), "victorious-presence")
        self.assertEqual(prefs.get("goals"), "profitability · pay for itself first")
        data = org_mod.add_project(str(self.home), "Pmill")
        self.assertEqual(data.get("project_id"), "pmill")
        ceo = next(row for row in data["projects"] if row["id"] == "pmill")
        tools = ceo.get("tools") or {}
        self.assertEqual(tools.get("site_url"), "https://pmill.ai")
        self.assertEqual(tools.get("github_repo"), "adamsch0100/pmillsports")
        self.assertEqual(tools.get("railway"), "victorious-presence")
        self.assertTrue(tools.get("mcp_github"))
        self.assertTrue(tools.get("authorize_site"))
        self.assertTrue(tools.get("authorize_railway"))
        index = (ceo.get("index") or "")
        self.assertIn("Goals: profitability · pay for itself first", index)
        self.assertIn("Site: https://pmill.ai", index)
        self.assertIn("Railway: victorious-presence", index)

    def test_clean_memory_strips_contributor_banner(self):
        raw = (
            "Saved inbox/ops.md. !!! CONTRIBUTOR TIER — TRAINS ON YOUR DATA !!! "
            "This is Meta's contributor tier. Selecting it permits Meta to use your "
            "prompts and completions to train future Meta models."
        )
        cleaned = clean_memory_text(raw)
        self.assertIn("Saved inbox/ops.md.", cleaned)
        self.assertNotIn("CONTRIBUTOR", cleaned)
        self.assertNotIn("contributor tier", cleaned.lower())

    def test_pending_skips_retired_login(self):
        jobs = [
            {
                "id": "cron-nadia-marketing-1",
                "project_id": "nadia-marketing",
                "login_wall": True,
                "at": "2026-09-06T01:33:08Z",
                "engine": "Hermes Agent",
                "preset": "ops",
            }
        ]
        live = [
            {"id": "openbot", "name": "OpenBot"},
            {"id": "saa-homes", "name": "SAA Homes"},
            {"id": "support", "name": "Support"},
        ]
        with patch("openbot.router.list_jobs", return_value=jobs):
            with patch("openbot.router.list_projects", return_value=live):
                rows = pending_approvals()
        self.assertFalse(any(row.get("project_id") == "nadia-marketing" for row in rows))


class TicketLoopTests(LaborLoopIsolation):
    def test_classify_and_suggest_faq_drafts(self):
        self.assertEqual(classify_kind("how do I pin a model"), "faq")
        self.assertEqual(classify_kind("the builder crash is a bug"), "bug")
        ticket = create_ticket("How do I start", "how do I open the board", source="suggest", auto_route=True)
        self.assertEqual(ticket["kind"], "faq")
        self.assertEqual(ticket["phase"], "triage")
        self.assertTrue(ticket.get("draft_id"))
        drafts = list_drafts("support", "drafts")
        self.assertTrue(any(row.get("id") == ticket["draft_id"] for row in drafts))
        pub = public_ticket(ticket)
        self.assertEqual(pub["id"], ticket["id"])
        work = working_on()
        self.assertTrue(any(row["id"] == ticket["id"] for row in work["open"]))

    def test_bug_routes_to_builder_handoff(self):
        ticket = create_ticket("Login crash", "bug: builder crash on submit", source="suggest", auto_route=True)
        self.assertEqual(ticket["kind"], "bug")
        self.assertEqual(ticket["phase"], "building")
        self.assertTrue(ticket.get("handoff_id"))
        handoff = org_mod.ORG / "projects" / "openbot" / "bus" / "handoffs"
        files = list(handoff.glob("*.md")) if handoff.is_dir() else []
        self.assertTrue(files)

    def test_accept_ships_and_drafts_announce(self):
        ticket = create_ticket("Add a button", "please add a feature for dark mode", source="suggest", auto_route=False)
        ticket = route_to_builder(ticket["id"])
        job = {"id": "abc123", "diff_pending": True, "engine": "OpenCode"}
        from openbot.tickets import on_job_linked

        linked = on_job_linked(ticket["id"], job)
        self.assertEqual(linked["phase"], "in_review")
        shipped = on_diff_decided({"id": "abc123"}, True)
        self.assertEqual(shipped["phase"], "shipped")
        self.assertTrue(shipped.get("draft_id"))
        announce = draft_announce(ticket["id"])
        self.assertTrue(announce.get("draft_id"))

    def test_x_ingest_fail_closed(self):
        config_mod.SETTINGS_PATH.write_text(json.dumps({"x_intake_enabled": False}), encoding="utf-8")
        out = ingest_x_mentions()
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "x intake off")
        config_mod.SETTINGS_PATH.write_text(json.dumps({"x_intake_enabled": True}), encoding="utf-8")
        out = ingest_x_mentions()
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "x credentials missing")


class GateDraftEvidenceTests(LaborLoopIsolation):
    def test_park_irreversible(self):
        self.assertTrue(should_park_irreversible("ops", "send this email now"))
        self.assertTrue(should_park_irreversible("builder", "push to origin main"))
        self.assertFalse(should_park_irreversible("ops", "draft a reply, do not send"))
        self.assertFalse(should_park_irreversible("cos", "send this"))
        self.assertFalse(should_park_irreversible("builder", "fix the crash locally"))

    def test_approval_expires_without_auto_approve(self):
        row = create_gate_approval(job_id="job1", project_id="support", kind="irreversible", message="post to x")
        self.assertEqual(row["status"], "pending")
        path = bus_mod.approvals_dir() / f"{row['id']}.json"
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        data = json.loads(path.read_text(encoding="utf-8"))
        data["expires_at"] = past
        path.write_text(json.dumps(data), encoding="utf-8")
        expired = expire_approvals()
        self.assertTrue(any(item["id"] == row["id"] for item in expired))
        listed = list_approvals("expired")
        self.assertEqual(listed[0]["status"], "expired")
        with self.assertRaises(ValueError):
            decide_approval(row["id"], True)

    def test_decide_approval_and_draft_lanes(self):
        approval = create_gate_approval(job_id="job2", project_id="support", kind="irreversible", message="send")
        decided = decide_approval(approval["id"], True)
        self.assertEqual(decided["status"], "approved")
        draft = write_draft(kind="announce", body="Shipped a fix.", project_id="support", title="Announce")
        moved = move_draft(draft["id"], "support", "reviews")
        self.assertEqual(moved["status"], "reviews")
        moved = move_draft(draft["id"], "support", "approved")
        self.assertEqual(moved["status"], "approved")
        self.assertTrue(list_drafts("support", "approved"))

    def test_evidence_bounce_unsourced(self):
        rel = write_evidence_record("job3", project_id="support", produced_by="research", source="", result="prices went up")
        path = self.home / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn("SOURCE: MISSING", text)
        self.assertFalse(evidence_has_source(text))
        ok = write_evidence_record(
            "job4",
            project_id="support",
            produced_by="research",
            source="https://example.com",
            result="listed",
        )
        ok_text = (self.home / ok).read_text(encoding="utf-8")
        self.assertTrue(evidence_has_source(ok_text))

    def test_support_fub_denied(self):
        tools = {
            "connectors": {
                "mcp": {"fub": {"mode": "deny", "ops": True}},
                "skills": {"fub": {"ops": True}, "web-search": {"ops": True}},
            }
        }
        self.assertEqual(connector_mode("fub", tools, "support"), "deny")
        self.assertEqual(connector_mode("followupboss", {}, "support"), "deny")
        skills = _effective_skills("ops", tools, "support")
        self.assertNotIn("fub", (skills or "").split(","))
        self.assertIn("web-search", (skills or "").split(","))


class RoutineSkillSmoke(unittest.TestCase):
    def test_support_triage_template_has_id(self):
        from openbot.routine_templates import get_routine_templates

        rows = get_routine_templates()
        ids = [row["id"] for row in rows]
        self.assertIn("support-triage", ids)
        self.assertIn("pre-deploy-check", ids)
        for row in rows:
            self.assertTrue(row.get("id"))
            self.assertTrue(row.get("steps"))


if __name__ == "__main__":
    unittest.main()
