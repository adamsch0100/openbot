"""Kill stale /root/.hermes dash when aiming SAA (Cos orphan)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parent.parent


class DashRootOrphanTests(unittest.TestCase):
    def test_markers(self):
        src = (ROOT / "openbot" / "launch.py").read_text(encoding="utf-8")
        self.assertIn("def _live_dash_home", src)
        self.assertIn("def _should_reuse_dash", src)
        self.assertIn("Always fuser-kill :9119 on retarget", src)
        cw = (ROOT / "openbot" / "cronwatch.py").read_text(encoding="utf-8")
        self.assertIn('{title} failed — open Results.', cw)
        self.assertNotIn("needs a look", cw)

    def test_should_not_reuse_root_when_aiming_saa(self):
        import openbot.launch as launch

        with patch.object(launch, "_port_open", return_value=True):
            with patch.object(launch, "_live_dash_home", return_value="/root/.hermes"):
                with patch.object(launch, "hermes_home", return_value=Path("/root/.hermes")):
                    launch._hermes_dash_home = "/data/hermes-homes/saa-homes"
                    launch._hermes_dash_proc = MagicMock(poll=MagicMock(return_value=None))
                    self.assertFalse(launch._should_reuse_dash("/data/hermes-homes/saa-homes"))

    def test_reuse_when_live_matches(self):
        import openbot.launch as launch

        saa = "/data/hermes-homes/saa-homes"
        with patch.object(launch, "_port_open", return_value=True):
            with patch.object(launch, "_live_dash_home", return_value=saa):
                with patch.object(launch, "hermes_home", return_value=Path("/root/.hermes")):
                    launch._hermes_dash_home = saa
                    launch._hermes_dash_proc = MagicMock(poll=MagicMock(return_value=None))
                    self.assertTrue(launch._should_reuse_dash(saa))


if __name__ == "__main__":
    unittest.main()
