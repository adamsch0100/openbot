"""Test Hermes cron list parsing (robust against table chrome)."""

import unittest
from openbot.hermes import _parse_cron_table, is_valid_job_id


class TestHermesCronParsing(unittest.TestCase):
    def test_parse_empty(self):
        """Empty output returns empty list."""
        self.assertEqual(_parse_cron_table(""), [])
        self.assertEqual(_parse_cron_table("No cron jobs"), [])
        self.assertEqual(_parse_cron_table("no cron execution"), [])
    
    def test_parse_clean_table(self):
        """Parse a clean ASCII table with job data."""
        table = """
┌──────────┬─────────────────┬──────────┬─────────┐
│ ID       │ Name            │ Schedule │ Enabled │
├──────────┼─────────────────┼──────────┼─────────┤
│ job-abc  │ daily-ranking   │ 0 9 * * *│ true    │
│ job-def  │ weekly-report   │ 0 0 * * 0│ true    │
└──────────┴─────────────────┴──────────┴─────────┘
"""
        jobs = _parse_cron_table(table)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["id"], "job-abc")
        self.assertEqual(jobs[0]["name"], "daily-ranking")
        self.assertEqual(jobs[0]["schedule"], "0 9 * * *")
        self.assertEqual(jobs[1]["id"], "job-def")
        self.assertEqual(jobs[1]["name"], "weekly-report")
    
    def test_parse_with_table_chrome(self):
        """Skip table borders and headers."""
        table = """
│ Schedule:  Last Dispatch:            │
│ job-abc    daily-ranking    every 1h │
│ job-def    weekly-summary   0 9 * * *│
"""
        jobs = _parse_cron_table(table)
        # Should skip "Schedule:" line and parse the two real jobs
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["id"], "job-abc")
        self.assertEqual(jobs[1]["id"], "job-def")
    
    def test_reject_garbage_ids(self):
        """Reject table chrome mistaken for job IDs."""
        table = """
│ Last    daily-ranking    0 9 * * *
Schedule: weekly-report   every 1h
Dispatch: summary         0 0 * * 0
job-real  real-job        every 2h
"""
        jobs = _parse_cron_table(table)
        # Only "job-real" is a valid job ID
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "job-real")
        self.assertEqual(jobs[0]["name"], "real-job")
    
    def test_parse_simple_space_separated(self):
        """Parse simple space-separated format (no box drawing)."""
        table = """
job-abc daily-ranking every 1h
job-def weekly-report 0 9 * * *
job-ghi monthly-audit every 30d
"""
        jobs = _parse_cron_table(table)
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["schedule"], "every 1h")
        self.assertEqual(jobs[1]["schedule"], "0 9 * * *")
        self.assertEqual(jobs[2]["schedule"], "every 30d")
    
    def test_skip_header_lines(self):
        """Skip common header patterns."""
        table = """
ID        Name            Schedule      Enabled
--------- --------------- ------------- -------
job-abc   daily-ranking   every 1h      true
"""
        jobs = _parse_cron_table(table)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "job-abc")
    
    def test_real_saa_homes_example(self):
        """Parse real SAA Homes cron jobs (not garbage)."""
        # This is what SHOULD be returned, not the junk IDs
        table = """
job-12345678  daily-ranking-strike   0 9 * * *    enabled  local
job-23456789  weekly-report          0 0 * * 0    enabled  local
job-34567890  hourly-sync            every 1h     enabled  telegram
"""
        jobs = _parse_cron_table(table)
        self.assertEqual(len(jobs), 3)
        # Verify real job names are extracted
        names = [j["name"] for j in jobs]
        self.assertIn("daily-ranking-strike", names)
        self.assertIn("weekly-report", names)
        self.assertIn("hourly-sync", names)
        # Verify schedules are clean (no "enabled" or "local" suffix)
        self.assertEqual(jobs[0]["schedule"], "0 9 * * *")
        self.assertEqual(jobs[1]["schedule"], "0 0 * * 0")
        self.assertEqual(jobs[2]["schedule"], "every 1h")


class TestCronListJSONFallback(unittest.TestCase):
    """Test that cron_list prefers JSON and falls back gracefully."""
    
    def test_cron_list_structure(self):
        """cron_list returns consistent structure."""
        from openbot.hermes import cron_list
        
        # When hermes binary is missing
        result = cron_list()
        self.assertIn("ok", result)
        # When binary is missing, may return "error" instead of "code"
        self.assertTrue("code" in result or "error" in result)
        # text may be empty string when binary missing
        self.assertTrue("text" in result or "error" in result)
        self.assertIn("jobs", result)
        self.assertIsInstance(result["jobs"], list)


class TestJobIdValidation(unittest.TestCase):
    """Test guard against junk job IDs."""
    
    def test_is_valid_job_id(self):
        """Helper to validate job IDs before using them."""
        # Good IDs
        self.assertTrue(is_valid_job_id("job-abc123"))
        self.assertTrue(is_valid_job_id("routine-abcd1234"))
        self.assertTrue(is_valid_job_id("12345678"))
        
        # Bad IDs (table chrome)
        self.assertFalse(is_valid_job_id("│"))
        self.assertFalse(is_valid_job_id("Schedule:"))
        self.assertFalse(is_valid_job_id("Last"))
        self.assertFalse(is_valid_job_id("Dispatch:"))
        self.assertFalse(is_valid_job_id("--"))
        self.assertFalse(is_valid_job_id(""))
        self.assertFalse(is_valid_job_id("a"))  # Too short


if __name__ == "__main__":
    unittest.main()
