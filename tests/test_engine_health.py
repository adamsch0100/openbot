"""Engine health chip — honest Steward status."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class EngineHealthTests(unittest.TestCase):
    def test_markers(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("loadCeoEngineHealth", js)
        self.assertIn("ceoEngineHealth", js)
        self.assertIn("/api/engines/health", js)
        self.assertIn("Accept only", js)
        self.assertIn("ceoHealthRestartGw", js)
        self.assertIn("Next:", js)
        src = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn("/api/engines/health", src)

    def test_dockerfile_pins(self):
        from openbot.engine_health import dockerfile_pins

        pins = dockerfile_pins(ROOT)
        self.assertTrue(pins.get("hermes_pin"))
        self.assertTrue(pins.get("opencode_pin"))

    def test_health_shape(self):
        from openbot import engine_health as eh

        with patch.object(eh, "detect", return_value={
            "hermes": {"present": True, "path": "hermes", "install": ""},
            "opencode": {"present": True, "path": "opencode", "install": ""},
        }):
            with patch.object(eh, "_run_version", side_effect=lambda b: "0.21.1" if b == "hermes" else "1.18.30"):
                with patch.object(eh, "hermes_dash_status", return_value={"running": True, "home": "/data/hermes-homes/saa-homes"}):
                    with patch.object(eh, "opencode_web_status", return_value={"running": True, "folder": "/data/workspaces/saa-homes"}):
                        with patch.object(eh, "_port_open", return_value=True):
                            with patch.object(eh, "_live_dash_home", return_value="/data/hermes-homes/saa-homes"):
                                with patch.object(eh, "resolve_ceo_hermes_home", return_value="/data/hermes-homes/saa-homes"):
                                    with patch("openbot.org.project_tools", return_value={
                                        "hermes_home": "/data/hermes-homes/saa-homes",
                                        "mcp_github": True,
                                        "authorize_railway": False,
                                        "authorize_site": True,
                                    }):
                                        with patch("openbot.hermes.gateway_status", return_value={"running": True, "ok": True}):
                                            row = eh.engine_health("saa-homes")
        self.assertTrue(row["hermes"]["dash_home_ok"])
        self.assertTrue(row["hermes"]["gateway_running"])
        self.assertTrue(row["wire"]["github"])
        self.assertIn("Accept-gated", row["steward"]["policy"])
        self.assertEqual(row.get("next"), [])
        self.assertIsNone(row.get("action"))



    def test_gateway_down_next_step(self):
        from openbot import engine_health as eh

        with patch.object(eh, "detect", return_value={
            "hermes": {"present": True, "path": "hermes", "install": ""},
            "opencode": {"present": True, "path": "opencode", "install": ""},
        }):
            with patch.object(eh, "_run_version", return_value="0.21.1"):
                with patch.object(eh, "hermes_dash_status", return_value={"running": True, "home": "/data/hermes-homes/saa-homes"}):
                    with patch.object(eh, "opencode_web_status", return_value={"running": False, "folder": ""}):
                        with patch.object(eh, "_port_open", return_value=True):
                            with patch.object(eh, "_live_dash_home", return_value="/data/hermes-homes/saa-homes"):
                                with patch.object(eh, "resolve_ceo_hermes_home", return_value="/data/hermes-homes/saa-homes"):
                                    with patch("openbot.org.project_tools", return_value={"hermes_home": "/data/hermes-homes/saa-homes"}):
                                        with patch("openbot.hermes.gateway_status", return_value={"running": False, "ok": False}):
                                            row = eh.engine_health("saa-homes")
        self.assertFalse(row["ok"])
        self.assertTrue(any("gateway" in w.lower() for w in row["warn"]))
        self.assertTrue(row["next"])
        self.assertEqual(row["action"], "restart_gateway")


if __name__ == "__main__":
    unittest.main()
