"""Restart UI: force-clear stale gateway state (no SSH)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestForceStaleClear(unittest.TestCase):
    def test_force_clears_live_looking_pid(self):
        from openbot.hermes import clear_stale_gateway_state

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-homes" / "saa-homes"
            home.mkdir(parents=True)
            (home / "gateway_state.json").write_text(
                '{"gateway_state":"running","pid":4242}', encoding="utf-8"
            )
            (home / "gateway.sock").write_text("x", encoding="utf-8")
            with patch("openbot.hermes._pid_alive", return_value=True):
                kept = clear_stale_gateway_state(home, force=False)
                forced = clear_stale_gateway_state(home, force=True)
            self.assertEqual(kept["count"], 0)
            self.assertGreaterEqual(forced["count"], 1)
            self.assertTrue(forced.get("forced"))
            self.assertFalse((home / "gateway.sock").exists())

    def test_files_present_auto_force_when_status_down(self):
        from openbot.hermes import gateway_start

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-homes" / "saa-homes"
            home.mkdir(parents=True)
            (home / "gateway_state.json").write_text(
                '{"gateway_state":"running","pid":4242}', encoding="utf-8"
            )
            (home / "gateway.sock").write_text("x", encoding="utf-8")
            with patch("openbot.hermes.which", return_value="/usr/local/bin/hermes"):
                with patch("openbot.hermes._in_container", return_value=False):
                    with patch("openbot.hermes.gateway_status") as mock_status:
                        mock_status.side_effect = [
                            {"running": False, "text": "Gateway is not running"},
                            {"running": True},
                        ]
                        with patch("openbot.hermes._pid_alive", return_value=True):
                            with patch("openbot.hermes._popen") as mock_popen:
                                mock_proc = MagicMock()
                                mock_proc.pid = 99
                                mock_popen.return_value = mock_proc
                                result = gateway_start(home, wait=False)
            self.assertTrue(result["ok"])
            self.assertTrue(result.get("cleared_stale_forced") or result.get("cleared_stale"))
            self.assertFalse((home / "gateway.sock").exists())

    @patch("openbot.hermes.gateway_stop", return_value={"ok": True})
    @patch("openbot.hermes._in_container", return_value=False)
    @patch("openbot.hermes.which", return_value="/usr/local/bin/hermes")
    @patch("openbot.hermes.gateway_status")
    @patch("openbot.hermes._popen")
    def test_force_restart_stops_then_starts(
        self, mock_popen, mock_status, _which, _box, mock_stop
    ):
        from openbot.hermes import gateway_start

        mock_status.side_effect = [
            {"running": True, "text": "Gateway is running"},
            {"running": True},
        ]
        mock_proc = MagicMock()
        mock_proc.pid = 77
        mock_popen.return_value = mock_proc
        result = gateway_start("/tmp/saa", wait=False, force=True)
        self.assertTrue(result.get("forced"))
        mock_stop.assert_called()
        mock_popen.assert_called()


class TestGatewayStartApiMarkers(unittest.TestCase):
    def test_server_passes_force_and_resolves_home(self):
        root = Path(__file__).resolve().parent.parent
        src = (root / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn('force = bool(data.get("force", False))', src)
        self.assertIn("resolve_ceo_hermes_home", src)
        self.assertEqual(src.count('if path == "/api/hermes/gateway/start":'), 1)
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("force: true", js)


if __name__ == "__main__":
    unittest.main()
