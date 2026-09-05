"""Tests for @seat mentions and handoff card metadata."""

import unittest
from pathlib import Path

from openbot import bus


class TestHandoffMetadata(unittest.TestCase):
    """Test handoff metadata added by close_work_job."""

    def test_handoff_metadata_on_multi_step_chain(self):
        """Handoff metadata only set when len(handoff_list) >= 2."""
        # Single-step job (Cos → Builder direct route)
        receipt_single = {
            "id": "test123",
            "preset": "builder",
            "message": "Add a comment",
            "handoff": ["builder"],  # Only 1 item
            "engine": "OpenCode",
        }
        result_single = bus.close_work_job(receipt_single, "Done")
        # Should NOT have handoff_from/to fields (single step)
        self.assertNotIn("handoff_from", result_single)
        self.assertNotIn("handoff_to", result_single)

    def test_handoff_metadata_on_real_chain(self):
        """Handoff metadata set when len(handoff_list) >= 2."""
        # Multi-step job (Cos routed → Builder ran)
        receipt_multi = {
            "id": "test456",
            "preset": "builder",
            "message": "Refactor utils.py",
            "handoff": ["cos", "builder"],  # 2 items (Cos → Builder)
            "engine": "OpenCode",
        }
        result_multi = bus.close_work_job(receipt_multi, "Refactored")
        # Should have handoff metadata
        self.assertEqual(result_multi.get("handoff_from"), "cos")
        self.assertEqual(result_multi.get("handoff_to"), "builder")
        self.assertEqual(result_multi.get("handoff_status"), "complete")
        self.assertEqual(result_multi.get("handoff_task"), "Refactor utils.py")
        self.assertEqual(result_multi.get("handoff_output"), "Refactored")

    def test_handoff_metadata_agent_to_agent(self):
        """Handoff metadata shows agent→agent routing."""
        # Builder → Research handoff
        receipt_chain = {
            "id": "test789",
            "preset": "research",
            "message": "Look up the API docs for stripe.com",
            "handoff": ["builder", "research"],  # Builder → Research
            "engine": "Hermes Agent",
            "url": "https://stripe.com/docs",
        }
        result_chain = bus.close_work_job(receipt_chain, "Found docs")
        # Should have builder→research handoff
        self.assertEqual(result_chain.get("handoff_from"), "builder")
        self.assertEqual(result_chain.get("handoff_to"), "research")
        self.assertIn("handoff_path", result_chain)

    def test_no_handoff_for_cos_or_ask(self):
        """Cos and Ask jobs don't get handoff metadata."""
        receipt_cos = {
            "id": "testcos",
            "preset": "cos",
            "message": "What's blocked?",
            "talk": True,
        }
        result_cos = bus.close_work_job(receipt_cos, "Reading INDEX")
        # Cos/talk jobs skip handoff entirely
        self.assertNotIn("handoff_path", result_cos)
        self.assertNotIn("handoff_from", result_cos)

    def test_handoff_not_set_when_from_equals_to(self):
        """No handoff card when from equals to (same preset repeated)."""
        receipt_same = {
            "id": "testsame",
            "preset": "builder",
            "message": "Keep coding",
            "handoff": ["builder", "builder"],  # Same preset repeated
            "engine": "OpenCode",
        }
        result_same = bus.close_work_job(receipt_same, "More changes")
        # Should not set handoff metadata when from == to
        self.assertNotIn("handoff_from", result_same)
        self.assertNotIn("handoff_to", result_same)

    def test_handoff_status_blocked(self):
        """Handoff status shows blocked when blocker present."""
        receipt_blocked = {
            "id": "testblock",
            "preset": "research",
            "message": "Fetch the page",
            "handoff": ["cos", "research"],
            "engine": "Hermes Agent",
            "blocker": "LOGIN_WALL",
        }
        result_blocked = bus.close_work_job(receipt_blocked, "Wall hit")
        self.assertEqual(result_blocked.get("handoff_status"), "blocked")

    def test_handoff_status_partial_on_diff(self):
        """Handoff status shows partial when diff_pending."""
        receipt_diff = {
            "id": "testdiff",
            "preset": "builder",
            "message": "Change footer",
            "handoff": ["cos", "builder"],
            "engine": "OpenCode",
            "diff_pending": True,
        }
        result_diff = bus.close_work_job(receipt_diff, "Local diff ready")
        self.assertEqual(result_diff.get("handoff_status"), "partial")


if __name__ == "__main__":
    unittest.main()
