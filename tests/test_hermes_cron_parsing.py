"""Test Hermes cron list parsing (multi-line block format)."""

import unittest
from openbot.hermes import _parse_cron_table, is_valid_job_id


class TestHermesCronParsing(unittest.TestCase):
    def test_parse_empty(self):
        """Empty output returns empty list."""
        self.assertEqual(_parse_cron_table(""), [])
        self.assertEqual(_parse_cron_table("No cron jobs"), [])
        self.assertEqual(_parse_cron_table("no cron execution"), [])
    
    def test_parse_real_multiline_format(self):
        """Parse real Hermes multi-line block format."""
        output = """
  7cb2a72c1cc8 [active]
    Name:      form-pipeline-health
    Schedule:  0 14 * * *
    Repeat:    ∞
    Next run:  2026-09-06T14:00:00+00:00
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
    Last run:  2026-09-05T14:00:10.773343+00:00  ok
    Dispatch:  on time (...)
    Execution: completed  b47c6c018b4348239ae05959c50d5e22

  240631fc9f22 [active]
    Name:      daily-ranking-strike
    Schedule:  0 13 * * 1-5
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 2)
        
        # First job
        self.assertEqual(jobs[0]["id"], "7cb2a72c1cc8")
        self.assertEqual(jobs[0]["name"], "form-pipeline-health")
        self.assertEqual(jobs[0]["schedule"], "0 14 * * *")
        self.assertEqual(jobs[0]["deliver"], "origin")
        
        # Second job
        self.assertEqual(jobs[1]["id"], "240631fc9f22")
        self.assertEqual(jobs[1]["name"], "daily-ranking-strike")
        self.assertEqual(jobs[1]["schedule"], "0 13 * * 1-5")
    
    def test_parse_paused_job(self):
        """Parse paused jobs correctly."""
        output = """
  abc123def456 [paused]
    Name:      test-job
    Schedule:  every 1h
    Deliver:   local
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "abc123def456")
        self.assertEqual(jobs[0]["name"], "test-job")
        self.assertEqual(jobs[0]["schedule"], "every 1h")
    
    def test_reject_label_words(self):
        """Reject lines with label words, not hex job IDs."""
        output = """
  Name: form-pipeline [active]
    Name:      fake-job
    Schedule:  0 14 * * *
  
  Next [active]
    Name:      another-fake
    Schedule:  every 1h
    
  Execution: something [active]
    Name:      also-fake
    Schedule:  0 9 * * *
"""
        jobs = _parse_cron_table(output)
        # Should reject all because "Name:", "Next", "Execution:" are not valid hex IDs
        self.assertEqual(len(jobs), 0)
    
    def test_real_saa_homes_fixture(self):
        """Parse real SAA Homes cron jobs (multi-line format)."""
        output = """
  7cb2a72c1cc8 [active]
    Name:      form-pipeline-health
    Schedule:  0 14 * * *
    Repeat:    ∞
    Next run:  2026-09-06T14:00:00+00:00
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
    Last run:  2026-09-05T14:00:10.773343+00:00  ok
    Dispatch:  on time (...)
    Execution: completed  b47c6c018b4348239ae05959c50d5e22

  240631fc9f22 [active]
    Name:      daily-ranking-strike
    Schedule:  0 13 * * 1-5
    Deliver:   origin
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 2)
        
        # Verify real job names are extracted
        names = [j["name"] for j in jobs]
        self.assertIn("form-pipeline-health", names)
        self.assertIn("daily-ranking-strike", names)
        
        # Verify schedules are clean
        schedules = [j["schedule"] for j in jobs]
        self.assertIn("0 14 * * *", schedules)
        self.assertIn("0 13 * * 1-5", schedules)
        
        # IDs should be hex-like
        self.assertEqual(jobs[0]["id"], "7cb2a72c1cc8")
        self.assertEqual(jobs[1]["id"], "240631fc9f22")


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
    """Test guard against junk job IDs (hex-like, 12+ chars)."""
    
    def test_is_valid_job_id(self):
        """Helper to validate job IDs before using them."""
        # Good IDs (hex-like, 12+ chars)
        self.assertTrue(is_valid_job_id("7cb2a72c1cc8"))
        self.assertTrue(is_valid_job_id("240631fc9f22"))
        self.assertTrue(is_valid_job_id("abc123def456"))
        self.assertTrue(is_valid_job_id("b47c6c018b4348239ae05959c50d5e22"))
        
        # Bad IDs (label words, too short, or not hex-like)
        self.assertFalse(is_valid_job_id("Name:"))
        self.assertFalse(is_valid_job_id("Schedule:"))
        self.assertFalse(is_valid_job_id("Next"))
        self.assertFalse(is_valid_job_id("Execution:"))
        self.assertFalse(is_valid_job_id("Skills:"))
        self.assertFalse(is_valid_job_id("Deliver:"))
        self.assertFalse(is_valid_job_id("Last"))
        self.assertFalse(is_valid_job_id("Dispatch:"))
        self.assertFalse(is_valid_job_id("│"))
        self.assertFalse(is_valid_job_id("--"))
        self.assertFalse(is_valid_job_id(""))
        self.assertFalse(is_valid_job_id("abc"))  # Too short
        self.assertFalse(is_valid_job_id("form-pipeline-health"))  # Name, not ID


if __name__ == "__main__":
    unittest.main()
