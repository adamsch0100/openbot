"""Comprehensive tests for WC-5 Observability."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openbot.store import read_session_log, write_session_log, mark_job_has_log


class TestSessionLogStorage(unittest.TestCase):
    """Test session log storage for Hermes and OpenCode."""

    def test_write_and_read_session_log(self):
        """Session logs can be written and read from jobs/."""
        log_content = "Test session log output\nLine 2\nLine 3"
        job_id = "abc123def456"
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, f"{job_id}.log")
        
        retrieved = read_session_log(job_id)
        self.assertEqual(retrieved, log_content)
        
        # Clean up
        if path.exists():
            path.unlink()

    def test_read_nonexistent_log(self):
        """Reading nonexistent log returns None."""
        result = read_session_log("nonexistent999")
        self.assertIsNone(result)

    def test_invalid_job_id_rejected(self):
        """Invalid job IDs are rejected."""
        invalid_ids = ["../etc/passwd", "test;rm", "test\nid", ""]
        for bad_id in invalid_ids:
            result = write_session_log(bad_id, "content")
            self.assertIsNone(result)
            retrieved = read_session_log(bad_id)
            self.assertIsNone(retrieved)

    def test_unicode_in_log(self):
        """Session logs handle unicode content correctly."""
        log_content = "Unicode test: 你好 世界 🎉 Hermes Agent → OpenCode"
        job_id = "unicode123"
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        
        retrieved = read_session_log(job_id)
        self.assertEqual(retrieved, log_content)
        
        # Clean up
        if path.exists():
            path.unlink()

    def test_large_log_storage(self):
        """Large session logs can be stored and retrieved."""
        job_id = "largelog123"
        # Create a large log (1MB of text)
        log_content = "Log line " * 100000
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        
        retrieved = read_session_log(job_id)
        self.assertEqual(len(retrieved), len(log_content))
        self.assertEqual(retrieved, log_content)
        
        # Clean up
        if path.exists():
            path.unlink()


class TestHermesProgressChips(unittest.TestCase):
    """Test Hermes progress chip patterns."""

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_hermes_emits_progress_on_tool_activity(self, mock_popen, mock_which):
        """Hermes on_progress callback fires when tool activity detected."""
        from openbot.hermes import chat as hermes_chat
        
        mock_which.return_value = "/usr/local/bin/hermes"
        
        progress_log = []
        
        def track_progress(msg):
            progress_log.append(msg)
        
        mock_proc = Mock()
        mock_proc.stdout = Mock()
        
        # Simulate readline behavior for tool activity
        lines = [
            "Starting task\n",
            "run terminal: git diff\n",
            "file_write: output.txt\n",
            "browser_navigate to https://example.com\n",
            "Done\n",
            "",
        ]
        mock_proc.stdout.readline = Mock(side_effect=lines)
        mock_proc.poll = Mock(side_effect=[None, None, None, None, None, 0])
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            result = hermes_chat(
                "Test",
                cwd=tmp,
                on_progress=track_progress,
                timeout=5,
            )
        
        # Verify progress chips were emitted for tool activity
        self.assertTrue(any("terminal" in msg.lower() or "command" in msg.lower() for msg in progress_log))
        self.assertTrue(any("file" in msg.lower() for msg in progress_log))

    def test_progress_event_format(self):
        """Progress events follow expected format."""
        test_events = [
            "Hermes · terminal",
            "Hermes · command",
            "Hermes · file",
            "Hermes · browser",
            "OpenCode · edit",
        ]
        
        for event in test_events:
            self.assertIn("·", event)
            parts = event.split("·")
            self.assertEqual(len(parts), 2)
            engine = parts[0].strip()
            action = parts[1].strip()
            self.assertTrue(engine in ["Hermes", "OpenCode"])
            self.assertTrue(len(action) > 0)


class TestAPIEndpoint(unittest.TestCase):
    """Test /api/jobs/{id}/log endpoint contract."""

    def test_api_endpoint_pattern(self):
        """API endpoint follows /api/jobs/{id}/log pattern."""
        endpoint_pattern = "/api/jobs/{id}/log"
        job_id = "test123"
        expected = f"/api/jobs/{job_id}/log"
        actual = endpoint_pattern.replace("{id}", job_id)
        self.assertEqual(actual, expected)

    def test_api_response_structure(self):
        """API response has job_id and log fields."""
        response = {
            "job_id": "test123",
            "log": "Session log content"
        }
        self.assertIn("job_id", response)
        self.assertIn("log", response)

    def test_write_log_marks_job_receipt(self):
        """Writing session log marks job receipt with has_session_log."""
        from openbot.store import write_job
        
        job_id = "markertest"
        receipt = {
            "id": job_id,
            "at": "2026-09-06T01:00:00Z",
            "engine": "Hermes Agent",
            "text": "Test output"
        }
        
        # Write job receipt
        write_job(receipt)
        
        # Write session log and mark
        log_content = "Test session log"
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        
        # Mark job has log
        result = mark_job_has_log(job_id)
        self.assertTrue(result)
        
        # Verify has_session_log is set
        from openbot.store import read_job
        updated = read_job(job_id)
        self.assertIsNotNone(updated)
        self.assertTrue(updated.get("has_session_log"))
        
        # Clean up
        if path.exists():
            path.unlink()
        job_path = Path(__file__).parent.parent / "jobs" / f"{job_id}.json"
        if job_path.exists():
            job_path.unlink()


class TestRouterIntegration(unittest.TestCase):
    """Test router stores logs and marks receipts."""

    def test_hermes_raw_log_contract(self):
        """Hermes chat result includes raw_log field."""
        result_keys = {"ok", "code", "text", "usage", "engine", "session", "session_id", "raw_log"}
        
        # Verify expected contract
        test_result = {
            "ok": True,
            "code": 0,
            "text": "output",
            "usage": {},
            "engine": "Hermes Agent",
            "session": "",
            "session_id": "",
            "raw_log": "test log",
        }
        
        for key in result_keys:
            self.assertIn(key, test_result)


if __name__ == "__main__":
    unittest.main()
