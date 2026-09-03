"""Product-ready checks. Status stays on files. Live HTTP runs when the board is up."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = "http://127.0.0.1:8787"


def _board_up() -> bool:
    try:
        with urllib.request.urlopen(BOARD + "/api/health", timeout=2) as res:
            return res.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class ReadyTests(unittest.TestCase):
    def test_cos_status_is_staff_not_vault(self):
        from openbot.router import handle

        job = handle("What is going on?")
        self.assertEqual(job.get("preset"), "cos")
        self.assertEqual(job.get("engine"), "board")
        self.assertTrue(job.get("talk"))
        text = job.get("text") or ""
        self.assertIn("openbot:", text)
        self.assertNotIn("secrets.local.json", text)
        self.assertNotIn("## Vault", job.get("index") or "")

    def test_ceo_status_reads_project_index(self):
        from openbot.router import handle

        job = handle("What is going on?", project_id="openbot")
        self.assertEqual(job.get("preset"), "cos")
        self.assertIn("Ticket 1", job.get("text") or "")

    def test_board_swallows_client_abort(self):
        src = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn("class BoardServer", src)
        self.assertIn("ConnectionAbortedError", src)
        self.assertIn("class BoardServer(ThreadingHTTPServer)", src)

    def test_credit_and_assets(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn("Not affiliated with, sponsored by, or endorsed by those projects.", html)
        self.assertIn("app.js?v=52", html)
        self.assertIn("refreshThreadTail", js)
        self.assertIn("data-lane=\"all\"", html)
        self.assertIn("function startReply", js)
        self.assertIn("function applyLaneFilter", js)
        self.assertIn("id=\"replyChip\"", html)
        self.assertIn("id=\"msgMenu\"", html)
        self.assertIn("Site logins", html)
        self.assertIn("org-inbox-empty", js)
        self.assertIn("Chief of Staff", html)
        self.assertIn("data-preset=\"builder\"", html)
        self.assertIn("loadOrgTree", js)
        self.assertIn("Add CEO", js)
        self.assertIn("Type", js)
        self.assertIn("Delete CEO", js)
        self.assertIn("fillCeoPanel", js)
        self.assertIn("setRoute", js)
        self.assertIn("laneStatus", html)
        self.assertIn("Brief", html)
        self.assertNotIn('"catalog": public_catalog()', server)
        self.assertIn("ingest_cron: bool = False", server)
        node = shutil.which("node")
        if node:
            checked = subprocess.run([node, "--check", str(ROOT / "web" / "app.js")], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)


class LiveBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = _board_up()

    def test_health_org_engines(self):
        if not self.live:
            self.skipTest("board not listening")
        with urllib.request.urlopen(BOARD + "/api/health", timeout=5) as res:
            health = json.loads(res.read().decode("utf-8"))
        self.assertTrue(health.get("ok"))
        self.assertTrue(health["engines"]["hermes"]["present"])
        self.assertTrue(health["engines"]["opencode"]["present"])
        with urllib.request.urlopen(BOARD + "/api/org", timeout=8) as res:
            org = json.loads(res.read().decode("utf-8"))
        self.assertEqual(org.get("role"), "cos")
        self.assertEqual(org.get("hermes_home"), "")
        self.assertTrue(
            "# Chief of Staff" in (org.get("staff") or "") or "# Staff" in (org.get("staff") or "")
        )
        homes = {row["id"]: bool((row.get("tools") or {}).get("hermes_home")) for row in org["projects"]}
        self.assertTrue(homes.get("openbot"))
        self.assertTrue(homes.get("saa-homes"))
        self.assertTrue(homes.get("listlogic"))
        self.assertTrue(homes.get("nadia"))
        saa = next(row for row in org["projects"] if row["id"] == "saa-homes")
        self.assertTrue(saa.get("folder"))

    def test_chat_stream_status(self):
        if not self.live:
            self.skipTest("board not listening")
        req = urllib.request.Request(
            BOARD + "/api/chat/stream",
            data=json.dumps({"message": "What is going on?"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            ctype = (res.headers.get("Content-Type") or "").lower()
            body = res.read().decode("utf-8", errors="replace")
        self.assertIn("event-stream", ctype)
        self.assertIn("event: start", body)
        self.assertIn("event: done", body)
        self.assertIn("openbot:", body)

    def test_engine_ports(self):
        if not self.live:
            self.skipTest("board not listening")
        with urllib.request.urlopen(BOARD + "/api/engines/opencode/web", timeout=5) as res:
            oc = json.loads(res.read().decode("utf-8"))
        with urllib.request.urlopen(BOARD + "/api/engines/hermes/dashboard", timeout=5) as res:
            hermes = json.loads(res.read().decode("utf-8"))
        self.assertTrue(oc.get("running") or oc.get("url"))
        self.assertTrue(hermes.get("running") or hermes.get("url"))


if __name__ == "__main__":
    unittest.main()
