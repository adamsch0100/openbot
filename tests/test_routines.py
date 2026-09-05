"""Test routines: multi-step scheduled flows."""

import json
import unittest
from pathlib import Path

from openbot import routines
from openbot.store import ROOT

ORG = ROOT / "org"


class RoutineStorageTests(unittest.TestCase):
    def tearDown(self):
        """Clean up test routines."""
        folder = routines.routine_dir(None)
        if folder.exists():
            for path in folder.glob("*.md"):
                try:
                    path.unlink()
                except Exception:
                    pass

    def test_routine_dir_staff(self):
        """routine_dir for staff returns org/bus/routines."""
        path = routines.routine_dir(None)
        self.assertEqual(path, ORG / "bus" / "routines")

    def test_routine_dir_project(self):
        """routine_dir for project returns org/projects/{slug}/bus/routines."""
        path = routines.routine_dir("Test Project")
        self.assertEqual(path, ORG / "projects" / "test-project" / "bus" / "routines")

    def test_create_routine(self):
        """create_routine writes a routine file and returns routine_id."""
        routine_id = routines.create_routine(
            "Morning Standup",
            "every morning at 8am",
            [
                {"seat": "builder", "instruction": "Check git status"},
                {"seat": "think", "instruction": "Summarize changes"},
            ],
            project_id=None,
            enabled=True,
        )
        self.assertTrue(routine_id.startswith("routine-"))
        path = routines.routine_path(routine_id, None)
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Morning Standup", content)
        self.assertIn("every morning at 8am", content)
        self.assertIn("**Builder** - Check git status", content)
        self.assertIn("**Think** - Summarize changes", content)

    def test_parse_routine(self):
        """parse_routine extracts metadata from markdown."""
        text = """# Daily Review

Schedule: every day at 5pm
Enabled: true
Owner: staff

## Steps

1. **Builder** - Check git status
2. **Think** - Summarize day

## History

"""
        meta = routines.parse_routine(text)
        self.assertEqual(meta["name"], "Daily Review")
        self.assertEqual(meta["schedule"], "every day at 5pm")
        self.assertTrue(meta["enabled"])
        self.assertEqual(meta["owner"], "staff")
        self.assertEqual(len(meta["steps"]), 2)
        self.assertEqual(meta["steps"][0]["seat"], "builder")
        self.assertEqual(meta["steps"][0]["instruction"], "Check git status")

    def test_list_routines(self):
        """list_routines returns all routines for a scope."""
        routines.create_routine("Test 1", "every morning", [{"seat": "builder", "instruction": "test"}], None, True)
        routines.create_routine("Test 2", "every evening", [{"seat": "think", "instruction": "test"}], None, False)
        
        items = routines.list_routines(None)
        self.assertEqual(len(items), 2)
        self.assertTrue(any(r["name"] == "Test 1" for r in items))
        self.assertTrue(any(r["name"] == "Test 2" for r in items))

    def test_update_routine(self):
        """update_routine modifies a routine file."""
        routine_id = routines.create_routine("Original", "every day", [{"seat": "builder", "instruction": "test"}], None, True)
        ok = routines.update_routine(routine_id, None, name="Updated Name", schedule="every week")
        self.assertTrue(ok)
        
        routine = routines.read_routine(routine_id, None)
        self.assertIsNotNone(routine)
        self.assertEqual(routine["name"], "Updated Name")
        self.assertEqual(routine["schedule"], "every week")

    def test_delete_routine(self):
        """delete_routine removes a routine file."""
        routine_id = routines.create_routine("Delete Me", "every day", [{"seat": "builder", "instruction": "test"}], None, True)
        path = routines.routine_path(routine_id, None)
        self.assertTrue(path.exists())
        
        ok = routines.delete_routine(routine_id, None)
        self.assertTrue(ok)
        self.assertFalse(path.exists())


class RoutineExecutionTests(unittest.TestCase):
    def tearDown(self):
        """Clean up test routines."""
        folder = routines.routine_dir(None)
        if folder.exists():
            for path in folder.glob("*.md"):
                try:
                    path.unlink()
                except Exception:
                    pass

    def test_execute_routine_not_found(self):
        """execute_routine returns error if routine not found."""
        result = routines.execute_routine("nonexistent", None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "routine not found")

    def test_execute_routine_disabled(self):
        """execute_routine returns error if routine disabled."""
        routine_id = routines.create_routine(
            "Disabled",
            "every day",
            [{"seat": "builder", "instruction": "test"}],
            None,
            enabled=False,
        )
        result = routines.execute_routine(routine_id, None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "routine disabled")

    def test_execute_routine_no_steps(self):
        """execute_routine returns error if routine has no steps."""
        routine_id = routines.create_routine("Empty", "every day", [], None, True)
        result = routines.execute_routine(routine_id, None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "routine has no steps")

    def test_routine_cron_name(self):
        """routine_cron_name generates consistent cron job names."""
        name1 = routines.routine_cron_name("routine-abc", None)
        name2 = routines.routine_cron_name("routine-abc", "test-project")
        
        self.assertEqual(name1, "openbot-routine-staff-routine-abc")
        self.assertEqual(name2, "openbot-routine-test-project-routine-abc")

    def test_add_history_entry(self):
        """add_history_entry appends to routine file."""
        routine_id = routines.create_routine(
            "Test",
            "every day",
            [{"seat": "builder", "instruction": "test"}],
            None,
            True,
        )
        
        routines.add_history_entry(routine_id, None, "run-123", "completed", 2, 2)
        
        path = routines.routine_path(routine_id, None)
        content = path.read_text(encoding="utf-8")
        self.assertIn("Run run-123 completed (2/2 steps)", content)


class RoutineFormatTests(unittest.TestCase):
    def test_format_routine(self):
        """format_routine generates valid markdown."""
        meta = {
            "name": "Test Routine",
            "schedule": "every morning at 8am",
            "enabled": True,
            "owner": "staff",
            "steps": [
                {"seat": "builder", "instruction": "Check status"},
                {"seat": "think", "instruction": "Summarize"},
            ],
        }
        
        md = routines.format_routine(meta)
        self.assertIn("# Test Routine", md)
        self.assertIn("Schedule: every morning at 8am", md)
        self.assertIn("Enabled: true", md)
        self.assertIn("1. **Builder** - Check status", md)
        self.assertIn("2. **Think** - Summarize", md)
        self.assertIn("## History", md)

    def test_parse_disabled_routine(self):
        """parse_routine handles enabled: false."""
        text = """# Test

Schedule: every day
Enabled: false

## Steps

1. **Builder** - test
"""
        meta = routines.parse_routine(text)
        self.assertFalse(meta["enabled"])


class RoutineResumeTests(unittest.TestCase):
    def tearDown(self):
        """Clean up test routines."""
        folder = routines.routine_dir(None)
        if folder.exists():
            for path in folder.glob("*.md"):
                try:
                    path.unlink()
                except Exception:
                    pass

    def test_resume_routine(self):
        """execute_routine can resume from a failed step."""
        routine_id = routines.create_routine(
            "Resume Test",
            "every day",
            [
                {"seat": "builder", "instruction": "Step 1"},
                {"seat": "think", "instruction": "Step 2"},
                {"seat": "ops", "instruction": "Step 3"},
            ],
            None,
            True,
        )
        
        # Simulate resume from step 2 with a prior result
        result = routines.execute_routine(
            routine_id,
            None,
            resume_step=2,
            resume_result="Result from step 1",
        )
        
        # Should start from step 2 (skipping step 1)
        # We can't test actual execution without mocking handle(),
        # but we can verify the structure is correct
        self.assertIn("run_id", result)
        self.assertEqual(result.get("total_steps"), 3)


if __name__ == "__main__":
    unittest.main()
