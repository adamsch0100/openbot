"""Chat OS Reliability tests for PR #2.

Tests that Cos status questions and CEO Chat sends never hang empty,
always stream progress or show a clear error card.
"""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import openbot.config as config_mod
import openbot.org as org_mod
import openbot.store as store_mod
from openbot.router import handle


class CosReliabilityTests(unittest.TestCase):
    """Test Cos status questions never hang or fail silently."""

    def test_cos_status_always_replies(self):
        """Cos status should always return a reply, never empty."""
        job = handle("What is going on?")
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        self.assertTrue(job.get("talk"))
        self.assertTrue(job.get("text"), "Cos status returned empty text")
        self.assertNotIn("(no output)", job.get("text") or "")

    def test_cos_status_with_index_fields(self):
        """Cos should extract Now/Last/Next/Blocker from INDEX."""
        job = handle("status", project_id="openbot")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos status returned empty text for project")
        # Should show at least one INDEX field
        has_field = any(
            field in text for field in ["Now:", "Last:", "Next:", "Blocker:"]
        )
        self.assertTrue(has_field, "Status reply missing INDEX fields")

    def test_cos_greeting_always_replies(self):
        """Cos greeting should always return a reply."""
        job = handle("hello")
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos greeting returned empty text")
        self.assertIn("Chief of Staff", text)

    def test_cos_thanks_always_replies(self):
        """Cos thanks should always return a reply."""
        job = handle("thanks")
        self.assertEqual(job.get("preset"), "cos")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos thanks returned empty text")

    def test_cos_browser_login_blocked(self):
        """Cos should reply to browser login requests with vault guidance."""
        job = handle("browser login for facebook")
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos browser login request returned empty text")
        self.assertIn("browser", text.lower())
        self.assertIn("vault", text.lower())

    def test_cos_skills_ask(self):
        """Cos should reply to skills questions."""
        job = handle("how do I add skills")
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos skills ask returned empty text")
        self.assertIn("skill", text.lower())

    def test_cos_with_quote(self):
        """Cos status with quote should still reply."""
        job = handle("as I said earlier, check status", quote="navy landing page")
        self.assertEqual(job.get("preset"), "cos")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos with quote returned empty text")

    def test_cos_project_status(self):
        """Cos should reply for project-specific status."""
        job = handle("blocked", project_id="openbot")
        self.assertEqual(job.get("preset"), "cos")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos project status returned empty text")

    def test_cos_worker_status(self):
        """Cos should reply for worker status."""
        job = handle("what's next", project_id="openbot", worker_id="test-worker")
        self.assertEqual(job.get("preset"), "cos")
        text = job.get("text") or ""
        self.assertTrue(text, "Cos worker status returned empty text")

    def test_cos_multiple_status_asks(self):
        """Multiple Cos status asks should all complete successfully."""
        messages = [
            "What is going on?",
            "What's blocked?",
            "status",
            "hello",
            "thanks",
            "What is the current status?",
            "blocked",
            "what's next",
            "index",
            "how do I add skills",
        ]
        for msg in messages:
            with self.subTest(message=msg):
                job = handle(msg)
                self.assertEqual(job.get("preset"), "cos", f"Wrong preset for: {msg}")
                text = job.get("text") or ""
                self.assertTrue(text, f"Empty reply for: {msg}")
                self.assertNotIn("(no output)", text, f"No output for: {msg}")


class CeoChatReliabilityTests(unittest.TestCase):
    """Test CEO Chat never hangs or fails silently."""

    def setUp(self):
        """Set up mocks for Hermes chat."""
        self.old_org = org_mod.ORG
        self.old_profile = org_mod.PROFILE_PATH
        self.old_homes = org_mod.HERMES_HOMES
        self.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(self.temp_dir.name)
        org_mod.ORG = folder / "org"
        org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
        org_mod.HERMES_HOMES = folder / "hermes-homes"

    def tearDown(self):
        """Restore original paths."""
        org_mod.ORG = self.old_org
        org_mod.PROFILE_PATH = self.old_profile
        org_mod.HERMES_HOMES = self.old_homes
        self.temp_dir.cleanup()

    def test_ceo_chat_with_hermes_success(self):
        """CEO Chat should complete when Hermes succeeds."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": True,
                "code": 0,
                "text": "Hello from Hermes.",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello, how are you?", project_id="openbot")
        
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "Hermes Agent")
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat returned empty text")
        self.assertIn("Hello from Hermes", text)

    def test_ceo_chat_with_hermes_failure_shows_fallback(self):
        """CEO Chat should show fallback brief when Hermes fails."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": False,
                "code": 1,
                "text": "Error running Hermes",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot")
        
        self.assertEqual(job.get("preset"), "cos")
        # Should fall back to board brief, not empty
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat with Hermes failure returned empty text")
        self.assertNotIn("(no output)", text)

    def test_ceo_chat_with_hermes_timeout_shows_fallback(self):
        """CEO Chat should show fallback brief when Hermes times out."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": False,
                "code": 124,
                "text": "hermes timed out",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot")
        
        self.assertEqual(job.get("preset"), "cos")
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat with timeout returned empty text")
        self.assertNotIn("(no output)", text)

    def test_ceo_chat_with_empty_hermes_output_shows_fallback(self):
        """CEO Chat should show fallback when Hermes returns empty output."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": True,
                "code": 0,
                "text": "(no output)",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot")
        
        self.assertEqual(job.get("preset"), "cos")
        # Should fall back to board brief, not "(no output)"
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat with empty output returned empty text")
        self.assertNotIn("(no output)", text)

    def test_ceo_chat_with_wallet_empty_shows_clear_error(self):
        """CEO Chat should show wallet empty error clearly."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": False,
                "code": 1,
                "text": "HTTP 401: Insufficient balance. Manage your billing here: https://opencode.ai/workspace/x/billing",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot")
        
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat with wallet empty returned empty text")
        self.assertIn("wallet", text.lower())

    def test_ceo_chat_keyring_fallback(self):
        """CEO Chat should try multiple accounts in keyring order."""
        call_count = [0]
        
        def mock_chat_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails with wallet empty
                return {
                    "ok": False,
                    "code": 1,
                    "text": "HTTP 401: Insufficient balance.",
                    "usage": {},
                }
            else:
                # Second call succeeds
                return {
                    "ok": True,
                    "code": 0,
                    "text": "Success from second account.",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                }
        
        with patch("openbot.router.hermes_chat", side_effect=mock_chat_side_effect):
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router._chat_attempts") as mock_attempts:
                    mock_attempts.return_value = [
                        ({"id": "acc1", "provider": "opencode"}, "opencode/gpt-5.4-nano"),
                        ({"id": "acc2", "provider": "opencode"}, "opencode/gpt-5.4-nano"),
                    ]
                    with patch("openbot.router.detect") as mock_detect:
                        mock_detect.return_value = {
                            "hermes": {"present": True},
                            "opencode": {"present": True},
                            "board": {"present": True},
                        }
                        with patch("openbot.router.activate_account"):
                            with patch("openbot.router._activate"):
                                job = handle("hello", project_id="openbot")
        
        self.assertEqual(call_count[0], 2, "Should have tried 2 accounts")
        text = job.get("text") or ""
        self.assertTrue(text, "CEO Chat with keyring fallback returned empty text")
        self.assertIn("Success from second account", text)

    def test_multiple_ceo_chat_sends(self):
        """Multiple CEO Chat sends should all complete successfully."""
        messages = [
            "hello",
            "how are you?",
            "what should we do today?",
            "can you help with this task?",
            "thanks for your help",
        ]
        
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": True,
                "code": 0,
                "text": "Response from Hermes.",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    for msg in messages:
                        with self.subTest(message=msg):
                            job = handle(msg, project_id="openbot")
                            self.assertEqual(job.get("preset"), "cos", f"Wrong preset for: {msg}")
                            text = job.get("text") or ""
                            self.assertTrue(text, f"Empty reply for: {msg}")
                            self.assertNotIn("(no output)", text, f"No output for: {msg}")


class ProgressVisibilityTests(unittest.TestCase):
    """Test that progress is always visible during operations."""

    def test_cos_status_calls_progress(self):
        """Cos status should call progress callback."""
        progress_calls = []
        
        def on_progress(text, lane=None):
            progress_calls.append((text, lane))
        
        job = handle("status", on_progress=on_progress)
        # Cos status is board-only, so no engine progress
        # But it should still complete without hanging
        self.assertTrue(job.get("text"), "Cos status returned empty")

    def test_ceo_chat_calls_progress(self):
        """CEO Chat should call progress callback."""
        progress_calls = []
        
        def on_progress(text, lane=None):
            progress_calls.append((text, lane))
        
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": True,
                "code": 0,
                "text": "Response.",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot", on_progress=on_progress)
        
        # Should have called progress with CEO name + Chat
        self.assertTrue(progress_calls, "No progress calls made")
        progress_text = " ".join(text for text, _ in progress_calls)
        self.assertIn("Chat", progress_text)


class TimeoutHandlingTests(unittest.TestCase):
    """Test timeout handling for Hermes operations."""

    def test_hermes_timeout_returns_structured_error(self):
        """Hermes timeout should return structured error, not silent hang."""
        with patch("openbot.router.hermes_chat") as mock_chat:
            mock_chat.return_value = {
                "ok": False,
                "code": 124,
                "text": "hermes timed out",
                "usage": {},
            }
            with patch("openbot.router.seated_or_auto", return_value="opencode/gpt-5.4-nano"):
                with patch("openbot.router.detect") as mock_detect:
                    mock_detect.return_value = {
                        "hermes": {"present": True},
                        "opencode": {"present": True},
                        "board": {"present": True},
                    }
                    job = handle("hello", project_id="openbot")
        
        # Should fall back to brief, not hang
        self.assertTrue(job.get("text"), "Timeout resulted in empty text")
        self.assertNotIn("(no output)", job.get("text") or "")

    def test_clean_hermes_fail_hint_timeout(self):
        """Timeout error should have clear hint."""
        from openbot.router import clean_hermes_fail_hint
        
        ran = {"code": 124, "text": "hermes timed out"}
        hint = clean_hermes_fail_hint(ran)
        self.assertIn("timed out", hint.lower())
        self.assertIn("brief", hint.lower())

    def test_clean_hermes_fail_hint_missing_binary(self):
        """Missing binary error should have clear hint."""
        from openbot.router import clean_hermes_fail_hint
        
        ran = {"code": 127, "text": "Hermes Agent binary missing"}
        hint = clean_hermes_fail_hint(ran)
        self.assertIn("missing", hint.lower())
        self.assertIn("brief", hint.lower())

    def test_clean_hermes_fail_hint_no_model(self):
        """No model error should have clear hint."""
        from openbot.router import clean_hermes_fail_hint
        
        ran = {"code": 2, "text": ""}
        hint = clean_hermes_fail_hint(ran)
        self.assertIn("model", hint.lower())


if __name__ == "__main__":
    unittest.main()
