"""Tests for Hermes gateway management (lazy, non-blocking)."""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestGatewayManagement(unittest.TestCase):
    """Test gateway status, start, stop operations."""
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_gateway_status_no_binary(self, mock_run, mock_which):
        """Gateway status returns error when Hermes binary missing."""
        from openbot.hermes import gateway_status
        
        mock_which.return_value = None
        
        result = gateway_status()
        
        self.assertFalse(result["running"])
        self.assertIn("missing", result["error"].lower())
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_gateway_status_running(self, mock_run, mock_which):
        """Gateway status checks if gateway is running."""
        from openbot.hermes import gateway_status
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_run.return_value = (0, "Gateway is running")
        
        result = gateway_status()
        
        self.assertTrue(result["running"])
        self.assertTrue(result["ok"])
        self.assertIsNone(result["error"])
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.gateway_status")
    @patch("openbot.hermes._popen")
    def test_gateway_start_no_wait(self, mock_popen, mock_status, mock_which):
        """Gateway start launches process without blocking."""
        from openbot.hermes import gateway_start
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_status.side_effect = [
            {"running": False},  # First check (not running)
            {"running": True},   # After start (running)
        ]
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc
        
        result = gateway_start(wait=False)
        
        self.assertTrue(result["ok"])
        self.assertTrue(result["started"])
        mock_popen.assert_called_once()
    
    @patch("openbot.hermes.which")
    def test_gateway_start_missing_binary(self, mock_which):
        """Gateway start fails gracefully when Hermes missing."""
        from openbot.hermes import gateway_start
        
        mock_which.return_value = None
        
        result = gateway_start()
        
        self.assertFalse(result["ok"])
        self.assertFalse(result["running"])
        self.assertIn("missing", result["error"].lower())
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_gateway_stop(self, mock_run, mock_which):
        """Gateway stop calls hermes gateway stop."""
        from openbot.hermes import gateway_stop
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_run.return_value = (0, "Gateway stopped")
        
        result = gateway_stop()
        
        self.assertTrue(result["ok"])
        mock_run.assert_called_once()


class TestCronList(unittest.TestCase):
    """Test cron_list parsing."""
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_cron_list_success(self, mock_run, mock_which):
        """cron_list parses Hermes cron list output."""
        from openbot.hermes import cron_list
        
        mock_which.return_value = "/usr/local/bin/hermes"
        # Multi-line format
        mock_run.side_effect = [
            (1, ""),  # JSON fails
            (0, """
  7cb2a72c1cc8 [active]
    Name:      saa-check-ranking
    Schedule:  0 9 * * *
    Deliver:   local

  abc123def456 [active]
    Name:      saa-update-listings
    Schedule:  0 */6 * * *
    Deliver:   local
"""),
        ]
        
        result = cron_list()
        
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["jobs"]), 2)
        self.assertEqual(result["jobs"][0]["id"], "7cb2a72c1cc8")
        self.assertEqual(result["jobs"][0]["name"], "saa-check-ranking")
    
    @patch("openbot.hermes.which")
    def test_cron_list_no_binary(self, mock_which):
        """cron_list fails gracefully when Hermes missing."""
        from openbot.hermes import cron_list
        
        mock_which.return_value = None
        
        result = cron_list()
        
        self.assertFalse(result["ok"])
        self.assertEqual(result["jobs"], [])


class TestMigrateDelivery(unittest.TestCase):
    """Test migrate_cron_delivery."""
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.cron_list")
    @patch("openbot.hermes._run")
    def test_migrate_delivery_dry_run(self, mock_run, mock_cron_list, mock_which):
        """Dry run migration reports what would be migrated."""
        from openbot.hermes import migrate_cron_delivery
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_cron_list.return_value = {
            "ok": True,
            "jobs": [
                {"id": "7cb2a72c1cc8", "name": "test1", "schedule": "0 9 * * *", "deliver": "origin"},
                {"id": "abc123def456", "name": "test2", "schedule": "every 1h", "deliver": "local"},
                {"id": "fedcba987654", "name": "test3", "schedule": "every 2h", "deliver": "origin"},
            ]
        }
        
        result = migrate_cron_delivery(dry_run=True)
        
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["migrated"]), 2)  # Two jobs with origin delivery
        self.assertIn("7cb2a72c1cc8", result["migrated"])
        self.assertIn("fedcba987654", result["migrated"])
        self.assertEqual(result["total"], 3)
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.cron_list")
    @patch("openbot.hermes._run")
    def test_migrate_delivery_success(self, mock_run, mock_cron_list, mock_which):
        """Migration updates crons to deliver=local."""
        from openbot.hermes import migrate_cron_delivery
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_cron_list.return_value = {
            "ok": True,
            "jobs": [
                {"id": "7cb2a72c1cc8", "name": "test1", "schedule": "0 9 * * *", "deliver": "origin"},
                {"id": "abc123def456", "name": "test2", "schedule": "every 1h", "deliver": "origin"},
            ]
        }
        mock_run.return_value = (0, "Updated cron")
        
        result = migrate_cron_delivery(dry_run=False)
        
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("dry_run", False))
        self.assertEqual(len(result["migrated"]), 2)
        self.assertEqual(len(result["failed"]), 0)
        self.assertEqual(mock_run.call_count, 2)


class TestRoutinesMerge(unittest.TestCase):
    """Test /api/routines merges OpenBot + Hermes crons."""
    
    @patch("openbot.hermes.cron_list")
    def test_list_routines_includes_hermes(self, mock_cron_list):
        """list_routines merges OpenBot routines with Hermes crons."""
        from openbot.routines import list_routines
        
        mock_cron_list.return_value = {
            "ok": True,
            "jobs": [
                {"id": "7cb2a72c1cc8", "name": "saa-check", "schedule": "0 9 * * *", "deliver": "local"},
                {"id": "abc123def456", "name": "saa-update", "schedule": "every 6h", "deliver": "local"},
            ]
        }
        
        result = list_routines(project_id="saa-homes", include_hermes=True)
        
        self.assertIn("routines", result)
        self.assertIn("hermes_crons", result)
        self.assertEqual(result["hermes_count"], 2)
        self.assertEqual(result["total"], len(result["routines"]) + 2)
        self.assertEqual(result["hermes_crons"][0]["source"], "hermes")
        self.assertEqual(result["hermes_crons"][0]["name"], "saa-check")


class TestNonBlocking(unittest.TestCase):
    """Test that gateway operations don't block HTTP server."""
    
    def test_gateway_status_timeout(self):
        """Gateway status respects timeout and fails fast."""
        from openbot.hermes import gateway_status
        import time
        
        start = time.time()
        result = gateway_status(timeout=2)
        elapsed = time.time() - start
        
        # Should complete within timeout + small overhead
        self.assertLess(elapsed, 4.0)
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.gateway_status")
    @patch("openbot.hermes._popen")
    def test_gateway_start_no_wait_immediate(self, mock_popen, mock_status, mock_which):
        """Gateway start without wait returns immediately."""
        from openbot.hermes import gateway_start
        import time
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_status.side_effect = [
            {"running": False},
            {"running": True},
        ]
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc
        
        start = time.time()
        result = gateway_start(wait=False)
        elapsed = time.time() - start
        
        # Should return almost immediately (< 2 seconds for 0.5s sleep + overhead)
        self.assertLess(elapsed, 2.0)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
