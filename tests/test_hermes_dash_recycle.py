"""Hermes dash recycles when target home ≠ live (Cos orphan)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class HermesDashRecycleTests(unittest.TestCase):
    def test_markers(self):
        src = (Path(__file__).resolve().parent.parent / "openbot" / "launch.py").read_text(encoding="utf-8")
        self.assertIn("Stale /root/.hermes Cos dash", src)
        self.assertIn("_should_reuse_dash", src)
        self.assertNotIn(
            "if not _hermes_dash_home:\n            _hermes_dash_home = target\n            return _dash_ok(target)",
            src,
        )
        proxy = (Path(__file__).resolve().parent.parent / "openbot" / "engine_proxy.py").read_text(encoding="utf-8")
        self.assertIn("target-home ≠ live", proxy)

    @patch("openbot.launch.time.sleep")
    @patch("openbot.launch.prepare_hermes", return_value={"ok": True})
    @patch("openbot.launch._wait_port", return_value=True)
    @patch("openbot.launch._kill_port")
    @patch("openbot.launch._kill")
    @patch("openbot.launch.detect")
    @patch("openbot.launch._push_wallets")
    @patch("openbot.launch.subprocess.Popen")
    def test_mismatch_kills_and_restarts(
        self, mock_popen, _push, mock_detect, mock_kill, mock_kill_port, _wait, _prep, _sleep
    ):
        import openbot.launch as launch

        mock_detect.return_value = {
            "hermes": {"present": True, "path": "hermes", "install": "", "install_cmd": ""}
        }
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 99
        mock_popen.return_value = proc

        with tempfile.TemporaryDirectory() as raw:
            cos = Path(raw) / "openbot"
            saa = Path(raw) / "saa-homes"
            cos.mkdir()
            saa.mkdir()
            launch._hermes_dash_home = str(cos)
            launch._hermes_dash_proc = MagicMock()

            # Port open until kill_port clears it, then start waits for bind.
            opens = {"n": 0}

            def port_open(*_a, **_k):
                opens["n"] += 1
                # First checks: still open (mismatch path). After kill loops: closed. After Popen wait: open.
                if opens["n"] <= 2:
                    return True
                if opens["n"] <= 6:
                    return False
                return True

            with patch("openbot.launch._port_open", side_effect=port_open):
                with patch("openbot.launch.resolve_ceo_hermes_home", return_value=str(saa)):
                    result = launch.start_hermes_dashboard(str(saa), project_id="saa-homes")

        mock_kill.assert_called()
        mock_popen.assert_called()
        self.assertTrue(result.get("ok"))
        self.assertEqual(Path(launch._hermes_dash_home).resolve(), saa.resolve())


if __name__ == "__main__":
    unittest.main()
