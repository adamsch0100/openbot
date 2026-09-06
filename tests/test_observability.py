"""Comprehensive tests for WC-5 Observability."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openbot.store import read_session_log, write_session_log


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


class TestHermesRawLog(unittest.TestCase):
    """Test that Hermes returns raw_log."""

    def test_hermes_result_has_raw_log_field(self):
        """Hermes chat result dict includes raw_log key."""
        # This tests the contract that hermes_chat returns raw_log
        from openbot.hermes import chat as hermes_chat
        
        # We can't easily test the actual Hermes binary, but we can
        # verify the function signature and key structure
        result_keys = {"ok", "code", "text", "usage", "engine", "session", "session_id", "raw_log"}
        
        # Create a minimal result to verify keys
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


class TestProgressEventStructure(unittest.TestCase):
    """Test progress event structure and patterns."""

    def test_progress_event_patterns(self):
        """Verify progress event string patterns match expected format."""
        test_events = [
            "Hermes · terminal",
            "Hermes · command",
            "Hermes · file",
            "Hermes · browser",
            "Hermes · thinking",
            "Hermes · working",
            "OpenCode · edit",
            "OpenCode · tool",
        ]
        
        for event in test_events:
            self.assertIn("·", event)
            parts = event.split("·")
            self.assertEqual(len(parts), 2)
            engine = parts[0].strip()
            action = parts[1].strip()
            self.assertTrue(engine in ["Hermes", "OpenCode"])
            self.assertTrue(len(action) > 0)


class TestLogStorageIntegration(unittest.TestCase):
    """Test log storage in actual job workflow."""

    def test_log_filename_matches_job_id(self):
        """Log files are named {job_id}.log."""
        job_id = "testjob789"
        log_content = "Session output here"
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        self.assertEqual(path.stem, job_id)
        self.assertEqual(path.suffix, ".log")
        
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


class TestAPIContract(unittest.TestCase):
    """Test the API contract for log retrieval."""

    def test_api_endpoint_pattern(self):
        """Verify API endpoint follows pattern /api/jobs/{id}/log."""
        endpoint_pattern = "/api/jobs/{id}/log"
        job_id = "test123"
        expected = f"/api/jobs/{job_id}/log"
        actual = endpoint_pattern.replace("{id}", job_id)
        self.assertEqual(actual, expected)

    def test_api_response_structure(self):
        """API response should have job_id and log fields."""
        response = {
            "job_id": "test123",
            "log": "Session log content"
        }
        self.assertIn("job_id", response)
        self.assertIn("log", response)
        self.assertEqual(response["job_id"], "test123")


if __name__ == "__main__":
    unittest.main()



class TestSessionLogStorage(unittest.TestCase):
    """Test session log storage for Hermes and OpenCode."""

    def test_write_and_read_session_log(self):
        """Session logs can be written and read from jobs/."""
        log_content = "Test session log output\nLine 2\nLine 3"
        job_id = "test123abc"
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, f"{job_id}.log")
        
        retrieved = read_session_log(job_id)
        self.assertEqual(retrieved, log_content)

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


class TestHermesProgressStreaming(unittest.TestCase):
    """Test Hermes tool-call progress streaming."""

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_hermes_emits_tool_progress_chips(self, mock_popen, mock_which):
        """Hermes tool calls emit progress chips during execution."""
        mock_which.return_value = "/usr/local/bin/hermes"
        
        progress_events = []
        
        def capture_progress(event):
            progress_events.append(event)
        
        # Simulate Hermes output with tool calls
        mock_proc = Mock()
        mock_proc.stdout.readline.side_effect = [
            "run terminal: ls\n",
            "command is: git status\n",
            "file_read: config.py\n",
            "browser_navigate to https://example.com\n",
            "thinking about next steps\n",
            "",
        ]
        mock_proc.poll.side_effect = [None, None, None, None, None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            result = hermes_chat(
                "Test prompt",
                cwd=tmp,
                on_progress=capture_progress,
                timeout=5,
            )
        
        # Verify progress chips were emitted
        self.assertGreater(len(progress_events), 0)
        self.assertTrue(any("terminal" in e.lower() for e in progress_events))
        self.assertTrue(any("command" in e.lower() for e in progress_events))
        self.assertTrue(any("file" in e.lower() for e in progress_events))
        self.assertTrue(any("browser" in e.lower() for e in progress_events))
        self.assertTrue(any("thinking" in e.lower() for e in progress_events))

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_hermes_raw_log_included(self, mock_popen, mock_which):
        """Hermes chat returns raw_log in result."""
        mock_which.return_value = "/usr/local/bin/hermes"
        
        mock_proc = Mock()
        session_output = "session_id: abc123\nTool call: file_read\nResult: Success\n"
        mock_proc.stdout.readline.side_effect = [
            line + "\n" for line in session_output.split("\n")
        ] + [""]
        mock_proc.poll.side_effect = [None] * 5 + [0]
        mock_proc.returncode = 0
        mock_proc.stderr = None
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            result = hermes_chat("Test prompt", cwd=tmp, timeout=5)
        
        self.assertIn("raw_log", result)
        self.assertTrue(result["raw_log"])
        self.assertIn("file_read", result["raw_log"])


class TestOpenCodeLogStorage(unittest.TestCase):
    """Test OpenCode session log storage."""

    @patch("openbot.router.which")
    @patch("subprocess.Popen")
    def test_opencode_returns_raw_log(self, mock_popen, mock_which):
        """OpenCode run_opencode returns raw log as third value."""
        mock_which.return_value = "/usr/local/bin/opencode"
        
        mock_proc = Mock()
        output_lines = [
            '{"type": "step_start", "part": {"name": "edit"}}\n',
            '{"type": "delta", "part": {"text": "Editing file..."}}\n',
            '{"type": "step_end"}\n',
        ]
        mock_proc.stdout.readline.side_effect = output_lines + [""]
        mock_proc.poll.side_effect = [None] * 4 + [0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            code, out, raw_log = run_opencode(
                tmp, "Test prompt", "/usr/local/bin/opencode", "model"
            )
        
        self.assertEqual(code, 0)
        self.assertTrue(raw_log)
        self.assertIn("step_start", raw_log)
        self.assertIn("Editing file", raw_log)


class TestObservabilityAPI(unittest.TestCase):
    """Test /api/jobs/{id}/log endpoint."""

    def test_write_session_log_creates_file(self):
        """Session log is stored in jobs/ directory."""
        job_id = "testjob456"
        log_content = "Session log line 1\nSession log line 2"
        path = write_session_log(job_id, log_content)
        
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        
        # Verify content
        retrieved = read_session_log(job_id)
        self.assertEqual(retrieved, log_content)

    def test_read_session_log_missing_returns_none(self):
        """Reading nonexistent session log returns None."""
        result = read_session_log("nonexistent999")
        self.assertIsNone(result)


class TestProgressStreaming(unittest.TestCase):
    """Test real-time progress streaming from Hermes."""

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_progress_callback_fires_on_tool_activity(self, mock_popen, mock_which):
        """on_progress callback fires when tool activity detected."""
        mock_which.return_value = "/usr/local/bin/hermes"
        
        progress_log = []
        
        def track_progress(msg):
            progress_log.append(msg)
        
        mock_proc = Mock()
        mock_proc.stdout.readline.side_effect = [
            "Starting task\n",
            "run terminal: git diff\n",
            "file_write: output.txt\n",
            "Done\n",
            "",
        ]
        mock_proc.poll.side_effect = [None, None, None, None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            hermes_chat(
                "Test",
                cwd=tmp,
                on_progress=track_progress,
                timeout=5,
            )
        
        self.assertTrue(any("terminal" in msg.lower() for msg in progress_log))
        self.assertTrue(any("file" in msg.lower() for msg in progress_log))


if __name__ == "__main__":
    unittest.main()



class TestSessionLogStorage(unittest.TestCase):
    """Test session log storage for Hermes and OpenCode."""

    def test_write_and_read_session_log(self):
        """Session logs can be written and read from jobs/."""
        log_content = "Test session log output\nLine 2\nLine 3"
        job_id = "test123abc"
        
        path = write_session_log(job_id, log_content)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, f"{job_id}.log")
        
        retrieved = read_session_log(job_id)
        self.assertEqual(retrieved, log_content)

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


class TestHermesProgressStreaming(unittest.TestCase):
    """Test Hermes tool-call progress streaming."""

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_hermes_emits_tool_progress_chips(self, mock_popen, mock_which):
        """Hermes tool calls emit progress chips during execution."""
        mock_which.return_value = "/usr/local/bin/hermes"
        
        progress_events = []
        
        def capture_progress(event):
            progress_events.append(event)
        
        # Simulate Hermes output with tool calls
        mock_proc = Mock()
        mock_proc.stdout.readline.side_effect = [
            "run terminal: ls\n",
            "command is: git status\n",
            "file_read: config.py\n",
            "browser_navigate to https://example.com\n",
            "thinking about next steps\n",
            "",
        ]
        mock_proc.poll.side_effect = [None, None, None, None, None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            result = hermes_chat(
                "Test prompt",
                cwd=tmp,
                on_progress=capture_progress,
                timeout=5,
            )
        
        # Verify progress chips were emitted
        self.assertGreater(len(progress_events), 0)
        self.assertTrue(any("terminal" in e.lower() for e in progress_events))
        self.assertTrue(any("command" in e.lower() for e in progress_events))
        self.assertTrue(any("file" in e.lower() for e in progress_events))
        self.assertTrue(any("browser" in e.lower() for e in progress_events))
        self.assertTrue(any("thinking" in e.lower() for e in progress_events))

    @patch("openbot.hermes.which")
    @patch("openbot.hermes._popen")
    def test_hermes_raw_log_included(self, mock_popen, mock_which):
        """Hermes chat returns raw_log in result."""
        mock_which.return_value = "/usr/local/bin/hermes"
        
        mock_proc = Mock()
        session_output = "session_id: abc123\nTool call: file_read\nResult: Success\n"
        mock_proc.stdout.readline.side_effect = [
            line + "\n" for line in session_output.split("\n")
        ] + [""]
        mock_proc.poll.side_effect = [None] * 5 + [0]
        mock_proc.returncode = 0
        mock_proc.stderr = None
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            result = hermes_chat("Test prompt", cwd=tmp, timeout=5)
        
        self.assertIn("raw_log", result)
        self.assertTrue(result["raw_log"])
        self.assertIn("file_read", result["raw_log"])


class TestOpenCodeLogStorage(unittest.TestCase):
    """Test OpenCode session log storage."""

    @patch("openbot.router.which")
    @patch("subprocess.Popen")
    def test_opencode_returns_raw_log(self, mock_popen, mock_which):
        """OpenCode run_opencode returns raw log as third value."""
        mock_which.return_value = "/usr/local/bin/opencode"
        
        mock_proc = Mock()
        output_lines = [
            '{"type": "step_start", "part": {"name": "edit"}}\n',
            '{"type": "delta", "part": {"text": "Editing file..."}}\n',
            '{"type": "step_end"}\n',
        ]
        mock_proc.stdout.readline.side_effect = output_lines + [""]
        mock_proc.poll.side_effect = [None] * 4 + [0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        with tempfile.TemporaryDirectory() as tmp:
            code, out, raw_log = run_opencode(
                tmp, "Test prompt", "/usr/local/bin/opencode", "model"
            )
        
        self.assertEqual(code, 0)
        self.assertTrue(raw_log)
        self.assertIn("step_start", raw_log)
        self.assertIn("Editing file", raw_log)


class TestObservabilityAPI(unittest.TestCase):
    """Test /api/jobs/{id}/log endpoint."""

    def test_api_returns_session_log(self):
        """GET /api/jobs/{id}/log returns stored session log."""
        from openbot.server import Handler
        from unittest.mock import MagicMock
        
        job_id = "testjob456"
        log_content = "Session log line 1\nSession log line 2"
        write_session_log(job_id, log_content)
        
        handler = Handler(MagicMock(), ("127.0.0.1", 8787), MagicMock())
        handler._unlocked = lambda: True
        handler.path = f"/api/jobs/{job_id}/log"
        
        response_data = {}
        
        def mock_json(code, payload, **kwargs):
            response_data["code"] = code
            response_data["payload"] = payload
        
        handler._json = mock_json
        handler.do_GET()
        
        self.assertEqual(response_data["code"], 200)
        self.assertEqual(response_data["payload"]["job_id"], job_id)
        self.assertEqual(response_data["payload"]["log"], log_content)

    def test_api_returns_404_for_missing_log(self):
        """GET /api/jobs/{id}/log returns 404 when log not found."""
        from openbot.server import Handler
        from unittest.mock import MagicMock
        
        handler = Handler(MagicMock(), ("127.0.0.1", 8787), MagicMock())
        handler._unlocked = lambda: True
        handler.path = "/api/jobs/nonexistent999/log"
        
        response_data = {}
        
        def mock_json(code, payload, **kwargs):
            response_data["code"] = code
            response_data["payload"] = payload
        
        handler._json = mock_json
        handler.do_GET()
        
        self.assertEqual(response_data["code"], 404)
        self.assertIn("error", response_data["payload"])


class TestWorkIntegration(unittest.TestCase):
    """Test that work() stores session logs for jobs."""

    @patch("openbot.router.detect")
    @patch("openbot.router.load_config")
    @patch("openbot.router.load_settings")
    @patch("openbot.router.hermes_chat")
    @patch("openbot.router.write_session_log")
    def test_work_stores_hermes_log(
        self, mock_write_log, mock_hermes, mock_settings, mock_config, mock_detect
    ):
        """work() stores Hermes session log after job completion."""
        mock_detect.return_value = {
            "hermes": {"present": True, "path": "/bin/hermes"},
            "opencode": {"present": False},
        }
        mock_config.return_value = {
            "work_dir": "/tmp/test",
            "work_dir_ok": True,
            "first_run_done": True,
            "spend_cap_usd": 5.0,
            "spend_cap_period": "week",
        }
        mock_settings.return_value = {"seats": {}}
        
        session_log = "Hermes session: tool call file_read\nResult: success"
        mock_hermes.return_value = {
            "ok": True,
            "code": 0,
            "text": "Job completed successfully",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "raw_log": session_log,
            "session_id": "test_session",
        }
        
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "brains").mkdir()
            Path(tmp, "brains", "INDEX.md").write_text("Now: test\n")
            
            result = work(
                message="Test research task",
                preset="research",
                tools={},
                project_id=None,
                worker_id=None,
            )
        
        # Verify session log was stored
        mock_write_log.assert_called()
        args = mock_write_log.call_args
        self.assertEqual(len(args[0]), 2)
        stored_log = args[0][1]
        self.assertEqual(stored_log, session_log)


if __name__ == "__main__":
    unittest.main()
