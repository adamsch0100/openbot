"""Tests for onboarding flow: auth checks and test job."""

import unittest
from unittest.mock import MagicMock, patch
import subprocess

from openbot.onboarding import (
    check_hermes_auth,
    check_opencode_auth,
    onboarding_status,
    test_job_prompt,
)


class TestOnboarding(unittest.TestCase):
    """Test onboarding auth checks and test job flow."""

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_hermes_auth_authenticated_portal(self, mock_run, mock_which):
        """Hermes authenticated via portal shows authenticated=True."""
        mock_which.return_value = "/usr/bin/hermes"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Status: authenticated\n"
        mock_run.return_value = mock_result

        result = check_hermes_auth()

        self.assertTrue(result["authenticated"])
        self.assertEqual(result["method"], "portal")
        self.assertIsNone(result["error"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[:3], ["/usr/bin/hermes", "portal", "status"])

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_hermes_auth_authenticated_session(self, mock_run, mock_which):
        """Hermes authenticated via session shows authenticated=True."""
        mock_which.return_value = "/usr/bin/hermes"
        
        # Portal status fails
        portal_result = MagicMock()
        portal_result.returncode = 1
        portal_result.stdout = "Not authenticated\n"
        
        # Session list succeeds
        session_result = MagicMock()
        session_result.returncode = 0
        session_result.stdout = "session-123\nsession-456\n"
        
        mock_run.side_effect = [portal_result, session_result]

        result = check_hermes_auth()

        self.assertTrue(result["authenticated"])
        self.assertEqual(result["method"], "session")
        self.assertIsNone(result["error"])
        self.assertEqual(mock_run.call_count, 2)

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_hermes_auth_not_authenticated(self, mock_run, mock_which):
        """Hermes not authenticated shows authenticated=False."""
        mock_which.return_value = "/usr/bin/hermes"
        
        portal_result = MagicMock()
        portal_result.returncode = 1
        portal_result.stdout = "Not authenticated\n"
        
        session_result = MagicMock()
        session_result.returncode = 0
        session_result.stdout = ""
        
        mock_run.side_effect = [portal_result, session_result]

        result = check_hermes_auth()

        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["method"])
        self.assertIsNone(result["error"])

    @patch("openbot.onboarding.which")
    def test_check_hermes_auth_binary_not_found(self, mock_which):
        """Hermes binary not found shows error."""
        mock_which.return_value = None

        result = check_hermes_auth()

        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["method"])
        self.assertIn("not found", result["error"])

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_hermes_auth_timeout(self, mock_run, mock_which):
        """Hermes auth check timeout shows error."""
        mock_which.return_value = "/usr/bin/hermes"
        mock_run.side_effect = subprocess.TimeoutExpired("hermes", 10)

        result = check_hermes_auth()

        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["method"])
        self.assertIsNotNone(result["error"])

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_opencode_auth_authenticated(self, mock_run, mock_which):
        """OpenCode authenticated shows authenticated=True."""
        mock_which.return_value = "/usr/bin/opencode"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Status: authenticated\n"
        mock_run.return_value = mock_result

        result = check_opencode_auth()

        self.assertTrue(result["authenticated"])
        self.assertEqual(result["method"], "oauth")
        self.assertIsNone(result["error"])
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[:3], ["/usr/bin/opencode", "auth", "status"])

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_opencode_auth_provider_list(self, mock_run, mock_which):
        """OpenCode authenticated via provider list shows authenticated=True."""
        mock_which.return_value = "/usr/bin/opencode"
        
        status_result = MagicMock()
        status_result.returncode = 1
        status_result.stdout = "Not authenticated\n"
        
        list_result = MagicMock()
        list_result.returncode = 0
        list_result.stdout = "opencode-zen\nopenrouter\n"
        
        mock_run.side_effect = [status_result, list_result]

        result = check_opencode_auth()

        self.assertTrue(result["authenticated"])
        self.assertEqual(result["method"], "provider")
        self.assertIsNone(result["error"])
        self.assertEqual(mock_run.call_count, 2)

    @patch("openbot.onboarding.which")
    @patch("subprocess.run")
    def test_check_opencode_auth_not_authenticated(self, mock_run, mock_which):
        """OpenCode not authenticated shows authenticated=False."""
        mock_which.return_value = "/usr/bin/opencode"
        
        status_result = MagicMock()
        status_result.returncode = 1
        status_result.stdout = "Not authenticated\n"
        
        list_result = MagicMock()
        list_result.returncode = 0
        list_result.stdout = ""
        
        mock_run.side_effect = [status_result, list_result]

        result = check_opencode_auth()

        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["method"])
        self.assertIsNone(result["error"])

    @patch("openbot.onboarding.which")
    def test_check_opencode_auth_binary_not_found(self, mock_which):
        """OpenCode binary not found shows error."""
        mock_which.return_value = None

        result = check_opencode_auth()

        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["method"])
        self.assertIn("not found", result["error"])

    @patch("openbot.onboarding.check_hermes_auth")
    @patch("openbot.onboarding.check_opencode_auth")
    def test_onboarding_status_both_authenticated(self, mock_oc, mock_hermes):
        """Onboarding status shows ready when both engines authenticated."""
        mock_hermes.return_value = {
            "authenticated": True,
            "method": "portal",
            "error": None,
        }
        mock_oc.return_value = {
            "authenticated": True,
            "method": "oauth",
            "error": None,
        }

        result = onboarding_status()

        self.assertTrue(result["ready"])
        self.assertTrue(result["hermes"]["authenticated"])
        self.assertTrue(result["opencode"]["authenticated"])

    @patch("openbot.onboarding.check_hermes_auth")
    @patch("openbot.onboarding.check_opencode_auth")
    def test_onboarding_status_hermes_missing(self, mock_oc, mock_hermes):
        """Onboarding status shows not ready when Hermes not authenticated."""
        mock_hermes.return_value = {
            "authenticated": False,
            "method": None,
            "error": None,
        }
        mock_oc.return_value = {
            "authenticated": True,
            "method": "oauth",
            "error": None,
        }

        result = onboarding_status()

        self.assertFalse(result["ready"])
        self.assertFalse(result["hermes"]["authenticated"])
        self.assertTrue(result["opencode"]["authenticated"])

    @patch("openbot.onboarding.check_hermes_auth")
    @patch("openbot.onboarding.check_opencode_auth")
    def test_onboarding_status_opencode_missing(self, mock_oc, mock_hermes):
        """Onboarding status shows not ready when OpenCode not authenticated."""
        mock_hermes.return_value = {
            "authenticated": True,
            "method": "portal",
            "error": None,
        }
        mock_oc.return_value = {
            "authenticated": False,
            "method": None,
            "error": None,
        }

        result = onboarding_status()

        self.assertFalse(result["ready"])
        self.assertTrue(result["hermes"]["authenticated"])
        self.assertFalse(result["opencode"]["authenticated"])

    @patch("openbot.onboarding.check_hermes_auth")
    @patch("openbot.onboarding.check_opencode_auth")
    def test_onboarding_status_both_missing(self, mock_oc, mock_hermes):
        """Onboarding status shows not ready when both engines not authenticated."""
        mock_hermes.return_value = {
            "authenticated": False,
            "method": None,
            "error": None,
        }
        mock_oc.return_value = {
            "authenticated": False,
            "method": None,
            "error": None,
        }

        result = onboarding_status()

        self.assertFalse(result["ready"])
        self.assertFalse(result["hermes"]["authenticated"])
        self.assertFalse(result["opencode"]["authenticated"])

    def test_test_job_prompt(self):
        """Test job prompt returns valid prompt string."""
        prompt = test_job_prompt()
        
        self.assertIsInstance(prompt, str)
        self.assertIn("hello.txt", prompt.lower())
        self.assertIn("openbot", prompt.lower())
        self.assertTrue(len(prompt) > 50)


if __name__ == "__main__":
    unittest.main()
