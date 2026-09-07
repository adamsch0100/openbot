"""Per-CEO collaborator shares. Owner keeps vault; invitees get a scoped session."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import openbot.config as config_mod
import openbot.store as store_mod
from openbot.config import save_settings
from openbot.org import add_project, ensure_org
from openbot.share import (
    allows_project,
    check_job_run,
    create_invite,
    filter_org,
    member_can,
    member_from_session,
    owner_only_path,
    peek_invite,
    project_share,
    redeem_invite,
    remove_member,
    revoke_invite,
    unlock_member,
)
from openbot.store import write_job


class ShareStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_root = store_mod.ROOT
        self._old_brains = store_mod.BRAINS
        self._old_jobs = store_mod.JOBS
        self._old_index = store_mod.INDEX
        self._old_settings = config_mod.SETTINGS_PATH
        self._old_org_root = None
        store_mod.ROOT = self.home
        store_mod.BRAINS = self.home / "brains"
        store_mod.JOBS = self.home / "jobs"
        store_mod.INDEX = self.home / "brains" / "INDEX.md"
        store_mod.BRAINS.mkdir(parents=True, exist_ok=True)
        store_mod.JOBS.mkdir(parents=True, exist_ok=True)
        store_mod.INDEX.write_text("Now: test\nLast: —\nNext: —\nBlocker: —\n", encoding="utf-8")
        config_mod.SETTINGS_PATH = self.home / "openbot.local.json"
        import openbot.org as org_mod

        self._org = org_mod
        self._old_org_root = org_mod.ROOT
        org_mod.ROOT = self.home
        org_mod.ORG = self.home / "org"
        org_mod.PROFILE_PATH = self.home / "org" / "profile.json"
        org_mod.HERMES_HOMES = self.home / "hermes-homes"
        save_settings({"operator_name": "Ada"})
        ensure_org()
        self.project = add_project(str(self.home), "ListLogic")
        self.pid = self.project["projects"][0]["id"] if "projects" in self.project else None
        if not self.pid:
            self.pid = ensure_org()["projects"][0]["id"]

    def tearDown(self):
        store_mod.ROOT = self._old_root
        store_mod.BRAINS = self._old_brains
        store_mod.JOBS = self._old_jobs
        store_mod.INDEX = self._old_index
        config_mod.SETTINGS_PATH = self._old_settings
        if self._old_org_root is not None:
            self._org.ROOT = self._old_org_root
            self._org.ORG = self._old_org_root / "org"
            self._org.PROFILE_PATH = self._old_org_root / "org" / "profile.json"
            self._org.HERMES_HOMES = self._old_org_root / "hermes-homes"
        self.tmp.cleanup()

    def test_invite_redeem_and_session(self):
        invite = create_invite(self.pid)
        self.assertTrue(invite["token"])
        peek = peek_invite(invite["token"])
        self.assertEqual(peek["project_id"], self.pid)
        joined = redeem_invite(invite["token"], "Alex", "help1234")
        self.assertEqual(joined["member"]["display_name"], "Alex")
        self.assertTrue(joined["member"]["permissions"]["chat_write"])
        self.assertFalse(joined["member"]["permissions"]["approve_needs_you"])
        row = member_from_session(joined["token"])
        self.assertIsNotNone(row)
        self.assertTrue(allows_project(row, self.pid))
        self.assertFalse(allows_project(row, "other-ceo"))
        again = unlock_member(joined["member"]["id"], "help1234")
        self.assertEqual(again["member"]["id"], joined["member"]["id"])

    def test_member_cannot_see_other_ceo_or_vault_paths(self):
        invite = create_invite(self.pid)
        joined = redeem_invite(invite["token"], "Alex", "help1234")
        row = member_from_session(joined["token"])
        org = filter_org({"projects": [{"id": self.pid}, {"id": "secret-ceo"}], "index": "staff"}, self.pid)
        ids = [item["id"] for item in org["projects"]]
        self.assertEqual(ids, [self.pid])
        self.assertEqual(org.get("staff"), "")
        self.assertTrue(owner_only_path("/api/keys"))
        self.assertTrue(owner_only_path("/api/logins/use"))
        self.assertFalse(member_can(row, "wiring_edit"))
        self.assertIsNone(check_job_run(row, self.pid, "cos"))
        self.assertIsNotNone(check_job_run(row, None, "cos"))
        self.assertIsNotNone(check_job_run(row, "secret-ceo", "cos"))

    def test_owner_can_revoke_and_remove(self):
        invite = create_invite(self.pid)
        joined = redeem_invite(invite["token"], "Alex", "help1234")
        revoked = revoke_invite(invite["id"])
        self.assertEqual(revoked["status"], "revoked")
        with self.assertRaises(ValueError):
            redeem_invite(invite["token"], "Bo", "help1234")
        removed = remove_member(joined["member"]["id"])
        self.assertEqual(removed["status"], "removed")
        self.assertIsNone(member_from_session(joined["token"]))
        share = project_share(self.pid)
        self.assertEqual(share["members"], [])

    def test_handler_member_cannot_read_vault(self):
        from openbot.server import Handler

        invite = create_invite(self.pid)
        joined = redeem_invite(invite["token"], "Alex", "help1234")
        handler = object.__new__(Handler)
        handler.headers = {"Authorization": f"Bearer {joined['token']}", "Cookie": ""}
        handler._json = lambda *args, **kwargs: None
        self.assertFalse(handler._owner_unlocked())
        self.assertTrue(handler._unlocked())
        self.assertIsNotNone(handler._member())
        self.assertTrue(handler._require_owner())
        self.assertFalse(handler._require_perm("chat_read", self.pid))
        self.assertTrue(handler._require_perm("chat_read", "secret-ceo"))
        self.assertTrue(handler._require_perm("wiring_edit", self.pid))

    def test_spend_ceiling_blocks_jobs(self):
        invite = create_invite(self.pid, spend_ceiling_usd_day=0.01)
        joined = redeem_invite(invite["token"], "Alex", "help1234")
        row = member_from_session(joined["token"])
        write_job(
            {
                "id": "aabbccdd",
                "at": __import__("openbot.store", fromlist=["now_iso"]).now_iso(),
                "usd_estimate": 1.0,
                "project_id": self.pid,
                "actor": {"id": joined["member"]["id"], "kind": "collaborator"},
            }
        )
        row["spend_ceiling_usd_day"] = 0.01
        self.assertIsNotNone(check_job_run(row, self.pid, "builder"))


class ShareUiTests(unittest.TestCase):
    def test_board_has_share_surface(self):
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="shareGate"', html)
        self.assertIn("fillOwnerSharePanel", js)
        self.assertIn("/api/share/redeem", js)
        py = (root / "openbot" / "share.py").read_text(encoding="utf-8")
        self.assertIn("shares.local.json", py)


if __name__ == "__main__":
    unittest.main()
