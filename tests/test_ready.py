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
        text = job.get("text") or ""
        self.assertTrue(text)
        self.assertIn("OttoBot", text)
        self.assertNotIn("secrets.local.json", text)

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
        self.assertIn("OttoBot uses Hermes Agent (MIT, Nous Research) and OpenCode (MIT, Anomaly).", html)
        self.assertIn("id=\"aboutCredit\"", html)
        self.assertIn("app.js?v=153", html)
        self.assertIn("styles.css?v=153", html)
        self.assertIn("activity-sheet", html)
        self.assertIn("route-hatch", html)
        self.assertIn("id=\"closeActivity\"", html)
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("position: sticky", css)
        self.assertIn("calm phone work lane", css)
        self.assertIn("do not crush Chat/Tools", css)
        self.assertIn("page-wide: vertical scroll only", css)
        self.assertIn("chat-shell.work-open", css)
        self.assertIn("id=\"pulse\"", html)
        self.assertIn("id=\"ceoBrief\"", html)
        self.assertIn("refreshThreadTail", js)
        self.assertIn("data-lane=\"all\"", html)
        self.assertIn("function startReply", js)
        self.assertIn("function applyLaneFilter", js)
        self.assertIn("id=\"replyChip\"", html)
        self.assertIn("id=\"msgMenu\"", html)
        self.assertIn("Site logins", html)
        self.assertIn("id=\"pairCard\"", html)
        self.assertIn("data-need-act", js)
        self.assertIn("function runNeedChoice", js)
        self.assertIn("function needChoices", js)
        self.assertIn("function fillPair", js)
        self.assertIn("function startLiveTick", js)
        self.assertIn("EventSource", js)
        self.assertIn("/api/pair", server)
        self.assertIn("/api/live", server)
        self.assertIn("def need_choices", (ROOT / "openbot" / "router.py").read_text(encoding="utf-8"))
        self.assertIn("def job_choices", (ROOT / "openbot" / "router.py").read_text(encoding="utf-8"))
        self.assertIn("function openSchedule", js)
        self.assertIn("Open schedule", js)
        self.assertIn("function cronIsPromptDump", js)
        self.assertIn("Job ID:", js)
        self.assertIn("folder_live", (ROOT / "openbot" / "org.py").read_text(encoding="utf-8"))
        self.assertIn("project_id: aim.projectId", js)
        self.assertIn("chat?resume=", js)
        self.assertIn("function cronChangedLine", js)
        self.assertIn("cron_report", (ROOT / "openbot" / "cronwatch.py").read_text(encoding="utf-8"))
        self.assertIn("saa-live-overlay.json", (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8"))
        self.assertIn("load_saa_overlay_cache", (ROOT / "openbot" / "org.py").read_text(encoding="utf-8"))
        self.assertIn('os.environ.get("OPENBOT_SUPERVISE_HOMES")', (ROOT / "openbot" / "launch.py").read_text(encoding="utf-8"))
        self.assertIn("id=\"workTabs\"", html)
        self.assertIn("data-work=\"doing\"", html)
        self.assertIn("data-work=\"next\"", html)
        self.assertIn("data-work=\"results\"", html)
        self.assertIn("function cronIsLive", js)
        self.assertIn("Running now on this CEO's Hermes.", js)
        self.assertIn("function rememberWorkFolds", js)
        self.assertIn("activity-sheet", html)
        self.assertIn("Waiting ·", js)
        self.assertIn("parse_hermes_running_job_ids", (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8"))
        self.assertIn("function cronClaimAt", js)
        self.assertIn("function cronClaimFresh", js)
        self.assertIn("function cronIsDueSoon", js)
        self.assertIn("function cronIsFailed", js)
        self.assertIn("function paintEmbedLive", js)
        self.assertIn("function engineStory", js)
        self.assertIn("function hermesScheduleSummary", js)
        self.assertIn("Old gateway stop scars", js)
        self.assertIn("function rowEngineKind", js)
        self.assertIn("receipt-line", js)
        self.assertIn("function redactSecrets", js)
        self.assertIn("Troubleshooting:", js)
        self.assertIn("function jobStoryTitle", js)
        self.assertIn("function cronNextUseful", js)
        self.assertIn("What to do:", js)
        self.assertIn("embed-tools", html)
        self.assertGreaterEqual(html.count('data-work="doing"'), 3)
        self.assertIn("function cronKind", js)
        self.assertIn("CLAIM_FRESH_MS", js)
        self.assertIn("id=\"ocLive\"", html)
        self.assertIn("id=\"hermesLive\"", html)
        self.assertIn("Failed ·", js)
        self.assertIn("function openWork", js)
        self.assertIn("function cronJobIsNoise", js)
        self.assertIn("function paintPulse", js)
        self.assertIn("function receiptLine", js)
        self.assertIn("supervise_ceo_gateways_background", server)
        # overlay_saa_live_background now gated by OPENBOT_SAA_OVERLAY_ENABLED (default OFF)
        self.assertIn("OPENBOT_SAA_OVERLAY_ENABLED", server)
        self.assertIn("from .pair import pair_payload, people_rows", server)
        self.assertTrue((ROOT / "openbot" / "pair.py").is_file())
        self.assertIn("openbot-saa-gateway", server)
        self.assertIn("function stripPacketEcho", js)
        self.assertIn("function formatBotHtml", js)
        self.assertIn("function paintBotText", js)
        self.assertIn("id=\"chatSchedule\"", html)
        self.assertIn("/api/crons", server)
        self.assertIn("/api/crons/run", server)
        self.assertIn("sync_saa_live_crons(home, live=True)", server)
        self.assertNotIn("&refresh=1", js)
        self.assertNotIn('if pid == "saa-homes" and refresh', server)
        self.assertIn("function cronSkipRetry", js)
        self.assertIn("function cronIsGatewayFail", js)
        self.assertIn("Chat is talk. Cron landings live in Results.", js)
        self.assertIn("More due ·", js)
        self.assertIn("diff-fold", js)
        self.assertIn("See change", js)
        self.assertIn("function cronIsStaleFail", js)
        self.assertIn("function isLiveBoard", js)
        self.assertIn("function paintBoardMark", js)
        self.assertIn("function quietStory", js)
        self.assertIn("function gatewayFailClusterHtml", js)
        self.assertIn("Old gateway stop scars", js)
        self.assertIn("Older fails", js)
        self.assertIn('label: "Retry"', js)
        self.assertIn("Fix key", js)
        self.assertIn("RAILWAY_ENVIRONMENT", server)
        self.assertIn("id=\"boardMark\"", html)
        self.assertIn("Chief of Staff", html)
        self.assertIn("data-lane=\"builder\"", html)
        self.assertIn("loadOrgTree", js)
        self.assertIn("Add CEO", js)
        self.assertIn("function canAddCeo", js)
        self.assertIn("can_add_ceo", server)
        self.assertIn("_token_unlocked", server)
        self.assertIn("unlock_tokens.json", server)
        self.assertIn("orgAddCeoSlot", html)
        self.assertIn("settingsAddCeo", html)
        self.assertIn("function paintAddCeoControls", js)
        self.assertIn("function addCeoFormHtml", js)
        self.assertIn("ceoAuthGithub", js)
        self.assertIn("whyIdleLine", js)
        self.assertIn("honestIndexNext", js)
        self.assertIn('id="routeHatch" hidden', html)
        self.assertNotIn("isCollaborator() || (cfg && cfg.hosted)", js)
        self.assertIn("Type", js)
        self.assertIn("Delete CEO", js)
        self.assertIn("fillCeoPanel", js)
        self.assertIn("setRoute", js)
        self.assertIn("laneStatus", html)
        self.assertIn("Brief", html)
        self.assertNotIn('"catalog": public_catalog()', server)
        self.assertIn("ingest_cron: bool = False", server)
        self.assertIn("min-width: 1280px", css)
        self.assertIn("function emptyWorkCopy", js)
        self.assertIn("Create support ticket", html)
        self.assertIn("data-stage=\"tools\"", html)
        self.assertIn("function gatewayOffHtml", js)
        self.assertIn("THINK_OK", js)
        self.assertIn("OPS_OK", js)
        self.assertIn("function humanFailReason", js)
        self.assertIn("function gateLineKind", js)
        self.assertIn("function failClustersHtml", js)
        self.assertIn("Fix key", js)
        self.assertIn("1 failed:", js)
        self.assertIn("Bare Done when idle", js)
        self.assertIn("done-fold", js)
        self.assertIn("function chatCeoProject", js)
        self.assertIn("function restartGateway", js)
        self.assertIn("id=\"chatContext\"", html)
        self.assertIn("id=\"retryHermes\">Restart", html)
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
        ids = {row["id"] for row in org["projects"]}
        self.assertTrue(homes.get("openbot"))
        self.assertTrue(homes.get("saa-homes"))
        self.assertIn("support", ids)
        self.assertNotIn("listlogic", ids)
        self.assertNotIn("nadia", ids)
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
        self.assertIn("openbot:", body.lower())

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
