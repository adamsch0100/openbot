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
        self.assertEqual(result["enabled_count"], 0)
        self.assertEqual(result["total_count"], 0)
        self.assertIn("missing", result["error"].lower())
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_gateway_status_running(self, mock_run, mock_which):
        """Gateway status parses cron list output."""
        from openbot.hermes import gateway_status
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_run.return_value = (0, """
ID    Name                  Schedule      Status
abc   saa-check-ranking     0 9 * * *     enabled
def   saa-update-listings   0 */6 * * *   enabled
xyz   test-job              every 1h      disabled
""")
        
        result = gateway_status()
        
        self.assertIn("running", result)
        self.assertEqual(result["enabled_count"], 2)
        self.assertEqual(result["total_count"], 3)
        self.assertIsNone(result["error"])
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._subprocess.Popen")
    def test_gateway_start_no_wait(self, mock_popen, mock_which):
        """Gateway start launches process without blocking."""
        from openbot.hermes import gateway_start
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_popen.return_value = mock_proc
        
        result = gateway_start(wait=False)
        
        self.assertTrue(result["ok"])
        self.assertTrue(result["running"])
        self.assertTrue(result["started"])
        self.assertIsNone(result["error"])
        mock_popen.assert_called_once()
    
    @patch("openbot.hermes.which")
    def test_gateway_start_missing_binary(self, mock_which):
        """Gateway start fails gracefully when Hermes missing."""
        from openbot.hermes import gateway_start
        
        mock_which.return_value = None
        
        result = gateway_start()
        
        self.assertFalse(result["ok"])
        self.assertFalse(result["running"])
        self.assertFalse(result["started"])
        self.assertIn("missing", result["error"].lower())
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._GATEWAY_PROCS", {"/home/user/.hermes": MagicMock(poll=lambda: None)})
    def test_gateway_stop(self, mock_which):
        """Gateway stop terminates running process."""
        from openbot.hermes import gateway_stop, _GATEWAY_PROCS
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        
        key = "/home/user/.hermes"
        _GATEWAY_PROCS[key] = mock_proc
        
        result = gateway_stop(Path("/home/user/.hermes"))
        
        self.assertTrue(result["ok"])
        self.assertTrue(result["stopped"])
        mock_proc.terminate.assert_called_once()


class TestCronList(unittest.TestCase):
    """Test cron_list parsing."""
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes._run")
    def test_cron_list_success(self, mock_run, mock_which):
        """cron_list parses Hermes cron list output."""
        from openbot.hermes import cron_list
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_run.return_value = (0, """
ID     Name                    Schedule      Status
abc    saa-check-ranking       0 9 * * *     enabled
def    saa-update-listings     0 */6 * * *   enabled
xyz    test-disabled           every 1h      disabled
""")
        
        result = cron_list()
        
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["crons"]), 3)
        self.assertEqual(result["crons"][0]["id"], "abc")
        self.assertEqual(result["crons"][0]["name"], "saa-check-ranking")
        self.assertTrue(result["crons"][0]["enabled"])
        self.assertFalse(result["crons"][2]["enabled"])
    
    @patch("openbot.hermes.which")
    def test_cron_list_no_binary(self, mock_which):
        """cron_list fails gracefully when Hermes missing."""
        from openbot.hermes import cron_list
        
        mock_which.return_value = None
        
        result = cron_list()
        
        self.assertFalse(result["ok"])
        self.assertEqual(result["crons"], [])
        self.assertIn("missing", result["error"].lower())


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
            "crons": [
                {"id": "abc", "name": "test1", "enabled": True, "raw": "abc test1 0 9 * * * enabled deliver origin"},
                {"id": "def", "name": "test2", "enabled": True, "raw": "def test2 every 1h enabled deliver local"},
                {"id": "xyz", "name": "test3", "enabled": False, "raw": "xyz test3 every 2h disabled deliver origin"},
            ]
        }
        
        result = migrate_cron_delivery(dry_run=True)
        
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["migrated"]), 2)  # abc and xyz need migration
        self.assertIn("abc", result["migrated"])
        self.assertIn("xyz", result["migrated"])
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
            "crons": [
                {"id": "abc", "name": "test1", "enabled": True, "raw": "abc test1 0 9 * * * enabled deliver origin"},
                {"id": "def", "name": "test2", "enabled": True, "raw": "def test2 every 1h enabled deliver origin"},
            ]
        }
        mock_run.return_value = (0, "Updated cron abc")
        
        result = migrate_cron_delivery(dry_run=False)
        
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("dry_run", False))
        self.assertEqual(len(result["migrated"]), 2)
        self.assertEqual(len(result["failed"]), 0)
        self.assertEqual(mock_run.call_count, 2)


class TestRoutinesMerge(unittest.TestCase):
    """Test /api/routines merges OpenBot + Hermes crons."""
    
    @patch("openbot.routines.cron_list")
    def test_list_routines_includes_hermes(self, mock_cron_list):
        """list_routines merges OpenBot routines with Hermes crons."""
        from openbot.routines import list_routines
        
        mock_cron_list.return_value = {
            "ok": True,
            "crons": [
                {"id": "abc", "name": "saa-check", "schedule": "0 9 * * *", "enabled": True, "raw": "..."},
                {"id": "def", "name": "saa-update", "schedule": "every 6h", "enabled": True, "raw": "..."},
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
    @patch("openbot.hermes._subprocess.Popen")
    def test_gateway_start_no_wait_immediate(self, mock_popen, mock_which):
        """Gateway start without wait returns immediately."""
        from openbot.hermes import gateway_start
        import time
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        start = time.time()
        result = gateway_start(wait=False)
        elapsed = time.time() - start
        
        # Should return almost immediately (< 1 second)
        self.assertLess(elapsed, 1.0)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
