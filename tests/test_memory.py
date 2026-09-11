"""Operator profile, decisions log, audit, prune, Reject → rule."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openbot.bus as bus_mod
import openbot.org as org_mod
import openbot.store as store_mod
from openbot.bus import cos_file_reply, law_extra
from openbot.gitutil import snapshot
from openbot.memory import (
    append_decision,
    collapse_blockers,
    decisions_excerpt,
    memory_packet_extra,
    operator_packet,
    prune_reply,
    teach_from_reject,
)
from openbot.router import decide_diff
from openbot.store import write_job


class CollapseBlockerTests(unittest.TestCase):
    def test_keeps_real_blocker_drops_dupes(self):
        text = "# SAA\n\nNow: Ready.\nBlocker: —\nBlocker: —\nNext: On schedule.\n"
        out = collapse_blockers(text)
        self.assertEqual(out.count("Blocker:"), 1)
        self.assertIn("Blocker: —", out)

    def test_prefers_never_over_dash(self):
        text = "Blocker: —\nBlocker: Do not Restart imported SAA Hermes\n"
        out = collapse_blockers(text)
        self.assertEqual(out.count("Blocker:"), 1)
        self.assertIn("Do not Restart imported SAA Hermes", out)


class MemoryFilesTests(unittest.TestCase):
    def test_operator_packet_uses_aimed_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "alpha"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text(
                "# Alpha\n\nHorizon-week: Ship desk honesty · operators · via INDEX · proof Goals tab\n",
                encoding="utf-8",
            )
            with patch.object(org_mod, "ORG", dest):
                packet = operator_packet("alpha")
                self.assertIn("OPERATOR:", packet)
                self.assertIn("Adam", packet)
                self.assertIn("Aimed this week: Ship desk honesty", packet)
                self.assertIn("Labor serves Horizons", packet)

    def test_decisions_excerpt_instance_and_ceo(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "projects" / "alpha").mkdir(parents=True)
            profile = dest / "profile.json"
            profile.write_text(json.dumps({"projects": [{"id": "alpha", "name": "alpha"}]}), encoding="utf-8")
            with patch.object(org_mod, "ORG", dest), patch.object(org_mod, "PROFILE_PATH", profile):
                append_decision(None, "Do not Accept parked restore cards", "parked on purpose")
                append_decision("alpha", "Do not Restart imported Hermes", "live box owns cron")
                blob = decisions_excerpt("alpha")
                self.assertIn("instance:", blob)
                self.assertIn("alpha:", blob)
                self.assertIn("parked restore", blob)
                self.assertIn("Restart imported Hermes", blob)

    def test_packet_extra_includes_operator_and_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "openbot"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text(
                "# OttoBot\n\nHorizon-week: Honest CEO desks · Adam · via board · proof Goals\n",
                encoding="utf-8",
            )
            profile = dest / "profile.json"
            profile.write_text(json.dumps({"projects": [{"id": "openbot", "name": "OttoBot"}]}), encoding="utf-8")
            with patch.object(org_mod, "ORG", dest), patch.object(org_mod, "PROFILE_PATH", profile):
                append_decision("openbot", "Labor serves Horizons", "Goals board")
                extra = memory_packet_extra("openbot")
                self.assertIn("OPERATOR:", extra)
                self.assertIn("DECISIONS", extra)
                self.assertIn("Aimed this week: Honest CEO desks", extra)
                law = law_extra("builder", "openbot")
                self.assertIn("Horizons", law)

    def test_reject_teaches_rule_and_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "projects" / "openbot").mkdir(parents=True)
            profile = dest / "profile.json"
            profile.write_text(json.dumps({"projects": [{"id": "openbot", "name": "OttoBot"}]}), encoding="utf-8")
            old_bus = (bus_mod.ORG, bus_mod.RULES)
            bus_mod.ORG = dest
            bus_mod.RULES = dest / "RULES.md"
            try:
                with patch.object(org_mod, "ORG", dest), patch.object(org_mod, "PROFILE_PATH", profile):
                    saved = teach_from_reject("openbot", "abc123", "rewrite the footer", "wrong voice")
                    self.assertIn("never silently re-apply rejected job abc123", saved)
                    self.assertIn("wrong voice", saved)
                    self.assertIn("rejected diff abc123", decisions_excerpt("openbot"))
                    self.assertTrue(bus_mod.RULES.is_file())
            finally:
                bus_mod.ORG, bus_mod.RULES = old_bus

    def test_prune_collapses_duplicate_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            project = dest / "projects" / "saa-homes"
            project.mkdir(parents=True)
            (project / "INDEX.md").write_text(
                "# SAA Homes\n\nNow: Ready.\nBlocker: —\nBlocker: —\nHorizon-week: 1 live city · NoCO · via URL · proof form 200\n",
                encoding="utf-8",
            )
            profile = dest / "profile.json"
            profile.write_text(
                json.dumps({"projects": [{"id": "saa-homes", "name": "SAA Homes"}]}),
                encoding="utf-8",
            )
            with patch.object(org_mod, "ORG", dest), patch.object(org_mod, "PROFILE_PATH", profile):
                reply = prune_reply("saa-homes")
                self.assertIn("collapsed duplicate Blocker", reply)
                text = (project / "INDEX.md").read_text(encoding="utf-8")
                self.assertEqual(text.count("Blocker:"), 1)

    def test_cos_prune_and_audit_phrases(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            profile = dest / "profile.json"
            profile.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(org_mod, "ORG", dest), patch.object(org_mod, "PROFILE_PATH", profile):
                prune = cos_file_reply("weekly review please")
                self.assertIn("Weekly prune", prune or "")
                audit = cos_file_reply("memory audit")
                self.assertIn("Memory audit", audit or "")


class DecideRejectTeachesTests(unittest.TestCase):
    def test_decide_diff_reject_writes_rule(self):
        old_jobs = store_mod.JOBS
        old_brains = store_mod.BRAINS
        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_bus = (bus_mod.ORG, bus_mod.RULES)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp)
                store_mod.JOBS = dest / "jobs"
                store_mod.BRAINS = dest / "brains"
                store_mod.JOBS.mkdir()
                store_mod.BRAINS.mkdir()
                (store_mod.BRAINS / "INDEX.md").write_text("Now: test\n", encoding="utf-8")
                org_mod.ORG = dest
                org_mod.PROFILE_PATH = dest / "profile.json"
                org_mod.PROFILE_PATH.write_text(
                    json.dumps({"projects": [{"id": "openbot", "name": "OttoBot"}]}),
                    encoding="utf-8",
                )
                (dest / "projects" / "openbot").mkdir(parents=True)
                (dest / "projects" / "openbot" / "INDEX.md").write_text("# OttoBot\nNow: Ready.\n", encoding="utf-8")
                bus_mod.ORG = dest
                bus_mod.RULES = dest / "RULES.md"
                work = dest / "work"
                work.mkdir()
                import subprocess

                subprocess.run(["git", "init"], cwd=work, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "test@local"], cwd=work, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=work, check=True, capture_output=True)
                (work / "app.txt").write_text("one\n", encoding="utf-8")
                subprocess.run(["git", "add", "app.txt"], cwd=work, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "init"], cwd=work, check=True, capture_output=True)
                snap = snapshot(str(work))
                (work / "app.txt").write_text("two\n", encoding="utf-8")
                write_job(
                    {
                        "id": "aabbcc11",
                        "at": "2026-09-11T00:00:00Z",
                        "preset": "builder",
                        "engine": "OpenCode",
                        "project_id": "openbot",
                        "folder": str(work),
                        "message": "change the footer",
                        "diff_pending": True,
                        "git_snapshot": snap,
                    }
                )
                result = decide_diff("aabbcc11", accept=False, reason="wrong voice")
                self.assertTrue(result.get("ok"))
                self.assertTrue(result.get("rejected"))
                self.assertEqual((work / "app.txt").read_text(encoding="utf-8"), "one\n")
                rules = bus_mod.RULES.read_text(encoding="utf-8")
                self.assertIn("aabbcc11", rules)
                self.assertIn("wrong voice", rules)
                self.assertIn("rejected diff aabbcc11", decisions_excerpt("openbot"))
        finally:
            store_mod.JOBS = old_jobs
            store_mod.BRAINS = old_brains
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            bus_mod.ORG, bus_mod.RULES = old_bus
