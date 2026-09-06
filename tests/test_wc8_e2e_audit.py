"""Tests for WC-8: E2E World-Class Audit.

Comprehensive tests for E2E harness and helpers.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from openbot.e2e import e2e_status, latest_e2e_run, record_e2e_run
from openbot.store import ROOT


class TestE2EHelpers(unittest.TestCase):
    """Test E2E helper functions."""

    def setUp(self):
        """Set up test environment."""
        self.test_run_id = f"test_{int(time.time())}"
        self.e2e_dir = ROOT / "tests" / "e2e" / "runs"
        self.e2e_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test files."""
        if self.e2e_dir.exists():
            for file in self.e2e_dir.glob(f"{self.test_run_id}*.json"):
                file.unlink()

    def test_record_e2e_run(self):
        """Test recording E2E run results."""
        results = [
            {"test": "health_check", "passed": True},
            {"test": "builder_flow", "passed": True},
            {"test": "research_flow", "passed": False},
        ]
        metadata = {"url": "https://test.example.com", "timestamp": time.time()}
        
        run_file = record_e2e_run(self.test_run_id, results, metadata)
        
        self.assertTrue(run_file.exists())
        
        with open(run_file) as f:
            data = json.load(f)
        
        self.assertEqual(data["run_id"], self.test_run_id)
        self.assertEqual(len(data["results"]), 3)
        self.assertEqual(data["summary"]["passed"], 2)
        self.assertEqual(data["summary"]["failed"], 1)
        self.assertEqual(data["metadata"], metadata)

    def test_latest_e2e_run(self):
        """Test fetching latest E2E run."""
        # Create multiple runs
        for i in range(3):
            run_id = f"{self.test_run_id}_{i}"
            results = [{"test": f"test_{i}", "passed": True}]
            record_e2e_run(run_id, results)
            time.sleep(0.1)  # Ensure different mtimes
        
        latest = latest_e2e_run()
        
        self.assertIsNotNone(latest)
        self.assertIn(self.test_run_id, latest["run_id"])

    def test_latest_e2e_run_no_runs(self):
        """Test latest_e2e_run when no runs exist."""
        # Clear all runs
        for file in self.e2e_dir.glob("*.json"):
            file.unlink()
        
        latest = latest_e2e_run()
        self.assertIsNone(latest)

    def test_e2e_status_passed(self):
        """Test E2E status when all tests passed."""
        results = [
            {"test": "health_check", "passed": True},
            {"test": "builder_flow", "passed": True},
        ]
        record_e2e_run(self.test_run_id, results)
        
        status = e2e_status()
        
        self.assertEqual(status["status"], "passed")
        self.assertEqual(status["run_id"], self.test_run_id)
        self.assertEqual(status["summary"]["passed"], 2)
        self.assertEqual(status["summary"]["failed"], 0)

    def test_e2e_status_failed(self):
        """Test E2E status when some tests failed."""
        results = [
            {"test": "health_check", "passed": True},
            {"test": "builder_flow", "passed": False},
        ]
        record_e2e_run(self.test_run_id, results)
        
        status = e2e_status()
        
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["summary"]["failed"], 1)

    def test_e2e_status_never_run(self):
        """Test E2E status when never run."""
        # Clear all runs
        for file in self.e2e_dir.glob("*.json"):
            file.unlink()
        
        status = e2e_status()
        
        self.assertEqual(status["status"], "never_run")


class TestE2ESmokeTestClient(unittest.TestCase):
    """Test E2E smoke test client."""

    @patch("tests.e2e.smoke_test.HTTPSConnection")
    def test_client_request(self, mock_https):
        """Test HTTP client request."""
        from tests.e2e.smoke_test import OpenBotE2EClient
        
        # Mock response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.getheaders.return_value = []
        
        mock_conn = Mock()
        mock_conn.request = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https.return_value = mock_conn
        
        client = OpenBotE2EClient("https://test.example.com")
        result = client._request("GET", "/api/status")
        
        self.assertEqual(result, {"status": "ok"})
        mock_conn.request.assert_called_once()

    @patch("tests.e2e.smoke_test.HTTPSConnection")
    def test_client_unlock(self, mock_https):
        """Test client unlock with PIN."""
        from tests.e2e.smoke_test import OpenBotE2EClient
        
        # Mock response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"unlocked": true}'
        mock_response.getheaders.return_value = []
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https.return_value = mock_conn
        
        client = OpenBotE2EClient("https://test.example.com", pin="1234")
        result = client.unlock()
        
        self.assertTrue(result)

    @patch("tests.e2e.smoke_test.HTTPSConnection")
    def test_client_send_message(self, mock_https):
        """Test sending message."""
        from tests.e2e.smoke_test import OpenBotE2EClient
        
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"job_id": "abc123"}'
        mock_response.getheaders.return_value = []
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https.return_value = mock_conn
        
        client = OpenBotE2EClient("https://test.example.com")
        result = client.send_message("test message", seat="builder")
        
        self.assertEqual(result["job_id"], "abc123")


class TestE2ETestRunner(unittest.TestCase):
    """Test E2E test runner."""

    def setUp(self):
        """Set up test environment."""
        self.evidence_dir = ROOT / "tests" / "e2e" / "test_evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test evidence."""
        if self.evidence_dir.exists():
            for file in self.evidence_dir.glob("*"):
                file.unlink()

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_health_check(self, mock_client_class):
        """Test health check test."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        mock_client = Mock()
        mock_client.get_status.return_value = {"status": "ok", "version": "1.0"}
        mock_client_class.return_value = mock_client
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.client = mock_client
        
        result = runner.test_health_check()
        
        self.assertTrue(result)
        self.assertEqual(len(runner.results), 1)
        self.assertTrue(runner.results[0]["passed"])

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_builder_flow(self, mock_client_class):
        """Test Builder flow test."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        mock_client = Mock()
        mock_client.send_message.return_value = {"job_id": "job123"}
        mock_client.get_job.return_value = {
            "status": "completed",
            "has_diff": True,
        }
        mock_client.accept_diff.return_value = {"accepted": True}
        mock_client_class.return_value = mock_client
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.client = mock_client
        
        result = runner.test_builder_flow()
        
        self.assertTrue(result)
        self.assertEqual(len(runner.results), 1)
        self.assertTrue(runner.results[0]["passed"])

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_research_flow(self, mock_client_class):
        """Test Research flow test."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        mock_client = Mock()
        mock_client.send_message.return_value = {"job_id": "job456"}
        mock_client.get_job.return_value = {
            "status": "completed",
            "result": "This is a summary of the README file with lots of content.",
        }
        mock_client_class.return_value = mock_client
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.client = mock_client
        
        result = runner.test_research_flow()
        
        self.assertTrue(result)

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_ops_flow(self, mock_client_class):
        """Test Ops flow test."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        mock_client = Mock()
        mock_client.send_message.return_value = {"job_id": "job789"}
        mock_client.get_job.return_value = {"status": "completed"}
        mock_client_class.return_value = mock_client
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.client = mock_client
        
        result = runner.test_ops_flow()
        
        self.assertTrue(result)

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_save_evidence(self, mock_client_class):
        """Test evidence saving."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.results = [
            {"test": "test1", "passed": True},
            {"test": "test2", "passed": False},
        ]
        
        evidence = runner.save_evidence()
        
        self.assertEqual(evidence["summary"]["total"], 2)
        self.assertEqual(evidence["summary"]["passed"], 1)
        self.assertEqual(evidence["summary"]["failed"], 1)
        
        # Check file was created
        evidence_file = self.evidence_dir / f"run_{runner.run_id}.json"
        self.assertTrue(evidence_file.exists())

    @patch("tests.e2e.smoke_test.OpenBotE2EClient")
    def test_runner_wait_for_job_timeout(self, mock_client_class):
        """Test job wait timeout."""
        from tests.e2e.smoke_test import E2ETestRunner
        
        mock_client = Mock()
        mock_client.get_job.return_value = {"status": "running"}
        mock_client_class.return_value = mock_client
        
        runner = E2ETestRunner("https://test.example.com", evidence_dir=self.evidence_dir)
        runner.client = mock_client
        
        result = runner.wait_for_job("job123", timeout=5)
        
        self.assertIsNone(result)


class TestE2ERegression(unittest.TestCase):
    """Test E2E regression routine support."""

    def test_regression_routine_can_be_created(self):
        """Test that E2E regression routine can be defined."""
        from openbot.routine_templates import get_routine_templates
        
        # Check if there's an E2E regression template
        templates = get_routine_templates()
        e2e_template = None
        for template in templates:
            if "e2e" in template.get("id", "").lower() or "regression" in template.get("id", "").lower():
                e2e_template = template
                break
        
        # Verify template exists and has correct structure
        self.assertIsNotNone(e2e_template, "E2E regression template should exist")
        self.assertIn("steps", e2e_template)
        self.assertIsInstance(e2e_template["steps"], list)
        self.assertGreater(len(e2e_template["steps"]), 0, "E2E template should have steps")


class TestE2EHarnessAssertions(unittest.TestCase):
    """Test that E2E harness has real assertions (not stubs)."""

    def test_smoke_test_has_assertions(self):
        """Verify smoke test has real assertions, not stubs."""
        with open(ROOT / "tests" / "e2e" / "smoke_test.py") as f:
            content = f.read()
        
        # Should NOT have stub patterns
        self.assertNotIn("except Exception: pass", content)
        self.assertNotIn("assertTrue(True)", content)
        self.assertNotIn("pass  # TODO", content)
        
        # Should HAVE real logic - check for if/else conditions and boolean returns
        self.assertIn("record_result", content)
        self.assertIn("if", content)
        self.assertIn("return True", content)
        self.assertIn("return False", content)

    def test_e2e_helpers_have_assertions(self):
        """Verify E2E helpers have real logic."""
        with open(ROOT / "openbot" / "e2e.py") as f:
            content = f.read()
        
        # Should have real implementation
        self.assertIn("def record_e2e_run", content)
        self.assertIn("def latest_e2e_run", content)
        self.assertIn("def e2e_status", content)
        self.assertIn("json.dump", content)
        
        # Should NOT be stubs
        self.assertNotIn("pass  # TODO", content)


if __name__ == "__main__":
    unittest.main()
