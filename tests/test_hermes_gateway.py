"""Tests for Hermes gateway management (lazy, non-blocking)."""

import os
import tempfile
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
    @patch("openbot.hermes._run")
    def test_gateway_status_not_running_despite_stale_state(self, mock_run, mock_which):
        from openbot.hermes import gateway_status

        mock_which.return_value = "/usr/local/bin/hermes"
        mock_run.return_value = (
            0,
            "Gateway is not running\nrecorded state 'running' but the recorded process is gone",
        )
        result = gateway_status()
        self.assertTrue(result["ok"])
        self.assertFalse(result["running"])
    
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

    @patch.dict("os.environ", {"RAILWAY_ENVIRONMENT": "production"})
    @patch("openbot.hermes.time.sleep")
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.gateway_status")
    @patch("openbot.hermes._popen_detached")
    def test_gateway_start_uses_run_in_container(self, mock_detached, mock_status, mock_which, _sleep):
        from openbot.hermes import gateway_start

        mock_which.return_value = "/usr/local/bin/hermes"
        mock_status.side_effect = [
            {"running": False},
            {"running": True},
        ]
        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_detached.return_value = mock_proc
        result = gateway_start(wait=False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["started"])
        mock_detached.assert_called_once()
        self.assertEqual(mock_detached.call_args[0][0][1:], ["gateway", "run"])
    
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
    
    @patch("openbot.hermes.which")
    @patch("openbot.hermes.cron_list")
    @patch("openbot.hermes._run")
    def test_migrate_delivery_uses_edit_command(self, mock_run, mock_cron_list, mock_which):
        """Migration uses 'hermes cron edit' (not 'update') with --deliver flag."""
        from openbot.hermes import migrate_cron_delivery
        
        mock_which.return_value = "/usr/local/bin/hermes"
        mock_cron_list.return_value = {
            "ok": True,
            "jobs": [
                {"id": "7cb2a72c1cc8", "name": "test-job", "schedule": "0 9 * * *", "deliver": "origin"}
            ]
        }
        mock_run.return_value = (0, "Job updated successfully")
        
        result = migrate_cron_delivery(dry_run=False)
        
        # Verify _run was called with correct command structure
        self.assertEqual(mock_run.call_count, 1)
        call_args = mock_run.call_args[0][0]  # First positional arg is the command list
        
        # Assert the command uses 'edit' subcommand, not 'update'
        self.assertIn("cron", call_args)
        self.assertIn("edit", call_args)
        self.assertNotIn("update", call_args)
        
        # Assert job ID and --deliver local are present
        self.assertIn("7cb2a72c1cc8", call_args)
        self.assertIn("--deliver", call_args)
        self.assertIn("local", call_args)
        
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["migrated"]), 1)
        self.assertIn("7cb2a72c1cc8", result["migrated"])


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
    
    @patch("openbot.org.project_tools")
    @patch("openbot.hermes.cron_list")
    def test_list_routines_calls_cron_list_with_home_kwarg(self, mock_cron_list, mock_project_tools):
        """list_routines calls cron_list with home= keyword argument, not positional timeout."""
        from openbot.routines import list_routines
        
        # Setup: mock project_tools to return a hermes_home
        mock_project_tools.return_value = {"hermes_home": "/path/to/hermes"}
        mock_cron_list.return_value = {
            "ok": True,
            "jobs": [
                {"id": "test123", "name": "test-cron", "schedule": "0 9 * * *", "deliver": "local"},
            ]
        }
        
        result = list_routines(project_id="test-project", include_hermes=True)
        
        # Verify: cron_list was called with home= keyword (no timeout kwarg)
        mock_cron_list.assert_called_once_with(home="/path/to/hermes")
        self.assertEqual(result["hermes_count"], 1)


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


class TestGatewaySupervise(unittest.TestCase):
    def test_warm_engines_does_not_start_gateway(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parent.parent / "openbot" / "launch.py").read_text(encoding="utf-8")
        start = src.find("def warm_engines()")
        end = src.find("def warm_engines_background()")
        body = src[start:end]
        self.assertNotIn("gateway_start", body)
        self.assertNotIn("ensure_supervised_gateway", body)
        self.assertIn("start_opencode_web", body)
        self.assertIn("start_hermes_dashboard", body)

    def test_warm_engines_keep_running(self):
        src = (Path(__file__).resolve().parent.parent / "openbot" / "launch.py").read_text(encoding="utf-8")
        start = src.find("def warm_engines_background()")
        end = src.find("def supervise_gateways_enabled()")
        body = src[start:end]
        self.assertIn("while True", body)
        self.assertNotIn("gateway_start", body)

    @patch("openbot.launch._kill_port")
    @patch("openbot.launch._port_open", return_value=True)
    @patch("openbot.launch.detect")
    def test_dashboard_reuses_running_port(self, mock_detect, _port, mock_kill):
        import openbot.launch as launch

        mock_detect.return_value = {
            "hermes": {"present": True, "path": "hermes", "install": "", "install_cmd": ""}
        }
        launch._hermes_dash_home = None
        result = launch.start_hermes_dashboard("/tmp/saa-homes")
        mock_kill.assert_not_called()
        self.assertTrue(result.get("ok"))

    def test_existing_dir_skips_missing_laptop_path(self):
        from openbot.launch import existing_dir, resolve_ceo_folder, resolve_ceo_hermes_home

        self.assertEqual(existing_dir(r"Z:\not-a-real-openbot-path\hermes-homes\saa-homes"), "")
        self.assertEqual(existing_dir(""), "")
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "saa-homes"
            home.mkdir()
            self.assertEqual(existing_dir(str(home)), str(home.resolve()))
            with patch("openbot.org.project_tools", return_value={"hermes_home": r"C:\missing\saa-homes"}):
                with patch("openbot.org.HERMES_HOMES", Path(raw)):
                    found = resolve_ceo_hermes_home("saa-homes", r"C:\missing\saa-homes")
            self.assertEqual(found, str(home.resolve()))

    def test_openbot_folder_falls_back_to_this_repo(self):
        from openbot.launch import resolve_ceo_folder
        from openbot.store import CODE_ROOT

        with patch("openbot.org.project_tools", return_value={"folder": r"Z:\not-here\openbot"}):
            found = resolve_ceo_folder("openbot", r"Z:\not-here\openbot")
        self.assertEqual(Path(found).resolve(), CODE_ROOT.resolve())
        from openbot.launch import supervise_ceo_gateways_once, supervise_gateways_enabled

        with patch.dict("os.environ", {"OPENBOT_DATA_DIR": "", "OPENBOT_SUPERVISE_GATEWAYS": "0"}):
            self.assertFalse(supervise_gateways_enabled())
            self.assertEqual(supervise_ceo_gateways_once(), [])

    def test_supervise_homes_default_empty(self):
        from openbot.launch import supervised_project_ids

        with patch.dict("os.environ"):
            os.environ.pop("OPENBOT_SUPERVISE_HOMES", None)
            self.assertEqual(supervised_project_ids(), [])

    def test_supervise_on_with_data_dir(self):
        from openbot.launch import supervise_gateways_enabled

        with patch.dict("os.environ", {"OPENBOT_DATA_DIR": "/data", "OPENBOT_SUPERVISE_GATEWAYS": ""}):
            self.assertTrue(supervise_gateways_enabled())

    @patch("openbot.launch.ensure_supervised_gateway")
    def test_supervise_once_starts_saa_only(self, mock_ensure):
        from openbot.launch import supervise_ceo_gateways_once

        mock_ensure.return_value = {"ok": True, "project_id": "saa-homes"}
        with patch.dict("os.environ", {"OPENBOT_SUPERVISE_GATEWAYS": "1", "OPENBOT_SUPERVISE_HOMES": "saa-homes"}):
            rows = supervise_ceo_gateways_once()
        self.assertEqual(len(rows), 1)
        mock_ensure.assert_called_once_with("saa-homes")

    @patch("openbot.hermes.gateway_start")
    @patch("openbot.launch._ceo_hermes_home", return_value="/data/hermes-homes/saa-homes")
    def test_supervise_does_not_start_on_status_timeout(self, _home, mock_start):
        from openbot.launch import ensure_supervised_gateway

        with patch("openbot.hermes.gateway_status", return_value={
            "ok": False,
            "code": 124,
            "running": False,
            "error": "hermes timed out",
            "text": "hermes timed out",
        }):
            row = ensure_supervised_gateway("saa-homes")
        self.assertTrue(row.get("skipped"))
        self.assertFalse(row.get("started"))
        mock_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
