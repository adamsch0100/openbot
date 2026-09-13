"""Compressed month v2: scar, proof, horizon, park. No live SAA Think."""

from __future__ import annotations

import unittest

from openbot.brainmonth import DESK_ID, format_month, run_month, run_on_desk, tick
from openbot.decide import (
    auto_labor_allowed,
    classify_proposal,
    close_proposal,
    ingest_think_result,
    last_labor_review,
    load_scar,
    load_skip_note,
    proposal_packet_extra,
    write_proposal,
)
from openbot.org import patch_scope
from openbot.store import write_job


def _day(report: dict, num: int) -> dict:
    for row in report.get("rows") or []:
        if row.get("day") == num:
            return row
    raise AssertionError(f"missing day {num}")


class BrainMonthV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_month(22)

    def test_twenty_two_weekdays_on_isolated_desk(self):
        self.assertTrue(self.report.get("ok"))
        self.assertEqual(self.report.get("days"), 22)
        self.assertEqual(self.report.get("desk"), DESK_ID)
        self.assertEqual(len(self.report.get("rows") or []), 22)
        self.assertNotIn("saa-homes", DESK_ID)

    def test_code_auto_then_review_implemented(self):
        d1 = _day(self.report, 1)
        self.assertEqual(d1["class"], "code")
        self.assertTrue(d1["allowed"], d1["reason"])
        self.assertEqual(d1["labor"], "implemented")
        d2 = _day(self.report, 2)
        self.assertEqual(d2["review_in"], "implemented")
        self.assertTrue(d2["allowed"], d2["reason"])

    def test_financial_and_ops_stay_notify(self):
        price = _day(self.report, 4)
        self.assertEqual(price["class"], "financial")
        self.assertFalse(price["allowed"])
        self.assertIn("notify", price["reason"])
        pay = _day(self.report, 11)
        self.assertEqual(pay["class"], "financial")
        self.assertFalse(pay["allowed"])
        ops = _day(self.report, 5)
        self.assertEqual(ops["class"], "ops")
        self.assertFalse(ops["allowed"])

    def test_failed_labor_blocks_next_two_code_ticks(self):
        fail = _day(self.report, 8)
        self.assertTrue(fail["allowed"], fail["reason"])
        self.assertEqual(fail["labor"], "failed")
        d9 = _day(self.report, 9)
        self.assertFalse(d9["allowed"])
        self.assertIn("did not implement", d9["reason"])
        d10 = _day(self.report, 10)
        self.assertFalse(d10["allowed"], "scar must survive the next Think")
        self.assertEqual(d10.get("scar"), "failed")

    def test_off_horizon_unit_test(self):
        row = _day(self.report, 12)
        self.assertFalse(row["allowed"])
        self.assertIn("off_horizon", row["reason"])

    def test_publish_parks_and_code_can_still_move(self):
        publish = _day(self.report, 13)
        self.assertEqual(publish.get("status"), "parked")
        self.assertFalse(publish["allowed"])
        self.assertGreaterEqual(publish.get("parked") or 0, 1)
        later = _day(self.report, 18)
        self.assertTrue(later["allowed"], later["reason"])
        self.assertEqual(later["class"], "code")

    def test_financial_repeat_on_second_price(self):
        row = _day(self.report, 19)
        self.assertEqual(row["class"], "financial")
        self.assertFalse(row["allowed"])
        self.assertGreaterEqual(row.get("financial_repeat") or 0, 2)

    def test_research_can_auto_under_recommended_mix(self):
        research = _day(self.report, 7)
        self.assertEqual(research["class"], "research")
        self.assertTrue(research["allowed"], research["reason"])

    def test_month_moves_both_ways(self):
        self.assertGreater(self.report["auto"], 0)
        self.assertGreater(self.report["held"], 0)
        self.assertEqual(self.report["failed"], 1)
        text = format_month(self.report)
        self.assertIn("Compressed month", text)
        self.assertIn("NOTIFY", text)
        self.assertIn("AUTO", text)


class BrainV2GateTests(unittest.TestCase):
    def test_classify_from_next_not_why(self):
        self.assertEqual(
            classify_proposal({"lane": "code", "why": "listing price is too low", "next": "Restore the CHFA form 200"}),
            "code",
        )
        self.assertEqual(
            classify_proposal({"lane": "code", "why": "404", "next": "Change the listing price"}),
            "financial",
        )

    def test_unproven_when_receipt_has_no_proof(self):
        def body(pid):
            write_proposal(
                pid,
                {
                    "why": "404 blocks the week",
                    "horizon": "CHFA",
                    "evidence": "verified",
                    "review": "none",
                    "lane": "code",
                    "next": "Restore the CHFA contact form",
                    "auto": "yes",
                    "proof": "form 200",
                    "at": "2026-10-01T09:00:00Z",
                },
            )
            write_job(
                {
                    "id": "unpv1",
                    "at": "2026-10-01T10:00:00Z",
                    "project_id": pid,
                    "preset": "builder",
                    "engine": "OpenCode",
                    "text": "done",
                }
            )
            return last_labor_review(pid)

        audit = run_on_desk(body)
        self.assertEqual(audit["review"], "unproven")

    def test_drifted_wrong_lane(self):
        def body(pid):
            write_proposal(
                pid,
                {
                    "why": "404",
                    "evidence": "verified",
                    "review": "none",
                    "lane": "code",
                    "next": "Restore the CHFA form",
                    "auto": "yes",
                    "proof": "form 200",
                    "at": "2026-10-01T09:00:00Z",
                },
            )
            write_job(
                {
                    "id": "dr1",
                    "at": "2026-10-01T10:00:00Z",
                    "project_id": pid,
                    "preset": "research",
                    "engine": "Hermes Agent",
                    "text": "form 200",
                }
            )
            return last_labor_review(pid)

        self.assertEqual(run_on_desk(body)["review"], "drifted")

    def test_skip_note_keeps_scar(self):
        def body(pid):
            write_proposal(
                pid,
                {
                    "why": "404",
                    "evidence": "verified",
                    "review": "failed",
                    "lane": "code",
                    "next": "Restore form",
                    "auto": "no",
                    "at": "2026-10-01T09:00:00Z",
                },
            )
            write_job(
                {
                    "id": "f1",
                    "at": "2026-10-01T10:00:00Z",
                    "project_id": pid,
                    "preset": "builder",
                    "blocker": "OpenCode binary missing",
                    "text": "failed",
                }
            )
            last_labor_review(pid)
            close_proposal(pid, "skipped", "skipped after fail; scar stays")
            extra = proposal_packet_extra(pid, "HEARTBEAT_TASK weekday")
            return {"scar": load_scar(pid).get("review"), "note": load_skip_note(pid), "extra": extra}

        out = run_on_desk(body)
        self.assertEqual(out["scar"], "failed")
        self.assertIn("scar stays", out["note"])
        self.assertIn("SKIP NOTE", out["extra"])
        self.assertIn("SCAR", out["extra"])

    def test_unknown_evidence_blocks(self):
        def body(pid):
            write_proposal(
                pid,
                {
                    "why": "maybe 404",
                    "evidence": "UNKNOWN",
                    "review": "none",
                    "lane": "code",
                    "next": "Restore the CHFA form 200",
                    "auto": "yes",
                },
            )
            return auto_labor_allowed(pid)

        ok, reason = run_on_desk(body)
        self.assertFalse(ok)
        self.assertIn("UNKNOWN", reason)

    def test_week_proven_stops(self):
        def body(pid):
            patch_scope(pid, None, "Last", "form 200 live url https://example.com/chfa")
            patch_scope(pid, None, "Now", "week closed")
            return tick(pid, 3, "Fix the contact form handler unit test", "ok")

        row = run_on_desk(body)
        self.assertFalse(row["allowed"])
        self.assertIn("week already proven", row["reason"])

    def test_ingest_unknown_labeled(self):
        def body(pid):
            return ingest_think_result(
                pid,
                "HEARTBEAT_TASK",
                "Why: source missing\nHorizon: CHFA\nEvidence: UNKNOWN\n"
                "Alternatives: wait\nReview: none\nLane: code\nNext: Restore form 200\n"
                "Auto: yes\nUncertainties: none\nDiscuss: ?\nProof: form 200\n",
                job_id="u1",
            )

        decided = run_on_desk(body)
        self.assertEqual(decided.get("proposal", {}).get("evidence"), "unknown")


if __name__ == "__main__":
    unittest.main()
