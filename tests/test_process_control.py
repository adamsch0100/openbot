"""Process control: verifier, retry≠round, store split, single writer, effect keys."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openbot.bus as bus_mod
import openbot.org as org_mod
import openbot.process as process_mod
import openbot.store as store_mod
from openbot.process import (
    attempt_kind,
    claim_effect,
    commit_index_patches,
    complete_effect,
    enrich_receipt,
    is_transient_text,
    parse_verifier,
    process_law_block,
    propose_index_patch,
    reconcile_effects,
    result_trailer,
    split_index_stores,
    verifier_blocks_success,
)


class ProcessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._store = {
            "root": store_mod.ROOT,
            "brains": store_mod.BRAINS,
            "jobs": store_mod.JOBS,
            "index": store_mod.INDEX,
        }
        self._org = {"root": org_mod.ROOT, "org": org_mod.ORG}
        self._bus = {"root": bus_mod.ROOT, "org": bus_mod.ORG}

        store_mod.ROOT = self.home
        store_mod.BRAINS = self.home / "brains"
        store_mod.JOBS = self.home / "jobs"
        store_mod.INDEX = self.home / "brains" / "INDEX.md"
        store_mod.BRAINS.mkdir(parents=True, exist_ok=True)
        store_mod.JOBS.mkdir(parents=True, exist_ok=True)
        store_mod.INDEX.write_text(
            "Now: ready\nLast: —\nNext: ship\nBlocker: —\n\n## Law\nKeep files.\n",
            encoding="utf-8",
        )
        org_mod.ROOT = self.home
        org_mod.ORG = self.home / "org"
        bus_mod.ROOT = self.home
        bus_mod.ORG = org_mod.ORG
        (org_mod.ORG / "projects" / "demo").mkdir(parents=True, exist_ok=True)
        (org_mod.ORG / "projects" / "demo" / "INDEX.md").write_text(
            "Now: ready\nLast: —\nNext: ship\nBlocker: —\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        store_mod.ROOT = self._store["root"]
        store_mod.BRAINS = self._store["brains"]
        store_mod.JOBS = self._store["jobs"]
        store_mod.INDEX = self._store["index"]
        org_mod.ROOT = self._org["root"]
        org_mod.ORG = self._org["org"]
        bus_mod.ROOT = self._bus["root"]
        bus_mod.ORG = self._bus["org"]
        self.tmp.cleanup()

    def test_law_and_trailer(self) -> None:
        law = process_law_block()
        self.assertIn("RETRY ≠ ROUND", law)
        self.assertIn("NESTED HARNESS GAP", law)
        self.assertIn("VERIFY:", result_trailer())

    def test_parse_verifier_and_gate(self) -> None:
        parsed = parse_verifier("done\nVERIFY: fail — no tests\nPROOF: pytest missing")
        self.assertEqual(parsed["status"], "fail")
        self.assertTrue(parsed["stated"])
        blocked, why = verifier_blocks_success(preset="think", result="VERIFY: fail — no tests")
        self.assertTrue(blocked)
        self.assertIn("no tests", why)
        ok, note = verifier_blocks_success(preset="builder", result="x", diff_pending=True)
        self.assertFalse(ok)
        self.assertIn("Accept", note)

    def test_retry_not_round(self) -> None:
        self.assertTrue(is_transient_text("502 gateway timeout"))
        self.assertEqual(attempt_kind(transient=True, new_evidence=False), "retry")
        self.assertEqual(attempt_kind(transient=True, new_evidence=True), "round")
        self.assertEqual(attempt_kind(transient=False, new_evidence=False), "round")

    def test_store_split(self) -> None:
        parts = split_index_stores(store_mod.INDEX.read_text(encoding="utf-8"))
        self.assertIn("Now:", parts["pulse"])
        self.assertIn("## Law", parts["doctrine"])
        self.assertNotIn("## Law", parts["pulse"])

    def test_single_writer_inbox(self) -> None:
        prop = propose_index_patch("demo", {"Last": "verified ship"}, job_id="job1")
        self.assertEqual(prop.get("status"), "proposed")
        applied = commit_index_patches("demo")
        self.assertEqual(len(applied), 1)
        text = (org_mod.ORG / "projects" / "demo" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("Last: verified ship", text)

    def test_effect_claim_once(self) -> None:
        first = claim_effect("demo", kind="publish", payload="post-1", job_id="a")
        second = claim_effect("demo", kind="publish", payload="post-1", job_id="b")
        self.assertTrue(second.get("duplicate"))
        self.assertEqual(first["key"], second["key"])
        open_rows = reconcile_effects("demo")
        self.assertEqual(len(open_rows), 1)
        done = complete_effect("demo", first["key"], receipt="ok", ok=True)
        self.assertEqual(done["status"], "done")
        self.assertEqual(reconcile_effects("demo"), [])

    def test_enrich_receipt(self) -> None:
        rec = enrich_receipt(
            {"id": "abc", "project_id": "demo", "message": "ship landing"},
            result="VERIFY: pass — lint\nPROOF: ruff",
            transient=False,
        )
        self.assertEqual(rec["attempt_kind"], "round")
        self.assertEqual(rec["verify"]["status"], "pass")
        self.assertTrue(rec["process"]["nested_harness_gap"])
        retry = enrich_receipt(
            {"id": "def", "project_id": "demo", "message": "ship landing"},
            result="timeout talking to API",
            transient=True,
        )
        self.assertEqual(retry["attempt_kind"], "retry")
        self.assertEqual(retry["round_key"], rec["round_key"])


if __name__ == "__main__":
    unittest.main()
