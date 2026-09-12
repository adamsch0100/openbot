"""Compressed month: file brain + real gates. No live SAA Think."""

from __future__ import annotations

import unittest

from openbot.brainmonth import DESK_ID, format_month, run_month


def _day(report: dict, num: int) -> dict:
    for row in report.get("rows") or []:
        if row.get("day") == num:
            return row
    raise AssertionError(f"missing day {num}")


class BrainMonthTests(unittest.TestCase):
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
        self.assertTrue(price["auto_mark"], "brain may mark Auto yes; board policy holds")
        pay = _day(self.report, 11)
        self.assertEqual(pay["class"], "financial")
        self.assertFalse(pay["allowed"])
        ops = _day(self.report, 5)
        self.assertEqual(ops["class"], "ops")
        self.assertFalse(ops["allowed"])
        self.assertIn("ops", ops["reason"])

    def test_publish_and_delete_never_auto(self):
        publish = _day(self.report, 13)
        self.assertFalse(publish["allowed"])
        self.assertIn("Accept gate", publish["reason"])
        delete = _day(self.report, 20)
        self.assertFalse(delete["allowed"])
        self.assertIn("Accept gate", delete["reason"])

    def test_failed_labor_blocks_next_auto(self):
        fail = _day(self.report, 8)
        self.assertTrue(fail["allowed"], fail["reason"])
        self.assertEqual(fail["labor"], "failed")
        nxt = _day(self.report, 9)
        self.assertEqual(nxt["review_in"], "failed")
        self.assertFalse(nxt["allowed"])
        self.assertIn("did not implement", nxt["reason"])

    def test_research_can_auto_under_recommended_mix(self):
        research = _day(self.report, 7)
        self.assertEqual(research["class"], "research")
        self.assertTrue(research["allowed"], research["reason"])
        self.assertEqual(research["labor"], "implemented")

    def test_month_moves_both_ways(self):
        self.assertGreater(self.report["auto"], 0)
        self.assertGreater(self.report["held"], 0)
        self.assertEqual(self.report["failed"], 1)
        text = format_month(self.report)
        self.assertIn("Compressed month", text)
        self.assertIn("NOTIFY", text)
        self.assertIn("AUTO", text)


if __name__ == "__main__":
    unittest.main()
