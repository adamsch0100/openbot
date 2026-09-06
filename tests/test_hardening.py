"""Tests for WC-2: Coding Worker Hardening."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from openbot import router, gitutil, testrunner, store as store_mod


class TestOpenCodeRetry(unittest.TestCase):
    """Test automatic retry on transient OpenCode failures."""
    
    def test_is_transient_failure_network_errors(self):
        """Network errors are transient."""
        self.assertTrue(router._is_transient_failure(1, "connection timeout"))
        self.assertTrue(router._is_transient_failure(1, "Network error occurred"))
        self.assertTrue(router._is_transient_failure(1, "socket error"))
        self.assertTrue(router._is_transient_failure(1, "DNS resolution failed"))
    
    def test_is_transient_failure_rate_limits(self):
        """Rate limit errors are transient."""
        self.assertTrue(router._is_transient_failure(1, "rate limit exceeded"))
        self.assertTrue(router._is_transient_failure(1, "too many requests"))
        self.assertTrue(router._is_transient_failure(1, "HTTP 429"))
    
    def test_is_transient_failure_api_errors(self):
        """502/503/504 errors are transient."""
        self.assertTrue(router._is_transient_failure(1, "502 bad gateway"))
        self.assertTrue(router._is_transient_failure(1, "503 service unavailable"))
        self.assertTrue(router._is_transient_failure(1, "504 gateway timeout"))
    
    def test_is_not_transient_failure(self):
        """Non-transient errors."""
        self.assertFalse(router._is_transient_failure(0, "success"))
        self.assertFalse(router._is_transient_failure(130, "stopped by user"))
        self.assertFalse(router._is_transient_failure(1, "syntax error"))
        self.assertFalse(router._is_transient_failure(1, "invalid argument"))
    
    @patch("openbot.router.subprocess.Popen")
    @patch("openbot.router.time.sleep")
    def test_retry_on_transient_failure(self, mock_sleep, mock_popen):
        """OpenCode retries on transient failure."""
        # First call fails with network error, second succeeds
        proc1 = MagicMock()
        proc1.returncode = 1
        proc1.stdout.readline.side_effect = ["connection timeout\n", "", "", ""]
        proc1.stdout.read.return_value = ""
        proc1.poll.side_effect = [None, None, 1]
        
        proc2 = MagicMock()
        proc2.returncode = 0
        proc2.stdout.readline.side_effect = ["success\n", "", "", ""]
        proc2.stdout.read.return_value = ""
        proc2.poll.side_effect = [None, None, 0]
        
        mock_popen.side_effect = [proc1, proc2]
        
        with tempfile.TemporaryDirectory() as tmp:
            code, out = router.run_opencode(tmp, "test prompt")
            
            self.assertEqual(code, 0)
            self.assertIn("success", out)
            self.assertEqual(mock_popen.call_count, 2)
            self.assertTrue(mock_sleep.called)
    
    @patch("openbot.router.subprocess.Popen")
    @patch("openbot.router.time.sleep")
    def test_retry_exponential_backoff(self, mock_sleep, mock_popen):
        """Retry uses exponential backoff: 2s, 4s, 8s."""
        # All attempts fail with network error
        def make_proc():
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout.readline.side_effect = ["network error\n", "", "", ""]
            proc.stdout.read.return_value = ""
            proc.poll.side_effect = [None, None, 1]
            return proc
        
        mock_popen.side_effect = [make_proc() for _ in range(4)]
        
        with tempfile.TemporaryDirectory() as tmp:
            code, out = router.run_opencode(tmp, "test prompt")
            
            self.assertEqual(code, 1)
            self.assertIn("network error", out)
            self.assertEqual(mock_popen.call_count, 4)  # initial + 3 retries
            # Check that sleep was called with backoff values 2, 4, 8 (may have extra 0.05 sleeps from loop)
            self.assertGreaterEqual(mock_sleep.call_count, 3)
            # Check that backoff values 2, 4, 8 are present in the calls
            sleep_args = [call[0][0] for call in mock_sleep.call_args_list if call[0][0] >= 1]
            self.assertGreaterEqual(len(sleep_args), 3)
            self.assertIn(2, sleep_args)
            self.assertIn(4, sleep_args)
            self.assertIn(8, sleep_args)


class TestRevertAccept(unittest.TestCase):
    """Test Accept → Revert rollback path."""
    
    @patch("openbot.router.restore_snapshot")
    @patch("openbot.router.read_job")
    @patch("openbot.router.update_job")
    @patch("openbot.router.patch_scope")
    @patch("openbot.router.rollup_staff")
    @patch("openbot.router.log_approval")
    @patch("openbot.router.read_project_index")
    def test_revert_restores_snapshot(self, mock_index, mock_log, mock_rollup, mock_patch, mock_update, mock_read, mock_restore):
        """Revert restores git snapshot."""
        job = {
            "id": "test123",
            "accepted": True,
            "reverted": False,
            "folder": "/tmp/test",
            "git_snapshot": {"is_repo": True, "diff": "", "untracked": []},
        }
        mock_read.return_value = job
        mock_restore.return_value = (True, "restored")
        mock_update.return_value = job
        mock_index.return_value = ""
        
        result = router.revert_accept("test123")
        
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("reverted"))
        mock_restore.assert_called_once()
        mock_update.assert_called_once()
    
    @patch("openbot.router.read_job")
    def test_revert_fails_if_not_accepted(self, mock_read):
        """Revert fails if job not accepted."""
        job = {
            "id": "test456",
            "accepted": False,
            "diff_pending": True,
        }
        mock_read.return_value = job
        
        result = router.revert_accept("test456")
        
        self.assertFalse(result.get("ok"))
        self.assertIn("not accepted", result.get("error", ""))
    
    @patch("openbot.router.read_job")
    def test_revert_fails_if_already_reverted(self, mock_read):
        """Revert fails if already reverted."""
        job = {
            "id": "test789",
            "accepted": True,
            "reverted": True,
        }
        mock_read.return_value = job
        
        result = router.revert_accept("test789")
        
        self.assertFalse(result.get("ok"))
        self.assertIn("already reverted", result.get("error", ""))


class TestBranchPR(unittest.TestCase):
    """Test branch/PR integration."""
    
    def test_create_branch(self):
        """Create and checkout new branch."""
        with tempfile.TemporaryDirectory() as tmp:
            gitutil._run(tmp, ["init"])
            gitutil._run(tmp, ["config", "user.name", "Test"])
            gitutil._run(tmp, ["config", "user.email", "test@example.com"])
            
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("initial\n")
            gitutil._run(tmp, ["add", "."])
            gitutil._run(tmp, ["commit", "-m", "initial"])
            
            ok, msg = gitutil.create_branch(tmp, "feature-test")
            
            self.assertTrue(ok)
            self.assertIn("feature-test", msg)
            
            branch = gitutil.get_current_branch(tmp)
            self.assertEqual(branch, "feature-test")
    
    def test_commit_changes(self):
        """Commit staged changes."""
        with tempfile.TemporaryDirectory() as tmp:
            gitutil._run(tmp, ["init"])
            gitutil._run(tmp, ["config", "user.name", "Test"])
            gitutil._run(tmp, ["config", "user.email", "test@example.com"])
            
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("initial\n")
            gitutil._run(tmp, ["add", "."])
            gitutil._run(tmp, ["commit", "-m", "initial"])
            
            # Make change
            test_file.write_text("changed\n")
            
            ok, msg = gitutil.commit_changes(tmp, "test commit")
            
            self.assertTrue(ok)
            self.assertEqual(msg, "committed")
            
            # Verify commit
            code, log = gitutil._run(tmp, ["log", "--oneline", "-1"])
            self.assertEqual(code, 0)
            self.assertIn("test commit", log)
    
    def test_commit_no_changes(self):
        """Commit fails if no changes."""
        with tempfile.TemporaryDirectory() as tmp:
            gitutil._run(tmp, ["init"])
            gitutil._run(tmp, ["config", "user.name", "Test"])
            gitutil._run(tmp, ["config", "user.email", "test@example.com"])
            
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("initial\n")
            gitutil._run(tmp, ["add", "."])
            gitutil._run(tmp, ["commit", "-m", "initial"])
            
            ok, msg = gitutil.commit_changes(tmp, "test commit")
            
            self.assertFalse(ok)
            self.assertIn("no changes", msg)
    
    @patch("openbot.gitutil._run")
    def test_push_branch(self, mock_run):
        """Push branch to remote."""
        mock_run.return_value = (0, "pushed")
        
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = gitutil.push_branch(tmp, "feature-test")
            
            # Would fail without mock since no remote, but we're testing the call
            mock_run.assert_called()


class TestTestAfterAccept(unittest.TestCase):
    """Test test-after-accept functionality."""
    
    def test_detect_npm_test(self):
        """Detect npm test from package.json."""
        with tempfile.TemporaryDirectory() as tmp:
            package_json = Path(tmp) / "package.json"
            package_json.write_text('{"scripts": {"test": "jest"}}')
            
            cmd = testrunner.detect_test_command(tmp)
            
            self.assertEqual(cmd, "npm test")
    
    def test_detect_pytest(self):
        """Detect pytest from test files."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test_example.py").write_text("def test_foo(): pass")
            
            cmd = testrunner.detect_test_command(tmp)
            
            self.assertIn("pytest", cmd)
    
    def test_no_test_command(self):
        """No test command detected."""
        with tempfile.TemporaryDirectory() as tmp:
            cmd = testrunner.detect_test_command(tmp)
            
            self.assertIsNone(cmd)
    
    @patch("openbot.testrunner.subprocess.run")
    def test_run_tests_success(self, mock_run):
        """Tests pass."""
        mock_run.return_value = MagicMock(returncode=0, stdout="all tests passed", stderr="")
        
        with tempfile.TemporaryDirectory() as tmp:
            ok, output = testrunner.run_tests(tmp, "npm test")
            
            self.assertTrue(ok)
            self.assertIn("all tests passed", output)
    
    @patch("openbot.testrunner.subprocess.run")
    def test_run_tests_failure(self, mock_run):
        """Tests fail."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="1 test failed")
        
        with tempfile.TemporaryDirectory() as tmp:
            ok, output = testrunner.run_tests(tmp, "npm test")
            
            self.assertFalse(ok)
            self.assertIn("1 test failed", output)


if __name__ == "__main__":
    unittest.main()
