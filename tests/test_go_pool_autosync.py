"""Auto-sync OPENCODE_GO_API_KEYS on boot / gateway_start / supervise."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class GoPoolAutosyncTests(unittest.TestCase):
    def test_markers(self):
        hermes = (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8")
        launch = (ROOT / "openbot" / "launch.py").read_text(encoding="utf-8")
        # gateway_start syncs before already-running early return
        start = hermes.find("def gateway_start")
        early = hermes.find("Gateway already running", start)
        sync_at = hermes.find("sync_opencode_go_pool_env", start)
        self.assertGreater(sync_at, 0)
        self.assertLess(sync_at, early)
        self.assertIn("sync_opencode_go_pool_env(home=home)", hermes)
        self.assertIn("sync_opencode_go_pool_env(home=ceo_home)", launch)
        self.assertIn("go_pool_synced", launch)
        ens = launch.find("def ensure_supervised_gateway")
        ens_sync = launch.find("sync_opencode_go_pool_env", ens)
        ens_running = launch.find('"running": True', ens)
        self.assertLess(ens_sync, ens_running)

    @patch("openbot.hermes.gateway_status", return_value={"running": True, "ok": True})
    @patch("openbot.hermes.which", return_value="/usr/bin/hermes")
    @patch("openbot.keyring.sync_opencode_go_pool_env", return_value=["k1", "k2"])
    @patch("openbot.keyring.preserve_merge_hermes_env", return_value={"ok": True})
    def test_gateway_start_syncs_when_already_running(self, _preserve, mock_sync, _which, _status):
        from openbot.hermes import gateway_start

        result = gateway_start("/tmp/saa-homes")
        mock_sync.assert_called()
        self.assertTrue(result.get("running"))
        self.assertTrue(result.get("go_pool_synced"))
        self.assertFalse(result.get("started"))

    @patch("openbot.hermes.gateway_status", return_value={"running": True, "ok": True})
    @patch("openbot.launch._ceo_hermes_home", return_value="/data/hermes-homes/saa-homes")
    @patch("openbot.keyring.sync_opencode_go_pool_env", return_value=["k1"])
    @patch("openbot.keyring.preserve_merge_hermes_env", return_value={"ok": True})
    def test_ensure_supervised_syncs_when_running(self, _preserve, mock_sync, _home, _status):
        from openbot.launch import ensure_supervised_gateway

        row = ensure_supervised_gateway("saa-homes")
        mock_sync.assert_called()
        kwargs = mock_sync.call_args.kwargs
        self.assertEqual(kwargs.get("home"), "/data/hermes-homes/saa-homes")
        self.assertTrue(row.get("go_pool_synced"))


if __name__ == "__main__":
    unittest.main()
