"""Week 1 glue tests. Stdlib only."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

from openbot.config import DEFAULT_SPEND_CAP_USD, load_config, save_settings, save_work_dir, verify_pin
from openbot.gitutil import diff_against_head, restore_snapshot, snapshot
from openbot.router import classify, resolve_preset
from openbot.store import in_spend_period, spend_summary, write_job, patch_index_line
from openbot.usage import parse_opencode_events
from openbot.server import _parse_index_fields, _search_memory
from openbot.org import patch_scope
from openbot.bus import write_handoff, load_open_handoffs, claim_handoff, create_handoff, handoff_summary
import openbot.config as config_mod
import openbot.store as store_mod


SAMPLE_JSON = """
{"type":"step_start","sessionID":"ses_abc","part":{"id":"prt_1","type":"step-start"}}
{"type":"text","sessionID":"ses_abc","part":{"type":"text","text":"Patched the footer."}}
{"type":"step_finish","sessionID":"ses_abc","part":{"reason":"stop","tokens":{"total":11168,"input":2,"output":34,"cache":{"write":11132,"read":9}},"cost":0.014087}}
{"type":"step_finish","sessionID":"ses_abc","part":{"reason":"stop","tokens":{"input":10,"output":6,"cache":{"read":1}},"cost":0.001}}
not json
"""


class MemoryTests(unittest.TestCase):
    def test_parse_index_fields_extracts_all(self):
        index = """# INDEX

Now: Implementing memory pane
Last: Added turn report card
Next: Write tests
Blocker: —
"""
        fields = _parse_index_fields(index)
        self.assertEqual(fields["now"], "Implementing memory pane")
        self.assertEqual(fields["last"], "Added turn report card")
        self.assertEqual(fields["next"], "Write tests")
        self.assertEqual(fields["blocker"], "—")

    def test_parse_index_fields_handles_empty(self):
        fields = _parse_index_fields("")
        self.assertEqual(fields["now"], "—")
        self.assertEqual(fields["last"], "—")
        self.assertEqual(fields["next"], "—")
        self.assertEqual(fields["blocker"], "—")

    def test_parse_index_fields_handles_missing_blocker(self):
        index = """Now: Working
Last: Done
Next: More"""
        fields = _parse_index_fields(index)
        self.assertEqual(fields["now"], "Working")
        self.assertEqual(fields["blocker"], "—")

    def test_search_memory_empty_query_returns_fields(self):
        with unittest.mock.patch("openbot.server.read_index") as mock_read:
            mock_read.return_value = "Now: Testing\nLast: Done\nNext: More\nBlocker: —"
            with unittest.mock.patch("openbot.server.list_jobs") as mock_jobs:
                mock_jobs.return_value = []
                result = _search_memory("")
                self.assertEqual(result["results"], [])
                self.assertIn("index_fields", result)
                self.assertEqual(result["index_fields"]["now"], "Testing")
                self.assertEqual(result["index_fields"]["last"], "Done")
                self.assertEqual(result["index_fields"]["next"], "More")
                self.assertEqual(result["index_fields"]["blocker"], "—")

    def test_search_memory_finds_in_index(self):
        with unittest.mock.patch("openbot.server.read_index") as mock_read:
            mock_read.return_value = "Now: Memory pane feature\nLast: Testing"
            with unittest.mock.patch("openbot.server.list_jobs") as mock_jobs:
                mock_jobs.return_value = []
                result = _search_memory("memory")
                self.assertGreater(len(result["results"]), 0)
                self.assertEqual(result["results"][0]["type"], "index")

    def test_search_memory_finds_in_jobs(self):
        with unittest.mock.patch("openbot.server.read_index") as mock_read:
            mock_read.return_value = "Now: Working\nLast: Done"
            with unittest.mock.patch("openbot.server.list_jobs") as mock_jobs:
                mock_jobs.return_value = [
                    {
                        "id": "abc123",
                        "text": "Added memory search feature",
                        "engine": "OpenCode",
                        "at": "2026-09-05T10:00:00Z"
                    }
                ]
                result = _search_memory("search")
                job_results = [r for r in result["results"] if r["type"] == "job"]
                self.assertEqual(len(job_results), 1)
                self.assertIn("search", job_results[0]["snippet"].lower())

    def test_patch_index_line_updates_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "INDEX.md"
            index_path.write_text("Now: Old value\nLast: Done\n", encoding="utf-8")
            with unittest.mock.patch("openbot.store.INDEX", index_path):
                patch_index_line("Now", "New value")
                text = index_path.read_text(encoding="utf-8")
                self.assertIn("Now: New value", text)
                self.assertNotIn("Old value", text)


class UsageTests(unittest.TestCase):
    def test_sums_step_finish_and_text(self):
        usage = parse_opencode_events(SAMPLE_JSON)
        self.assertEqual(usage.prompt_tokens, 12)
        self.assertEqual(usage.output_tokens, 40)
        self.assertEqual(usage.cached_tokens, 10)
        self.assertAlmostEqual(usage.usd_estimate, 0.015087)
        self.assertEqual(usage.text, "Patched the footer.")
        self.assertEqual(usage.session_id, "ses_abc")

    def test_empty_raw_stays_zero(self):
        usage = parse_opencode_events("opencode not on PATH")
        self.assertEqual(usage.prompt_tokens, 0)
        self.assertEqual(usage.usd_estimate, 0.0)
        self.assertEqual(usage.text, "")


class RouterClassifyTests(unittest.TestCase):
    def test_status_and_code(self):
        self.assertEqual(classify("What is going on and what is blocked?"), "cos")
        self.assertEqual(classify("Change the code: add a footer"), "builder")
        self.assertEqual(classify("Look at this site https://example.com"), "research")
        self.assertEqual(classify("Every morning ping the board"), "ops")
        self.assertEqual(classify("hello"), "cos")

    def test_requested_preset_wins(self):
        self.assertEqual(resolve_preset("hello", "builder"), "builder")
        self.assertEqual(resolve_preset("hello", None), "cos")
        self.assertEqual(resolve_preset("hello", "nope"), "cos")

    def test_route_plan_chains_and_think(self):
        from openbot.router import route_plan

        self.assertEqual(
            route_plan("Change the code after looking at https://example.com/docs", None),
            ["research", "builder"],
        )
        self.assertEqual(route_plan("think hard about the routing", None), ["think"])
        self.assertEqual(route_plan("hello", "ops"), ["ops"])
        self.assertEqual(route_plan("hello", None), ["cos"])
        from openbot.router import route_for_node

        self.assertEqual(route_for_node("hello", "staff"), ["cos"])
        self.assertEqual(route_for_node("hello", "worker"), ["cos"])
        self.assertEqual(route_for_node("hello", "ceo"), ["cos"])
        self.assertEqual(route_for_node("can you help with ticket 1", "ceo"), ["cos"])
        self.assertEqual(route_for_node("What is going on and what is blocked?", "worker"), ["cos"])
        self.assertEqual(route_for_node("think hard about the routing", "ceo"), ["think"])
        self.assertEqual(route_for_node("Change the code: add a footer", "ceo"), ["builder"])
        from openbot.hermes import HERMES_TIMEOUT
        from openbot.router import PROGRAM, handle, keep_going_for, status_reply

        self.assertGreaterEqual(HERMES_TIMEOUT, 600)
        status_job = handle("what's going on", preset="think")
        self.assertEqual(status_job.get("preset"), "cos")
        self.assertEqual(status_job.get("engine"), "board")
        self.assertTrue(status_job.get("talk"))

        self.assertTrue(PROGRAM.search("Build me a full program and set up 25 tasks"))
        self.assertTrue(PROGRAM.search("always be improving the code"))
        self.assertFalse(PROGRAM.search("hello"))
        index = "Now: ticket 1\nLast: builder\nNext: folder then diff\nBlocker: —\n## Law\nsecret dump"
        hello = status_reply(index, "hello", "openbot")
        self.assertIn("openbot", hello)
        self.assertIn("report to Chief of Staff", hello)
        self.assertNotIn("ticket 1", hello)
        self.assertNotIn("## Law", hello)
        self.assertNotIn("secret dump", hello)
        thanks = status_reply(index, "thanks", "openbot")
        self.assertIn("openbot", thanks)
        self.assertIn("Chief of Staff", thanks)
        self.assertNotIn("ticket 1", thanks)
        status = status_reply(index, "What is going on?")
        self.assertNotIn("how can I help", status)
        self.assertIn("Last: builder", status)
        self.assertFalse(keep_going_for("think", talk=True))
        self.assertTrue(keep_going_for("think", talk=False))
        self.assertFalse(keep_going_for("cos"))
        self.assertTrue(keep_going_for("builder"))
        self.assertFalse(keep_going_for("builder", ok=False))
        self.assertTrue(keep_going_for("think", talk=True, login_wall=True))
        from openbot.router import _index_last

        self.assertEqual(_index_last("Patched the footer.\nMore."), "Patched the footer. More.")
        self.assertTrue(_index_last("boom", failed=True).startswith("failed:"))
        self.assertNotIn("abc123", _index_last("Patched the footer."))


class SpendTests(unittest.TestCase):
    def test_period_and_sum(self):
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
        self.assertTrue(in_spend_period("2026-08-31T12:00:00Z", "day", now))
        self.assertFalse(in_spend_period("2026-08-20T12:00:00Z", "week", now))
        old_jobs = store_mod.JOBS
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.JOBS = Path(tmp)
            write_job({"id": "aaa111", "at": "2026-08-31T10:00:00Z", "usd_estimate": 0.04, "engine": "board"})
            write_job({"id": "bbb222", "at": "2026-08-31T11:00:00Z", "usd_estimate": 0.01, "rejected": True, "engine": "OpenCode"})
            write_job({"id": "ccc333", "at": "2026-01-01T00:00:00Z", "usd_estimate": 9.0, "engine": "Hermes Agent"})
            write_job({"id": "ddd444", "at": "2026-08-31T12:00:00Z", "usd_estimate": 0.10, "engine": "OpenCode"})
            write_job({"id": "eee555", "at": "2026-08-31T13:00:00Z", "usd_estimate": 0.02, "engine": "Hermes Agent"})
            summary = spend_summary(5.0, "week", now, go_usage={})
        store_mod.JOBS = old_jobs
        self.assertAlmostEqual(summary["spent_usd"], 0.12)
        self.assertAlmostEqual(summary["spent_payg_usd"], 0.12)
        self.assertAlmostEqual(summary["spent_included_usd"], 0.04)
        self.assertAlmostEqual(summary["cap_remaining"], 4.88)
        self.assertAlmostEqual(summary["by_engine"]["chat"], 0.04)
        self.assertAlmostEqual(summary["by_engine"]["opencode"], 0.10)
        self.assertAlmostEqual(summary["by_engine"]["hermes"], 0.02)
        self.assertFalse(summary["enforced"])
        self.assertEqual(summary["policy"]["bind"], "payg")

    def test_go_quota_keeps_opencode_off_payg(self):
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
        old_jobs = store_mod.JOBS
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.JOBS = Path(tmp)
            write_job({"id": "ddd444", "at": "2026-08-31T12:00:00Z", "usd_estimate": 0.10, "engine": "OpenCode"})
            write_job({"id": "eee555", "at": "2026-08-31T13:00:00Z", "usd_estimate": 0.02, "engine": "Hermes Agent"})
            go = {"http_status": 200, "usage": {"weekly": {"status": "ok", "percent": 12, "resetsAt": "2026-09-07T00:00:00Z"}}}
            summary = spend_summary(5.0, "week", now, go_usage=go)
        store_mod.JOBS = old_jobs
        self.assertAlmostEqual(summary["spent_payg_usd"], 0.02)
        self.assertAlmostEqual(summary["spent_included_usd"], 0.10)
        self.assertTrue(summary["go"]["present"])
        self.assertFalse(summary["go"]["exhausted"])

    def test_hard_cap_blocks_paid_work(self):
        from openbot.spend import gate

        blocked = gate("builder", {"policy": {"bind": "payg", "mode": "hard", "allow_zen_fallback": True}, "cap_remaining": 0, "go": {}})
        self.assertFalse(blocked["allow"])
        allowed = gate("cos", {"policy": {"mode": "hard"}, "cap_remaining": 0, "go": {}})
        self.assertTrue(allowed["allow"])
        warn = gate("builder", {"policy": {"bind": "payg", "mode": "warn", "allow_zen_fallback": True}, "cap_remaining": 0, "go": {}})
        self.assertTrue(warn["allow"])


class GitUtilTests(unittest.TestCase):
    def test_snapshot_accept_path_and_reject_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "openbot@local"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "OpenBot"], cwd=root, check=True, capture_output=True)
            (root / "app.txt").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.txt"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
            before = snapshot(str(root))
            (root / "app.txt").write_text("two\n", encoding="utf-8")
            (root / "new.txt").write_text("fresh\n", encoding="utf-8")
            after = diff_against_head(str(root))
            self.assertIn("two", after)
            ok, _ = restore_snapshot(str(root), before)
            self.assertTrue(ok)
            self.assertEqual((root / "app.txt").read_text(encoding="utf-8"), "one\n")
            self.assertFalse((root / "new.txt").exists())


class ConfigTests(unittest.TestCase):
    def test_save_work_dir_writes_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            env_path = Path(tmp) / ".env"
            old_path = config_mod.ENV_PATH
            old_val = os.environ.pop("OPENBOT_WORK_DIR", None)
            config_mod.ENV_PATH = env_path
            try:
                cfg = save_work_dir(str(folder))
                self.assertTrue(cfg["first_run_done"])
                self.assertTrue(cfg["work_dir_ok"])
                self.assertEqual(load_config()["spend_cap_usd"], DEFAULT_SPEND_CAP_USD)
                self.assertIn("OPENBOT_WORK_DIR=", env_path.read_text(encoding="utf-8"))
            finally:
                config_mod.ENV_PATH = old_path
                if old_val is None:
                    os.environ.pop("OPENBOT_WORK_DIR", None)
                else:
                    os.environ["OPENBOT_WORK_DIR"] = old_val

    def test_listen_addr_uses_railway_port(self):
        from openbot.server import listen_addr

        old = {key: os.environ.get(key) for key in ("PORT", "OPENBOT_PORT", "OPENBOT_HOST")}
        try:
            os.environ.pop("PORT", None)
            os.environ.pop("OPENBOT_PORT", None)
            os.environ.pop("OPENBOT_HOST", None)
            self.assertEqual(listen_addr(), ("127.0.0.1", 8787))
            os.environ["PORT"] = "8080"
            self.assertEqual(listen_addr(), ("0.0.0.0", 8080))
            os.environ["OPENBOT_HOST"] = "127.0.0.1"
            self.assertEqual(listen_addr(), ("127.0.0.1", 8080))
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_operator_profile_is_hashed_and_not_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "openbot.local.json"
            old_path = config_mod.SETTINGS_PATH
            config_mod.SETTINGS_PATH = settings_path
            try:
                cfg = save_settings({
                    "operator_name": "Ada",
                    "pin": "1234",
                    "license_key": "lic-secret",
                })
                self.assertEqual(cfg["operator_name"], "Ada")
                self.assertTrue(cfg["has_pin"])
                self.assertTrue(cfg["has_license"])
                self.assertNotIn("pin_hash", cfg)
                self.assertNotIn("pin_salt", cfg)
                self.assertNotIn("license_key", cfg)
                raw = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(raw["operator_name"], "Ada")
                self.assertNotEqual(raw["pin_hash"], "1234")
                self.assertEqual(raw["license_key"], "lic-secret")
                self.assertTrue(verify_pin("1234"))
                self.assertFalse(verify_pin("0000"))
                public = load_config()
                self.assertNotIn("license_key", public)
                self.assertNotIn("pin_hash", public)
            finally:
                config_mod.SETTINGS_PATH = old_path


class FileMemoryTests(unittest.TestCase):
    def test_brain_names_are_allowlisted(self):
        from openbot.store import write_brain

        with self.assertRaises(ValueError):
            write_brain("../secrets", "nope")

    def test_thread_is_ui_only_and_clipped_to_preset(self):
        from openbot import threadstore

        old = threadstore.THREADS
        with tempfile.TemporaryDirectory() as tmp:
            threadstore.THREADS = Path(tmp)
            threadstore.append_turn("cos", {"role": "user", "text": "hi"})
            self.assertEqual(len(threadstore.read_thread("cos")), 1)
            self.assertEqual(threadstore.read_thread("builder"), [])
        with self.assertRaises(ValueError):
            threadstore.write_thread("not-a-bot", [])
        threadstore.THREADS = old


class BrandMarkTests(unittest.TestCase):
    def test_lockup_is_on_the_board(self):
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("OPENBOT", html)
        self.assertIn("LOCAL ORG.", html)
        self.assertIn('data-stage="chat"', html)
        self.assertIn('data-stage="opencode"', html)
        self.assertIn('data-stage="hermes"', html)
        self.assertIn("Settings", html)
        self.assertIn("id=\"openSettings\"", html)
        self.assertIn("id=\"openSpend\"", html)
        self.assertIn("id=\"profileDock\"", html)
        self.assertIn('id="settings"', html)
        self.assertIn(">You</button>", html)
        self.assertIn(">OpenCode</button>", html)
        self.assertIn(">Hermes</button>", html)
        self.assertIn("Models", html)
        self.assertIn("id=\"panel-you\"", html)
        self.assertIn("id=\"panel-keys\"", html)
        self.assertIn("id=\"panel-import\"", html)
        self.assertIn("id=\"panel-git\"", html)
        self.assertIn("id=\"panel-usage\"", html)
        self.assertIn("id=\"unlockGate\"", html)
        self.assertIn("id=\"keyProvider\"", html)
        self.assertIn("Chief of Staff", html)
        self.assertIn("id=\"orgTree\"", html)
        self.assertIn("id=\"nodeMenu\"", html)
        self.assertIn("id=\"scheduleList\"", html)
        self.assertNotIn("id=\"addProject\"", html)
        self.assertNotIn('id="settingsMenu"', html)
        self.assertNotIn("id=\"railDock\"", html)
        self.assertNotIn("id=\"ceoTools\"", html)
        self.assertIn("This CEO", html)
        self.assertIn("id=\"seatList\"", html)
        self.assertIn("Default folder", html)
        self.assertIn("wizardProvider", html)
        self.assertNotIn('id="engines"', html)
        self.assertNotIn("toggleAdvanced", html)
        self.assertNotIn("Open Hermes console", html)
        self.assertNotIn("openHermesTui", html)
        self.assertIn('id="hermesHint"', html)
        self.assertIn('id="profileAccount"', html)
        self.assertIn('id="rankCite"', html)
        self.assertIn("arena.ai", html)
        self.assertIn("id=\"assignmentMap\"", html)
        self.assertIn("OpenRouter", html)
        self.assertIn("everyday talk", html.lower())
        self.assertIn("Nous Portal is the standard Hermes subscription", html)
        self.assertIn("https://portal.nousresearch.com/r/adam-schwartz", html)
        self.assertIn("id=\"wizardKeyHint\"", html)
        self.assertIn("id=\"keyProviderHint\"", html)
        self.assertIn("not OpenRouter rankings", html)
        self.assertNotIn("Retry dashboard", html)
        self.assertNotIn("native Windows dashboard", html)
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("sortSeatModels", js)
        self.assertIn("renderAssignmentMap", js)
        self.assertIn("Board — free brief talk", js)
        self.assertIn("chatModelLabel", js)
        self.assertIn("recommended_chat", js)
        self.assertIn('$("form").addEventListener("submit"', js)
        self.assertIn("/api/chat/stream", js)
        self.assertIn("Keep going", js)
        self.assertIn("renderTalk", js)
        self.assertIn("Open Hermes", js)
        self.assertNotIn("ceoSkills", js)
        self.assertIn("hermesSkills", html)
        self.assertIn("defaultModelOptionLabel", js)
        self.assertIn("keyringProviderRank", js)
        self.assertIn("providerHintHtml", js)
        self.assertIn("first in keyring", js)
        self.assertIn("currentAim", js)
        self.assertIn("hermes_home", js)
        self.assertIn("org.staff", js)
        self.assertIn("Chief of Staff brief", js)
        self.assertIn("bubble-work", js)
        self.assertIn("startOpenCode()", js)
        self.assertIn("startHermes()", js)
        self.assertIn("syncHermesHint", js)
        self.assertIn("add-project", js)
        self.assertIn("fillImport", js)
        self.assertIn("ceoAccount", js)
        self.assertIn("saveStaffProfile", js)
        self.assertIn("profileAccount", js)
        self.assertIn("menuStaffSeatList", js)
        self.assertIn("data-fallback-up", js)
        self.assertIn("data-save-label", js)
        self.assertIn("/api/hermes/import/backup", js)
        self.assertIn("saveCeoTools", js)
        self.assertIn("waitForUnlock", js)
        self.assertIn("id=\"sendBtn\"", html)
        self.assertIn("id=\"workHint\"", html)
        self.assertIn("thinkingBubble", js)
        self.assertNotIn("id=\"chatModel\"", html)
        self.assertIn("function setRoute", js)
        self.assertNotIn("id=\"stopBtn\"", html)
        self.assertNotIn("id=\"ceoTools\"", html)
        self.assertNotIn("CREATE_NEW_CONSOLE", (root / "openbot" / "launch.py").read_text(encoding="utf-8"))
        server = (root / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn("rename_project", server)
        self.assertIn("rename_account", server)
        self.assertIn("set_project_folder", server)
        self.assertIn("write_worker_brain", server)
        self.assertIn("ingest_cron_runs", server)
        self.assertIn("/api/chat/stream", server)
        self.assertIn("live_stop", server)
        self.assertIn("patch_project_tools", server)
        self.assertIn("/api/unlock", server)
        self.assertIn("operator_name", server)
        self.assertIn("/api/hermes/import/backup", server)


class CatalogTests(unittest.TestCase):
    def test_seat_capabilities(self):
        from openbot.models import allowed_for_seat, public_catalog, validate_seats
        from openbot.pickers import parse_hermes_catalog

        self.assertTrue(allowed_for_seat("chat", ""))
        self.assertTrue(allowed_for_seat("chat", "openrouter/deepseek/deepseek-v4-flash-0731"))
        self.assertFalse(allowed_for_seat("chat", "nope"))
        self.assertTrue(allowed_for_seat("think", "opencode/gpt-5.4-nano"))
        self.assertTrue(allowed_for_seat("think", "opencode/gpt-5.4"))
        self.assertTrue(allowed_for_seat("think", "openrouter/anthropic/claude-sonnet-4.6"))
        self.assertTrue(allowed_for_seat("code", ""))
        validate_seats(
            {
                "think": {"model": ""},
                "code": {"model": ""},
                "research": {"model": ""},
                "ops": {"model": ""},
            }
        )
        validate_seats({"think": {"model": "opencode/gpt-5.4-nano"}})
        catalog = public_catalog()
        self.assertTrue(catalog["models"])
        self.assertIn("guides", catalog)
        self.assertIn("arena.ai", catalog["ranking_citation"])
        chat = next(seat for seat in catalog["seats"] if seat["id"] == "chat")
        self.assertFalse(chat["locked"])
        self.assertEqual(chat["engine"], "Hermes Agent")
        from openbot.models import recommended_chat_id

        self.assertEqual(
            recommended_chat_id(
                [
                    {"id": "openrouter/openai/gpt-5", "label": "GPT-5", "in_usd": 2, "out_usd": 8, "connected": True},
                    {"id": "openrouter/deepseek/deepseek-v4-flash-0731", "label": "DeepSeek V4 Flash", "in_usd": 0.07, "out_usd": 0.28, "connected": True},
                ]
            ),
            "openrouter/deepseek/deepseek-v4-flash-0731",
        )
        self.assertEqual(
            recommended_chat_id(
                [
                    {"id": "opencode/deepseek-v4-flash", "label": "DeepSeek V4 Flash", "in_usd": 0.05, "out_usd": 0.1, "connected": True},
                    {"id": "openrouter/deepseek/deepseek-v4-flash-0731", "label": "DeepSeek V4 Flash", "in_usd": 0.07, "out_usd": 0.28, "connected": True},
                ]
            ),
            "opencode/deepseek-v4-flash",
        )
        from openbot.models import cheap_chat_for_provider
        from openbot.router import wallet_empty

        self.assertEqual(
            cheap_chat_for_provider(
                "openrouter",
                [
                    {"id": "opencode/deepseek-v4-flash", "label": "DeepSeek V4 Flash", "provider": "opencode", "connected": True},
                    {"id": "openrouter/deepseek/deepseek-v4-flash-0731", "label": "DeepSeek V4 Flash", "provider": "openrouter", "connected": True},
                ],
            ),
            "openrouter/deepseek/deepseek-v4-flash-0731",
        )
        self.assertTrue(wallet_empty("HTTP 401: Insufficient balance. Manage your billing here: https://opencode.ai/workspace/x/billing"))
        self.assertFalse(wallet_empty("Hello."))
        from openbot.router import wallet_empty_reply

        self.assertNotIn("opencode.ai/", wallet_empty_reply())
        self.assertNotIn("http://", wallet_empty_reply().lower())
        self.assertEqual(
            recommended_chat_id(
                [
                    {"id": "opencode/claude-opus-4.6", "label": "Opus 4.6", "in_usd": 0, "out_usd": 0, "connected": True},
                    {"id": "opencode/gpt-5.4-nano", "label": "GPT 5.4 Nano", "in_usd": 0, "out_usd": 0, "connected": True},
                ]
            ),
            "opencode/gpt-5.4-nano",
        )
        self.assertEqual(
            recommended_chat_id(
                [
                    {"id": "openrouter/deepseek/deepseek-v4-flash-0731", "label": "DeepSeek V4 Flash", "in_usd": 0.07, "out_usd": 0.28, "connected": True},
                    {"id": "nous/hermes-4-70b", "label": "Hermes 4 70B", "in_usd": 0, "out_usd": 0, "connected": True},
                    {"id": "nous/hermes-4-405b", "label": "Hermes 4 405B", "in_usd": 0, "out_usd": 0, "connected": True},
                    {"id": "nous/deepseek/deepseek-v4-flash", "label": "DeepSeek V4 Flash", "in_usd": 0.05, "out_usd": 0.1, "connected": True},
                ],
                provider="nous",
            ),
            "nous/hermes-4-70b",
        )
        think = next(seat for seat in catalog["seats"] if seat["id"] == "think")
        self.assertEqual(think["need"], [])
        self.assertFalse(any(":batch" in row["id"] for row in catalog["models"]))
        ids = {row["id"] for row in catalog["models"]}
        self.assertIn("", ids)
        parsed = parse_hermes_catalog(
            {
                "providers": {
                    "openrouter": {
                        "models": [
                            {"id": "z-ai/glm-5.2", "description": "default", "default": True},
                            {"id": "deepseek/deepseek-v4-flash-0731", "description": ""},
                            {"id": "openai/gpt-5:batch"},
                        ]
                    },
                    "nous": {"models": [{"id": "hermes-4-70b"}]},
                    "opencode-zen": {"models": [{"id": "gpt-5.4"}]},
                }
            }
        )
        parsed_ids = {row["id"] for row in parsed}
        self.assertIn("openrouter/z-ai/glm-5.2", parsed_ids)
        self.assertIn("openrouter/deepseek/deepseek-v4-flash-0731", parsed_ids)
        self.assertNotIn("openrouter/openai/gpt-5:batch", parsed_ids)
        self.assertIn("nous/hermes-4-70b", parsed_ids)
        self.assertFalse(any(row["id"].endswith("/gpt-5.4") and row["provider"] == "opencode" for row in parsed))
        glm = next(row for row in parsed if row["id"] == "openrouter/z-ai/glm-5.2")
        self.assertEqual(glm["badge"], "default")
        self.assertIn("OpenCode", glm["engines"])
        live_only = parse_hermes_catalog(
            {"providers": {"openrouter": {"models": [{"id": "z-ai/glm-5.2"}, {"id": "x-ai/grok-4.6"}]}}},
            None,
            {"z-ai/glm-5.2"},
        )
        self.assertEqual([row["or_id"] for row in live_only], ["z-ai/glm-5.2"])
        keyed = parse_hermes_catalog(
            {
                "providers": {
                    "openrouter": {"models": [{"id": "z-ai/glm-5.2"}]},
                    "nous": {"models": [{"id": "hermes-4-70b"}]},
                }
            },
            {"opencode"},
        )
        self.assertEqual(keyed, [])
        keyed_nous = parse_hermes_catalog(
            {
                "providers": {
                    "anthropic": {"models": [{"id": "claude-sonnet-4.6"}]},
                    "nous": {"models": [{"id": "hermes-4-70b"}]},
                }
            },
            {"nous"},
        )
        self.assertEqual([row["id"] for row in keyed_nous], ["nous/hermes-4-70b"])
        picker = Path(__file__).resolve().parent.parent / "openbot" / "pickers.py"
        self.assertIn("lmarena-ai/leaderboard-dataset", picker.read_text(encoding="utf-8"))
        self.assertNotIn("openrouter.ai/rankings", picker.read_text(encoding="utf-8"))
        self.assertNotIn("classifications/task", picker.read_text(encoding="utf-8"))
        from openbot.keyring import PASTEABLE
        from openbot.providers import NOUS_SUBSCRIBE, PROVIDERS

        self.assertIn("openrouter", {item["id"] for item in PASTEABLE})
        self.assertEqual(PASTEABLE[0]["id"], "nous")
        self.assertEqual(PASTEABLE[0]["subscribe"], NOUS_SUBSCRIBE)
        self.assertEqual(NOUS_SUBSCRIBE, "https://portal.nousresearch.com/r/adam-schwartz")
        self.assertEqual(PASTEABLE[0]["engines"], ["Hermes Agent"])
        nous_provider = next(item for item in PROVIDERS if item["id"] == "nous")
        self.assertEqual(nous_provider["connect"], NOUS_SUBSCRIBE)
        self.assertTrue(nous_provider.get("hermes_default"))
        opencode = next(item for item in PASTEABLE if item["id"] == "opencode")
        self.assertIn("OPENCODE_ZEN_API_KEY", opencode["env"])
        self.assertIn("OPENCODE_GO_API_KEY", opencode["env"])


class AutoPickTests(unittest.TestCase):
    def test_chat_stays_on_opencode_even_if_openrouter_is_cheaper(self):
        from openbot.auto import auto_model_for_seat
        from openbot.pickers import arena_key

        self.assertEqual(arena_key("openrouter/anthropic/claude-sonnet-4.6"), "claudesonnet46")
        self.assertEqual(arena_key("opencode/claude-sonnet-4-6"), "claudesonnet46")
        models = [
            {
                "id": "openrouter/deepseek/deepseek-v4-flash-0731",
                "label": "Flash OR",
                "provider": "openrouter",
                "in_usd": 0.01,
                "out_usd": 0.02,
                "connected": True,
                "tools": True,
                "code": True,
                "engines": ("OpenCode", "Hermes Agent"),
            },
            {
                "id": "opencode/deepseek-v4-flash",
                "label": "Flash Go",
                "provider": "opencode",
                "in_usd": 0.05,
                "out_usd": 0.1,
                "connected": True,
                "tools": True,
                "code": True,
                "engines": ("OpenCode", "Hermes Agent"),
            },
        ]
        pick = auto_model_for_seat("chat", models=models, guides={})
        self.assertEqual(pick["id"], "opencode/deepseek-v4-flash")
        think = auto_model_for_seat(
            "think",
            models=[
                {
                    "id": "opencode/deepseek-v4-flash",
                    "label": "Flash",
                    "provider": "opencode",
                    "in_usd": 0.05,
                    "out_usd": 0.1,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "reasoning": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
                {
                    "id": "opencode/claude-sonnet-4-6",
                    "label": "Sonnet",
                    "provider": "opencode",
                    "in_usd": 3,
                    "out_usd": 15,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "reasoning": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
                {
                    "id": "opencode/gpt-5.4",
                    "label": "GPT 5.4",
                    "provider": "opencode",
                    "in_usd": 1.2,
                    "out_usd": 4.8,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "reasoning": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
            ],
            guides={
                "think": {
                    "scores": [
                        {"id": "claude-sonnet-4-6", "rating": 1400, "key": "claudesonnet46", "rank": 1},
                        {"id": "gpt-5.4", "rating": 1390, "key": "gpt54", "rank": 2},
                    ],
                    "as_of": "2026-06-10",
                }
            },
        )
        self.assertEqual(think["id"], "opencode/gpt-5.4")
        self.assertIn("Arena", think["why"])
        code = auto_model_for_seat(
            "code",
            models=[
                {
                    "id": "opencode/claude-opus-5",
                    "label": "Opus 5",
                    "provider": "opencode",
                    "in_usd": 0,
                    "out_usd": 0,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "reasoning": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
                {
                    "id": "opencode/claude-fable-5",
                    "label": "Fable 5",
                    "provider": "opencode",
                    "in_usd": 0,
                    "out_usd": 0,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "reasoning": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
            ],
            guides={
                "code": {
                    "scores": [
                        {"id": "claude-opus-5", "rating": 1661, "key": "claudeopus5", "rank": 1},
                        {"id": "claude-fable-5", "rating": 1627, "key": "claudefable5", "rank": 2},
                    ],
                    "as_of": "2026-09-01",
                }
            },
        )
        self.assertEqual(code["id"], "opencode/claude-fable-5")
        ops = auto_model_for_seat(
            "ops",
            models=[
                {
                    "id": "opencode/big-pickle",
                    "label": "Big Pickle",
                    "provider": "opencode",
                    "in_usd": 0,
                    "out_usd": 0,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
                {
                    "id": "opencode/claude-haiku-4-5",
                    "label": "Haiku",
                    "provider": "opencode",
                    "in_usd": 0,
                    "out_usd": 0,
                    "connected": True,
                    "tools": True,
                    "code": True,
                    "engines": ("OpenCode", "Hermes Agent"),
                },
            ],
            guides={},
        )
        self.assertEqual(ops["id"], "opencode/claude-haiku-4-5")

    def test_opencode_key_falls_back_to_keyring(self):
        import openbot.providers as providers

        with unittest.mock.patch.object(providers, "_read_auth", return_value={}), unittest.mock.patch(
            "openbot.keyring.accounts_for",
            return_value=[{"key": "test-go-placeholder"}],
        ):
            self.assertEqual(providers._opencode_key(), "test-go-placeholder")

    def test_zen_models_waits_when_cache_empty(self):
        import openbot.providers as providers

        with providers._ZEN_LOCK:
            providers._ZEN_CACHE["at"] = 0.0
            providers._ZEN_CACHE["models"] = []
            providers._ZEN_FETCHING = False
        called = []

        def fake_refresh():
            called.append(1)
            with providers._ZEN_LOCK:
                providers._ZEN_CACHE["at"] = 1.0
                providers._ZEN_CACHE["models"] = [{"id": "opencode/deepseek-v4-flash"}]
                providers._ZEN_FETCHING = False

        try:
            with unittest.mock.patch.object(providers, "_refresh_zen_models", fake_refresh):
                rows = providers.zen_models()
            self.assertEqual(called, [1])
            self.assertEqual(rows[0]["id"], "opencode/deepseek-v4-flash")
        finally:
            with providers._ZEN_LOCK:
                providers._ZEN_CACHE["at"] = 0.0
                providers._ZEN_CACHE["models"] = []
                providers._ZEN_FETCHING = False


class KeyringTests(unittest.TestCase):
    def test_rename_account_keeps_secret_off_the_wire(self):
        import openbot.keyring as keyring_mod

        old = keyring_mod.SECRETS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "secrets.local.json"
                keyring_mod.SECRETS_PATH = path
                path.write_text(
                    json.dumps(
                        {
                            "accounts": [
                                {
                                    "id": "abc12345",
                                    "provider": "opencode",
                                    "label": "old name",
                                    "key": "test-opencode-placeholder",
                                }
                            ],
                            "fallback": ["abc12345"],
                            "active": {},
                        }
                    ),
                    encoding="utf-8",
                )
                renamed = keyring_mod.rename_account("abc12345", "ListLogic Go")
                self.assertEqual(renamed["accounts"][0]["label"], "ListLogic Go")
                self.assertNotIn("test-opencode-placeholder", json.dumps(renamed))
        finally:
            keyring_mod.SECRETS_PATH = old

    def test_keyring_order_keeps_openrouter_last(self):
        import openbot.keyring as keyring_mod

        old = keyring_mod.SECRETS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "secrets.local.json"
                keyring_mod.SECRETS_PATH = path
                path.write_text(
                    json.dumps(
                        {
                            "accounts": [
                                {"id": "oc1", "provider": "opencode", "label": "Go 1", "key": "x"},
                                {"id": "oc2", "provider": "opencode", "label": "Go 2", "key": "y"},
                                {"id": "or1", "provider": "openrouter", "label": "OR", "key": "z"},
                            ],
                            "fallback": ["oc1", "oc2", "or1"],
                            "active": {},
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(
                    keyring_mod.ordered_account_ids(engine="Hermes Agent"),
                    ["oc1", "oc2", "or1"],
                )
                self.assertEqual(
                    keyring_mod.ordered_account_ids(engine="Hermes Agent", provider="openrouter"),
                    ["or1"],
                )
                self.assertEqual(
                    keyring_mod.ordered_account_ids(engine="Hermes Agent", provider="opencode"),
                    ["oc1", "oc2"],
                )
        finally:
            keyring_mod.SECRETS_PATH = old

    def test_empty_opencode_wallet_is_skipped_for_next_key(self):
        import openbot.keyring as keyring_mod
        from openbot import router as router_mod

        old = keyring_mod.SECRETS_PATH
        keyring_mod.clear_marked_empty()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "secrets.local.json"
                keyring_mod.SECRETS_PATH = path
                path.write_text(
                    json.dumps(
                        {
                            "accounts": [
                                {"id": "oc1", "provider": "opencode", "label": "Go 1", "key": "x"},
                                {"id": "oc2", "provider": "opencode", "label": "Go 2", "key": "y"},
                                {"id": "or1", "provider": "openrouter", "label": "OR", "key": "z"},
                            ],
                            "fallback": ["oc1", "oc2", "or1"],
                            "active": {},
                        }
                    ),
                    encoding="utf-8",
                )
                with unittest.mock.patch.object(
                    router_mod,
                    "cheap_chat_for_provider",
                    side_effect=lambda provider, models=None: (
                        "openrouter/deepseek/deepseek-v4-flash-0731" if provider == "openrouter" else ""
                    ),
                ):
                    attempts = router_mod._code_attempts({}, "opencode/deepseek-v4-flash")
                self.assertEqual([row["id"] for row, _model in attempts], ["oc1", "oc2", "or1"])
                self.assertEqual(attempts[0][1], "opencode/deepseek-v4-flash")
                self.assertEqual(attempts[2][1], "openrouter/deepseek/deepseek-v4-flash-0731")
                keyring_mod.mark_wallet_empty("oc1")
                with unittest.mock.patch.object(
                    router_mod,
                    "cheap_chat_for_provider",
                    side_effect=lambda provider, models=None: (
                        "openrouter/deepseek/deepseek-v4-flash-0731" if provider == "openrouter" else ""
                    ),
                ):
                    attempts = router_mod._code_attempts({}, "opencode/deepseek-v4-flash")
                self.assertEqual([row["id"] for row, _model in attempts], ["oc2", "or1"])
                picked = []

                def fake_activate(account_id):
                    picked.append(account_id)
                    return {}

                with unittest.mock.patch.object(keyring_mod, "activate_account", fake_activate):
                    self.assertEqual(keyring_mod.activate_for_engine("OpenCode"), "oc2")
                self.assertEqual(picked, ["oc2"])
                seen = []
                drop = router_mod._quiet_delta(seen.append)
                drop(
                    "HTTP 401: Insufficient balance. Manage your billing here: https://opencode.ai/workspace/x/billing"
                )
                drop("patched footer")
                self.assertEqual(seen, ["patched footer"])
        finally:
            keyring_mod.SECRETS_PATH = old
            keyring_mod.clear_marked_empty()

    def test_nous_key_becomes_hermes_primary(self):
        import openbot.keyring as keyring_mod

        old = keyring_mod.SECRETS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "secrets.local.json"
                keyring_mod.SECRETS_PATH = path
                path.write_text(
                    json.dumps(
                        {
                            "accounts": [
                                {"id": "oc1", "provider": "opencode", "label": "Go 1", "key": "x"},
                                {"id": "or1", "provider": "openrouter", "label": "OR", "key": "z"},
                            ],
                            "fallback": ["oc1", "or1"],
                            "active": {},
                        }
                    ),
                    encoding="utf-8",
                )
                with unittest.mock.patch.object(keyring_mod, "_write_opencode_auth"), unittest.mock.patch.object(
                    keyring_mod, "_write_hermes_env"
                ), unittest.mock.patch("openbot.keyring.upsert_env"):
                    public = keyring_mod.add_account("nous", "nous-placeholder", "Portal")
                self.assertNotIn("nous-placeholder", json.dumps(public))
                self.assertTrue(public["fallback"][0])
                self.assertEqual(public["accounts"][-1]["provider"], "nous")
                self.assertEqual(
                    keyring_mod.ordered_account_ids(engine="Hermes Agent"),
                    [public["fallback"][0], "oc1", "or1"],
                )
                self.assertEqual(
                    keyring_mod.ordered_account_ids(engine="OpenCode"),
                    ["oc1", "or1"],
                )
        finally:
            keyring_mod.SECRETS_PATH = old

    def test_site_login_stays_off_the_wire(self):
        import openbot.keyring as keyring_mod
        from openbot.keyring import LOGIN_FILE

        old = keyring_mod.SECRETS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                path = folder / "secrets.local.json"
                keyring_mod.SECRETS_PATH = path
                public = keyring_mod.add_login(
                    "GBP",
                    "https://business.google.com",
                    "user@example.com",
                    "secret-pass",
                    "saa-homes",
                    auto=True,
                )
                blob = json.dumps(public)
                self.assertNotIn("secret-pass", blob)
                self.assertTrue(public["logins"][0]["has_password"])
                self.assertTrue(public["logins"][0]["auto"])
                asked = keyring_mod.add_login(
                    "Meta",
                    "https://business.facebook.com",
                    "user@example.com",
                    "other-secret",
                    "saa-homes",
                    auto=False,
                )
                self.assertNotIn("other-secret", json.dumps(asked))
                home = folder / "hermes"
                home.mkdir()
                staged = keyring_mod.stage_job_logins("saa-homes", home, only_auto=True)
                self.assertTrue(staged)
                text = Path(staged).read_text(encoding="utf-8")
                self.assertIn("secret-pass", text)
                self.assertNotIn("other-secret", text)
                self.assertEqual(Path(staged).name, LOGIN_FILE)
                used = keyring_mod.use_login(
                    project_id="saa-homes",
                    username="once@example.com",
                    password="once-secret",
                    save=False,
                    home=str(home),
                )
                self.assertTrue(used["staged"])
                self.assertFalse(used["saved"])
                self.assertNotIn("once-secret", json.dumps(used))
                once_text = (home / LOGIN_FILE).read_text(encoding="utf-8")
                self.assertIn("once-secret", once_text)
                parsed = keyring_mod.parse_chat_login(
                    "the login is adam@saahomes.com and password is saahomes.com"
                )
                self.assertEqual(parsed["username"], "adam@saahomes.com")
                self.assertEqual(
                    keyring_mod.redact_chat_login(
                        "the login is adam@saahomes.com and password is saahomes.com"
                    ),
                    "Login given on the board (not stored in chat).",
                )
        finally:
            keyring_mod.SECRETS_PATH = old

    def test_pending_approvals_use_latest_job(self):
        from unittest.mock import patch

        from openbot.router import pending_approvals

        jobs = [
            {
                "id": "new",
                "at": "2026-09-02T20:00:00",
                "login_wall": True,
                "project_id": "saa-homes",
                "engine": "Hermes Agent",
                "preset": "research",
                "url": "https://business.google.com",
            },
            {
                "id": "old",
                "at": "2026-09-02T10:00:00",
                "diff_pending": True,
                "project_id": "saa-homes",
                "engine": "OpenCode",
                "preset": "builder",
            },
            {
                "id": "diff",
                "at": "2026-09-02T19:00:00",
                "diff_pending": True,
                "project_id": "openbot",
                "engine": "OpenCode",
                "preset": "builder",
            },
        ]
        with patch("openbot.router.list_jobs", return_value=jobs):
            rows = pending_approvals()
        kinds = {row["project_id"]: row["kind"] for row in rows}
        self.assertEqual(kinds["saa-homes"], "login")
        self.assertEqual(kinds["openbot"], "diff")

    def test_hermes_portal_auth_counts_as_nous(self):
        from unittest.mock import patch

        from openbot.providers import connected_provider_ids, nous_portal_connected

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "auth.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "providers": {
                            "nous": {
                                "refresh_token": "rt-placeholder",
                                "access_token": "at-placeholder",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("openbot.providers.hermes_home", return_value=home):
                self.assertTrue(nous_portal_connected())
                self.assertIn("nous", connected_provider_ids())
                from openbot.keyring import public_keyring

                blob = public_keyring()
                self.assertTrue(blob["nous_portal"])
                self.assertEqual(blob["subscribe"], "https://portal.nousresearch.com/r/adam-schwartz")
                wire = json.dumps(blob)
                self.assertNotIn("rt-placeholder", wire)
                self.assertNotIn("at-placeholder", wire)


class StreamAndErrorTests(unittest.TestCase):
    def test_chat_stream_handler_is_not_dead_code(self):
        import ast

        src = (Path(__file__).resolve().parent.parent / "openbot" / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        stream_if = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Handler":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "do_POST":
                        for stmt in item.body:
                            if (
                                isinstance(stmt, ast.If)
                                and isinstance(stmt.test, ast.Compare)
                                and any(
                                    isinstance(cmp, ast.Constant) and cmp.value == "/api/chat/stream"
                                    for cmp in stmt.test.comparators
                                )
                            ):
                                stream_if = stmt
        self.assertIsNotNone(stream_if)
        kinds = [type(item).__name__ for item in stream_if.body]
        self.assertIn("Try", kinds)
        self.assertIn("FunctionDef", kinds)
        src = (Path(__file__).resolve().parent.parent / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"Connection", "close"', src)

    def test_opencode_error_strips_headers(self):
        from openbot.usage import error_message_from_raw, sanitize_job_text

        raw = json.dumps(
            {
                "type": "error",
                "error": {
                    "name": "APIError",
                    "data": {
                        "message": "No endpoints found that support tool use.",
                        "responseHeaders": {"set-cookie": "secret-cookie"},
                    },
                },
            }
        )
        self.assertEqual(error_message_from_raw(raw), "No endpoints found that support tool use.")
        self.assertNotIn("set-cookie", sanitize_job_text(raw + " set-cookie=secret").lower())


class OrgTests(unittest.TestCase):
    def test_ensure_org_does_not_recurse(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                org_mod.ORG = folder / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(folder),
                            "projects": [
                                {
                                    "id": "openbot",
                                    "name": "openbot",
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": True,
                                    "workers": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                data = org_mod.public_org()
                self.assertEqual(data["role"], "cos")
                self.assertEqual(data["title"], "Chief of Staff")
                self.assertTrue(data["projects"])
                self.assertEqual(data["projects"][0]["workers"], [])
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile

    def test_new_ceo_gets_own_workspace(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_homes = org_mod.HERMES_HOMES
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                org_mod.ORG = folder / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.HERMES_HOMES = folder / "hermes-homes"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(folder),
                            "projects": [
                                {
                                    "id": "openbot",
                                    "name": "openbot",
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": True,
                                    "workers": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                data = org_mod.add_project(None, "opencode test")
                ceo = next(row for row in data["projects"] if row["id"] == "opencode-test")
                self.assertEqual(data["project_id"], "opencode-test")
                self.assertNotEqual(Path(ceo["folder"]).resolve(), Path(folder).resolve())
                self.assertTrue(Path(ceo["folder"]).is_dir())
                self.assertTrue((Path(ceo["folder"]) / "README.md").is_file())
                home = Path(ceo["tools"]["hermes_home"])
                self.assertTrue(home.is_dir())
                self.assertEqual(home.parent.resolve(), org_mod.HERMES_HOMES.resolve())
                self.assertEqual(home.name, "opencode-test")
                if org_mod.which("git"):
                    self.assertTrue((Path(ceo["folder"]) / ".git").exists())
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            org_mod.HERMES_HOMES = old_homes

    def test_existing_repo_is_not_reinitialized(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_homes = org_mod.HERMES_HOMES
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                repo = folder / "existing-app"
                repo.mkdir()
                git = repo / ".git"
                git.mkdir()
                (git / "HEAD").write_text("ref: refs/heads/keep-me\n", encoding="utf-8")
                (repo / "keep.txt").write_text("stay", encoding="utf-8")
                org_mod.ORG = folder / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.HERMES_HOMES = folder / "hermes-homes"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(folder),
                            "projects": [
                                {
                                    "id": "openbot",
                                    "name": "openbot",
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": True,
                                    "workers": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                data = org_mod.add_project(str(repo), "Existing App")
                ceo = next(row for row in data["projects"] if row["id"] == "existing-app")
                self.assertEqual(Path(ceo["folder"]).resolve(), repo.resolve())
                self.assertEqual((git / "HEAD").read_text(encoding="utf-8"), "ref: refs/heads/keep-me\n")
                self.assertFalse((repo / "README.md").exists())
                self.assertTrue(Path(ceo["tools"]["hermes_home"]).is_dir())
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            org_mod.HERMES_HOMES = old_homes

    def test_hermes_env_inherits_machine_keys(self):
        from unittest.mock import patch

        import openbot.hermes as hermes_mod

        with tempfile.TemporaryDirectory() as tmp:
            machine = Path(tmp) / "machine"
            ceo = Path(tmp) / "ceo"
            machine.mkdir()
            ceo.mkdir()
            (machine / ".env").write_text("OPENCODE_ZEN_API_KEY=test-machine-key\n", encoding="utf-8")
            with patch("openbot.hermes.hermes_home", return_value=machine):
                env = hermes_mod._hermes_env(ceo)
            self.assertEqual(env["HERMES_HOME"], str(ceo))
            self.assertEqual(env.get("OPENCODE_ZEN_API_KEY"), "test-machine-key")
            self.assertFalse((ceo / ".env").exists())
            (ceo / ".env").write_text("OPENCODE_ZEN_API_KEY=test-ceo-overlay\n", encoding="utf-8")
            with patch("openbot.hermes.hermes_home", return_value=machine):
                overlay = hermes_mod._hermes_env(ceo)
            self.assertEqual(overlay.get("OPENCODE_ZEN_API_KEY"), "test-ceo-overlay")

    def test_folder_inbox_and_session(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_homes = org_mod.HERMES_HOMES
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                extra = root / "extra"
                extra.mkdir()
                moved = root / "moved"
                moved.mkdir()
                org_mod.ORG = root / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.HERMES_HOMES = root / "hermes-homes"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(root),
                            "projects": [
                                {
                                    "id": "openbot",
                                    "name": "openbot",
                                    "role": "ceo",
                                    "folder": str(root),
                                    "primary": True,
                                    "workers": [],
                                },
                                {
                                    "id": "extra",
                                    "name": "extra",
                                    "role": "ceo",
                                    "folder": str(extra),
                                    "primary": False,
                                    "workers": [],
                                },
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                org_mod._ensure_project_index("extra", "extra", str(extra))
                org_mod.set_project_folder("extra", str(moved))
                ceo = next(row for row in org_mod.public_org()["projects"] if row["id"] == "extra")
                self.assertTrue("moved" in ceo["folder"].replace("\\", "/"))
                path = org_mod.write_project_inbox("extra", "Build me a full program and set up 25 tasks")
                self.assertTrue(path.is_file())
                self.assertIn("queued", org_mod.inbox_tail("extra"))
                self.assertEqual(org_mod.session_name("extra", "scout"), "openbot-extra-scout")
                self.assertEqual(org_mod.session_name("extra", None), "openbot-extra-ceo")
                org_mod.rename_project("extra", "Atlas")
                ceo = next(row for row in org_mod.public_org()["projects"] if row["id"] == "extra")
                self.assertEqual(ceo["name"], "Atlas")
                org_mod.add_schedule("extra", "0 9 * * *", "ping the board", "abc123")
                self.assertEqual(org_mod.read_schedules("extra")[0]["schedule"], "0 9 * * *")
                ceo = next(row for row in org_mod.public_org()["projects"] if row["id"] == "extra")
                self.assertTrue(Path(ceo["tools"]["hermes_home"]).is_dir())
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            org_mod.HERMES_HOMES = old_homes


class StaffBusTests(unittest.TestCase):
    def test_cos_has_no_engine_home(self):
        import openbot.org as org_mod

        org = org_mod.public_org()
        self.assertEqual(org["role"], "cos")
        self.assertEqual(org.get("hermes_home"), "")
        self.assertIn("# Chief of Staff", org.get("staff") or "")
        self.assertNotIn("## Vault", org.get("staff") or "")

    def test_work_target_rides_ceo_not_cos(self):
        from openbot.org import primary_project_id, work_target

        self.assertIsNone(work_target(None, "cos"))
        self.assertIsNone(work_target(None, "ask"))
        self.assertEqual(work_target(None, "builder"), primary_project_id())
        self.assertEqual(work_target("opencode-test", "think"), "opencode-test")
        self.assertEqual(work_target("openbot", "cos"), "openbot")

    def test_staff_briefing_and_worker_session(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_homes = org_mod.HERMES_HOMES
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                work = root / "work"
                work.mkdir()
                org_mod.ORG = root / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.HERMES_HOMES = root / "hermes-homes"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(work),
                            "projects": [
                                {
                                    "id": "alpha",
                                    "name": "alpha",
                                    "role": "ceo",
                                    "folder": str(work),
                                    "primary": True,
                                    "workers": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                org_mod._ensure_project_index("alpha", "alpha", str(work))
                info = org_mod.ensure_ceo_engines("alpha")
                self.assertEqual(Path(info["folder"]).resolve(), work.resolve())
                self.assertTrue(Path(info["hermes_home"]).is_dir())
                self.assertEqual(Path(info["hermes_home"]).name, "alpha")
                self.assertFalse((org_mod.HERMES_HOMES / "cos").exists())
                org_mod.add_worker("alpha", "Scout")
                data = org_mod.public_org()
                self.assertEqual(data.get("hermes_home"), "")
                ceo = next(row for row in data["projects"] if row["id"] == "alpha")
                self.assertTrue(ceo["tools"]["hermes_home"])
                self.assertEqual(ceo["workers"][0]["session"], "openbot-alpha-scout")
                brief = org_mod.staff_briefing()
                self.assertIn("alpha CEO", brief)
                self.assertIn("Scout:", brief)
                status = org_mod.staff_status_reply()
                self.assertIn("alpha:", status)
                self.assertEqual(org_mod.session_name(None, None), None)
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            org_mod.HERMES_HOMES = old_homes


class LastResultTests(unittest.TestCase):
    def test_scopes_hints_to_project(self):
        from openbot.router import last_results
        import openbot.store as store_mod

        old = store_mod.JOBS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store_mod.JOBS = Path(tmp)
                write_job(
                    {
                        "id": "aaa",
                        "at": "2026-01-01T00:00:00Z",
                        "engine": "Hermes Agent",
                        "project_id": "alpha",
                        "worker_id": "scout",
                        "text": "alpha result",
                    }
                )
                write_job(
                    {
                        "id": "bbb",
                        "at": "2026-01-02T00:00:00Z",
                        "engine": "OpenCode",
                        "project_id": "beta",
                        "worker_id": "dev",
                        "text": "beta result",
                    }
                )
                scoped = last_results(project_id="alpha")
                self.assertIn("alpha result", scoped)
                self.assertNotIn("beta result", scoped)
        finally:
            store_mod.JOBS = old


class ResearchTests(unittest.TestCase):
    def test_first_url(self):
        from openbot.research import first_url

        self.assertEqual(first_url("Look at this site https://example.com/docs"), "https://example.com/docs")
        self.assertIsNone(first_url("no link here"))


class HermesGlueTests(unittest.TestCase):
    def test_parse_schedule_and_split_model(self):
        from openbot.hermes import chat_packet, job_packet, parse_schedule, split_model

        self.assertEqual(parse_schedule("Every morning ping the board"), "0 9 * * *")
        self.assertEqual(parse_schedule("every 2 hours check the site"), "every 2h")
        self.assertEqual(parse_schedule("every 30 minutes"), "every 30m")
        self.assertIsNone(parse_schedule("remind me sometime"))
        self.assertEqual(split_model("opencode/gpt-5.4-mini"), ("opencode-zen", "gpt-5.4-mini"))
        self.assertEqual(split_model("openrouter/anthropic/claude-sonnet-4.6"), ("openrouter", "anthropic/claude-sonnet-4.6"))
        self.assertEqual(split_model("nous/hermes-3"), ("nous", "hermes-3"))
        self.assertEqual(split_model("local-model"), (None, "local-model"))
        self.assertEqual(split_model("unknown-lab/gpt-5"), (None, None))
        packet = job_packet("research", "Now: ok", "Last: none", "Look at https://example.com", "URL: https://example.com")
        self.assertIn("INDEX:", packet)
        self.assertIn("engine on this CEO", packet)
        self.assertIn("Look at https://example.com", packet)
        self.assertIn("HANDOFF", packet)
        self.assertIn("Park send", packet)
        self.assertIn("LOGIN_WALL", packet)
        self.assertNotIn("api_key", packet.lower())
        talk = chat_packet("openbot CEO", "Now: ok\nLast: —", "hello")
        self.assertIn("hello", talk)
        self.assertIn("You are the openbot CEO", talk)
        self.assertIn("report to Chief of Staff", talk)
        self.assertIn("STAFF", talk)
        self.assertIn("Now: ok", talk)
        self.assertNotIn("INDEX:", talk)
        self.assertNotIn("Write a short RESULT", talk)
        from openbot.hermes import clean_hermes_text

        cleaned = clean_hermes_text("Session openbot-openbot-ceo found\nHey.\nsession_id: abc123")
        self.assertEqual(cleaned, "Hey.")
        resumed = clean_hermes_text(
            "Resumed session 20260831_221406_e0566d (1 user message, 12 total messages)\n"
            "RESULT (Hermes Agent · think)\n"
            "Hello. Board is running."
        )
        self.assertEqual(resumed, "Hello. Board is running.")
        arrow = clean_hermes_text(
            "↻ Resumed session 20260820_043738_841a6253 \"Session Restored After Gateway Shutdown\" "
            "(27 user messages, 814 total messages)\n"
            "Model restored from session: deepseek/deepseek-v4-flash (openrouter)\n"
            "SAA Homes Think confirmed and ready."
        )
        self.assertEqual(arrow, "SAA Homes Think confirmed and ready.")
        source = (Path(__file__).resolve().parent.parent / "openbot" / "hermes.py").read_text(encoding="utf-8")
        self.assertIn("--continue", source)
        self.assertIn("--resume", source)
        self.assertIn("--skills", source)
        self.assertIn("--ignore-rules", source)
        self.assertIn("--toolsets", source)
        self.assertIn("bot_room", source)
        self.assertNotIn('--toolsets", "none"', source)
        self.assertIn('"1" if talk', source)
        self.assertNotIn("--ignore-user-config", source)
        self.assertNotIn("--create-if-missing", source)


class ThreadQuoteTests(unittest.TestCase):
    def test_one_quote_never_replays_the_week(self):
        from openbot import threadstore

        old = threadstore.THREADS
        with tempfile.TemporaryDirectory() as tmp:
            threadstore.THREADS = Path(tmp)
            key = threadstore.thread_key("atlas", None)
            self.assertEqual(key, "org:atlas:ceo")
            threadstore.append_turn(key, {"role": "user", "text": "Ship the landing page in navy not teal."})
            threadstore.append_turn(key, {"role": "bot", "job": {"text": "ok navy it is"}})
            self.assertTrue(threadstore.wants_quote("as I said earlier, the navy landing page"))
            self.assertFalse(threadstore.wants_quote("please implement the header"))
            quote = threadstore.search_quote(key, "as I said earlier, the navy landing page")
            self.assertIn("navy", quote.lower())
            self.assertLessEqual(len(quote), 400)
            from openbot.router import _clean_quote, _packet_extra

            self.assertEqual(_clean_quote("  navy   landing  "), "navy landing")
            extra = _packet_extra(None, quote="Ship the landing page in navy not teal.")
            self.assertIn("QUOTE", extra)
            self.assertIn("navy", extra)
        threadstore.THREADS = old


class CronWatchTests(unittest.TestCase):
    def test_parse_run_lines_skips_empty(self):
        from openbot.cronwatch import parse_run_lines

        self.assertEqual(parse_run_lines(""), [])
        self.assertEqual(parse_run_lines("No cron execution history found."), [])
        lines = parse_run_lines("Job ID    Name\n--------\nopenbot-atlas-morning  ok  hello")
        self.assertTrue(any("openbot-atlas" in line for line in lines))


class ProjectToolsTests(unittest.TestCase):
    def test_tools_survive_ensure_org(self):
        import openbot.org as org_mod
        from unittest.mock import patch

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                pid = org_mod._slug(folder.name)
                org_mod.ORG = folder / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(folder),
                            "projects": [
                                {
                                    "id": pid,
                                    "name": pid,
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": True,
                                    "workers": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                with patch("openbot.org.load_config", return_value={"work_dir": str(folder)}):
                    org_mod.patch_project_tools(
                        pid,
                        {
                            "mcp_github": True,
                            "skills": "github",
                            "spend_cap_usd": 2.5,
                            "seats": {"think": {"model": "opencode/gpt-5.4"}},
                        },
                    )
                    data = org_mod.ensure_org()
                    tools = next(row["tools"] for row in data["projects"] if row["id"] == pid)
                    self.assertTrue(tools["mcp_github"])
                    self.assertEqual(tools["skills"], "github")
                    self.assertEqual(tools["spend_cap_usd"], 2.5)
                    self.assertEqual(
                        tools["seats"]["think"]["model"],
                        "opencode/gpt-5.4",
                    )
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile

    def test_seat_model_prefers_ceo(self):
        from openbot.models import seat_model

        settings = {"seats": {"think": {"model": "openrouter/nousresearch/hermes-4-70b"}}}
        ceo = {"think": {"model": "openrouter/anthropic/claude-sonnet-4.6"}}
        self.assertEqual(
            seat_model(settings, "think", ceo),
            "openrouter/anthropic/claude-sonnet-4.6",
        )
        self.assertEqual(
            seat_model(settings, "think", {}),
            "openrouter/nousresearch/hermes-4-70b",
        )


class HermesImportTests(unittest.TestCase):
    def test_peek_redacts_keys_and_skips_env(self):
        import zipfile

        from openbot.hermes_import import build_index, peek_backup

        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "hermes-backup-2026-08-31-101955.zip"
            with zipfile.ZipFile(zpath, "w") as archive:
                archive.writestr(
                    "SOUL.md",
                    "# SAA Homes SEO\n\nAPI_KEY=sk-secretsecret12\nNow: ranking the blog.\n",
                )
                archive.writestr(".env", "OPENAI_API_KEY=sk-secretsecret12\n")
            peek = peek_backup(str(zpath))
            self.assertEqual(peek["title"], "SAA Homes SEO")
            self.assertIn("soul.md", peek["files"])
            self.assertNotIn("sk-secret", peek["soul"])
            index = build_index("SAA Homes SEO", tmp, peek["texts"], str(zpath))
            self.assertNotIn("sk-secret", index)
            self.assertIn("SAA Homes SEO", index)
            self.assertIn("ranking the blog", index)

    def test_public_instances_hide_keys(self):
        from openbot import hermes_import as hi
        from openbot.keyring import SECRETS_PATH

        old = hi.SECRETS_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "secrets.local.json"
                hi.SECRETS_PATH = path
                import openbot.keyring as keyring_mod

                old_keyring = keyring_mod.SECRETS_PATH
                keyring_mod.SECRETS_PATH = path
                rows = hi.add_instance("https://example.up.railway.app", "super-secret-key", "SAA Homes")
                self.assertEqual(rows[0]["label"], "SAA Homes")
                self.assertTrue(rows[0]["has_key"])
                self.assertNotIn("super-secret-key", json.dumps(hi.public_instances()))
                keyring_mod.SECRETS_PATH = old_keyring
        finally:
            hi.SECRETS_PATH = old


class ChannelTests(unittest.TestCase):
    def test_recent_turns_from_state_db(self):
        import sqlite3

        from openbot.channel import public_channel, session_hint, telegram_session_id

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            db = home / "state.db"
            con = sqlite3.connect(db)
            con.execute(
                "CREATE TABLE gateway_routing (session_key TEXT, entry_json TEXT, updated_at INTEGER)"
            )
            con.execute(
                "CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, timestamp INTEGER)"
            )
            con.execute(
                "INSERT INTO gateway_routing VALUES (?,?,?)",
                ("agent:main:telegram:dm:1", json.dumps({"session_id": "ses-tg"}), 9),
            )
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?)",
                ("ses-tg", "user", "status on Fort Collins", 1),
            )
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?)",
                ("ses-tg", "assistant", "Now: ranking the hub pages.", 2),
            )
            con.commit()
            con.close()
            self.assertEqual(telegram_session_id(home), "ses-tg")
            channel = public_channel(home)
            self.assertEqual(channel["hermes_session_id"], "ses-tg")
            self.assertEqual(channel["turns"][0]["text"], "status on Fort Collins")
            self.assertEqual(channel["turns"][1]["role"], "bot")
            self.assertIn("Railway", channel["note"])
            hint = session_hint(home)
            self.assertIn("RECENT TELEGRAM", hint)
            self.assertIn("Fort Collins", hint)


class RemoveProjectTests(unittest.TestCase):
    def test_delete_requires_typed_name(self):
        import openbot.org as org_mod

        old_org = org_mod.ORG
        old_profile = org_mod.PROFILE_PATH
        old_homes = org_mod.HERMES_HOMES
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                org_mod.ORG = folder / "org"
                org_mod.PROFILE_PATH = org_mod.ORG / "profile.json"
                org_mod.HERMES_HOMES = folder / "hermes-homes"
                org_mod.ORG.mkdir()
                org_mod.PROFILE_PATH.write_text(
                    json.dumps(
                        {
                            "name": "OPENBOT",
                            "role": "cos",
                            "folder": str(folder),
                            "projects": [
                                {
                                    "id": "openbot",
                                    "name": "openbot",
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": True,
                                    "workers": [],
                                },
                                {
                                    "id": "spare",
                                    "name": "Spare CEO",
                                    "role": "ceo",
                                    "folder": str(folder),
                                    "primary": False,
                                    "workers": [],
                                },
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    org_mod.remove_project("spare")
                with self.assertRaises(ValueError):
                    org_mod.remove_project("spare", "nope")
                org = org_mod.remove_project("openbot", "openbot")
                ids = [row["id"] for row in org["projects"]]
                self.assertNotIn("openbot", ids)
                self.assertIn("spare", ids)
                spare = next(row for row in org["projects"] if row["id"] == "spare")
                self.assertTrue(spare.get("primary"))
                leftover = org_mod.remove_project("spare", "Spare CEO")
                self.assertEqual(leftover["projects"], [])
        finally:
            org_mod.ORG = old_org
            org_mod.PROFILE_PATH = old_profile
            org_mod.HERMES_HOMES = old_homes


class BusLawTests(unittest.TestCase):
    def test_contracts_gates_and_files(self):
        import openbot.bus as bus_mod

        old = (bus_mod.ORG, bus_mod.ACTION_LOG, bus_mod.RULES)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bus_mod.ORG = root / "org"
            bus_mod.ACTION_LOG = bus_mod.ORG / "ACTION_LOG.md"
            bus_mod.RULES = bus_mod.ORG / "RULES.md"
            try:
                self.assertIn("Triage", bus_mod.contract_lines("cos"))
                self.assertIn("GATE 1 SOURCE", bus_mod.gates_block("research"))
                self.assertIn("MEMORY POLICY", bus_mod.law_extra("builder", "openbot"))
                gate = bus_mod.classify_gate("builder", "add a footer", diff_pending=True)
                self.assertEqual(gate["action"], "approval")
                parked = bus_mod.classify_gate("research", "publish this to twitter")
                self.assertTrue(parked["irreversible"])
                self.assertEqual(parked["action"], "approval")
                talk = bus_mod.classify_gate("cos", "hello", talk=True)
                self.assertEqual(talk["action"], "allow")
                rel = bus_mod.write_handoff(
                    "abc123",
                    "builder",
                    "Change the footer. password: hunter2",
                    "Patched.",
                    project_id="openbot",
                    engine="OpenCode",
                    next_owner="operator",
                )
                self.assertIn("handoffs", rel.replace("\\", "/"))
                blob = (bus_mod.bus_dir("openbot") / "handoffs" / "abc123.md").read_text(encoding="utf-8")
                self.assertIn("TASK:", blob)
                self.assertNotIn("hunter2", blob)
                self.assertIn("[redacted]", blob)
                bus_mod.append_action_log(
                    {
                        "id": "abc123",
                        "bot": "openbot",
                        "engine": "OpenCode",
                        "preset": "builder",
                        "status": "partial",
                        "gate": "approval",
                        "files": rel,
                        "approval": "needed",
                    }
                )
                log = bus_mod.ACTION_LOG.read_text(encoding="utf-8")
                self.assertIn("abc123", log)
                self.assertIn("password", bus_mod.SECRET.pattern.lower())
                hire = bus_mod.cos_file_reply("hire a gmail bot for inbox")
                self.assertIn("Do not hire a Bot for an app", hire)
                rule = bus_mod.cos_file_reply("We just found a failure: never treat chat as memory.")
                self.assertIn("org/RULES.md", rule)
                self.assertTrue(bus_mod.RULES.is_file())
                seeded = bus_mod.seed_contract("# Demo\n\nNow: ready.\n", "ceo")
                self.assertIn("## Contract", seeded)
                self.assertEqual(bus_mod.seed_contract(seeded, "ceo"), seeded)
            finally:
                bus_mod.ORG, bus_mod.ACTION_LOG, bus_mod.RULES = old

    def test_router_and_ops_use_the_bus(self):
        from openbot.ops import write_ops_ticket
        from openbot.router import _packet_extra, handle
        from unittest.mock import patch
        import openbot.ops as ops_mod

        extra = _packet_extra("openbot", extra="URL: https://example.com", preset="research")
        self.assertIn("THREE GATES", extra)
        self.assertIn("CONTRACT:", extra)
        self.assertIn("HANDOFF", extra)
        old_inbox = ops_mod.INBOX
        with tempfile.TemporaryDirectory() as tmp:
            ops_mod.INBOX = Path(tmp)
            try:
                ticket = write_ops_ticket("Every morning ping the board")
            finally:
                ops_mod.INBOX = old_inbox
        self.assertIn("SILENCE", ticket)
        self.assertIn("idempotent", ticket.lower())
        self.assertIn("FORBIDDEN", ticket)
        with patch("openbot.router.seated_or_auto", return_value=""), patch(
            "openbot.router.recommended_chat_id", return_value=""
        ):
            job = handle("hire a chrome bot")
        self.assertEqual(job.get("engine"), "board")
        self.assertEqual(job.get("preset"), "cos")
        self.assertIn("Do not hire a Bot for an app", job.get("text") or "")


class HandoffBusTests(unittest.TestCase):
    """Tests for handoff bus protocol: schema, load, claim, multi-step metadata."""

    def test_create_open_handoff_workflow(self):
        """create_handoff creates open status handoff that appears in list and can be claimed."""
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            try:
                # Create open handoff
                result = create_handoff(
                    task="Implement the new feature",
                    project_id="test5",
                    from_seat="cos",
                    to_seat="builder",
                    next_owner="builder"
                )
                self.assertTrue(result["ok"])
                self.assertIsNotNone(result["handoff_id"])
                self.assertIn("handoff-", result["handoff_id"])
                
                # Should appear in open handoffs list
                handoffs = load_open_handoffs("test5")
                self.assertEqual(len(handoffs), 1)
                self.assertEqual(handoffs[0]["status"], "open")
                self.assertEqual(handoffs[0]["to_seat"], "builder")
                self.assertIn("Implement the new feature", handoffs[0]["task"])
                
                # Claim it
                claim_result = claim_handoff(result["handoff_id"], "test5", "builder-worker")
                self.assertTrue(claim_result["ok"])
                
                # Should now be claimed
                handoffs_after = load_open_handoffs("test5")
                self.assertEqual(len(handoffs_after), 1)
                self.assertEqual(handoffs_after[0]["status"], "claimed")
                self.assertEqual(handoffs_after[0]["next_owner"], "builder-worker")
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root

    def test_write_handoff_creates_standard_schema(self):
        """write_handoff creates a standardized markdown file with required fields."""
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            try:
                rel_path = write_handoff(
                    job_id="job123",
                    preset="builder",
                    message="Refactor the utils module",
                    result="Diff created, waiting for Accept",
                    project_id="test-project",
                    status="partial",
                    sources="org/projects/test-project/INDEX.md",
                    next_owner="operator (Accept / Reject)",
                    from_seat="think",
                    to_seat="builder",
                )
                self.assertIn("handoffs/job123.md", rel_path)
                handoff_path = Path(tmp) / rel_path
                self.assertTrue(handoff_path.is_file())
                
                content = handoff_path.read_text(encoding="utf-8")
                # Check required fields
                self.assertIn("TASK:", content)
                self.assertIn("STATUS: partial", content)
                self.assertIn("OUTPUT:", content)
                self.assertIn("FROM: think", content)
                self.assertIn("TO: builder", content)
                self.assertIn("NEXT OWNER: operator (Accept / Reject)", content)
                self.assertIn("SOURCES:", content)
                self.assertIn("job123", content)
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root

    def test_load_open_handoffs_filters_by_status(self):
        """load_open_handoffs returns only open/claimed/blocked handoffs, not complete."""
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            try:
                # Create open handoff
                write_handoff(
                    "job1", "think", "Plan the feature", "Plan ready",
                    project_id="test2", status="open", next_owner="builder"
                )
                # Create claimed handoff
                write_handoff(
                    "job2", "builder", "Implement the feature", "Working on it",
                    project_id="test2", status="claimed", next_owner="ops"
                )
                # Create complete handoff (should be filtered out)
                write_handoff(
                    "job3", "research", "Find docs", "Docs found",
                    project_id="test2", status="complete", next_owner="operator"
                )
                
                handoffs = load_open_handoffs("test2")
                self.assertEqual(len(handoffs), 2)
                ids = {h["id"] for h in handoffs}
                self.assertIn("job1", ids)
                self.assertIn("job2", ids)
                self.assertNotIn("job3", ids)
                
                # Check fields are extracted
                job1 = next(h for h in handoffs if h["id"] == "job1")
                self.assertEqual(job1["status"], "open")
                self.assertIn("Plan the feature", job1["task"])
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root

    def test_claim_handoff_updates_status_and_owner(self):
        """claim_handoff changes STATUS to claimed and sets NEXT OWNER."""
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            try:
                write_handoff(
                    "job123", "think", "Analyze the problem", "Analysis complete",
                    project_id="test3", status="open", next_owner="—"
                )
                
                result = claim_handoff("job123", "test3", "builder")
                self.assertTrue(result["ok"])
                self.assertIn("claimed", result["message"])
                
                # Verify file was updated
                handoffs = load_open_handoffs("test3")
                job = next(h for h in handoffs if h["id"] == "job123")
                self.assertEqual(job["status"], "claimed")
                self.assertEqual(job["next_owner"], "builder")
                
                # Cannot claim completed handoff
                write_handoff(
                    "job456", "ops", "Done work", "Finished",
                    project_id="test3", status="complete", next_owner="operator"
                )
                result2 = claim_handoff("job456", "test3", "research")
                self.assertFalse(result2["ok"])
                self.assertIn("complete", result2["message"])
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root

    def test_handoff_summary_formats_for_job_packet(self):
        """handoff_summary generates brief text for job packet OPEN HANDOFFS section."""
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            try:
                # No handoffs
                summary = handoff_summary("test4")
                self.assertEqual(summary, "")
                
                # Create some handoffs
                write_handoff(
                    "job1", "think", "Design the API endpoints", "Draft ready",
                    project_id="test4", status="open", next_owner="builder"
                )
                write_handoff(
                    "job2", "research", "Find pricing info", "Blocked on login",
                    project_id="test4", status="blocked", next_owner="operator"
                )
                
                summary = handoff_summary("test4")
                self.assertIn("2 open handoffs:", summary)
                self.assertIn("job1:", summary)
                self.assertIn("job2:", summary)
                self.assertIn("builder", summary)
                self.assertIn("operator", summary)
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root

    def test_close_work_job_preserves_handoff_metadata(self):
        """close_work_job includes handoff_from/handoff_to for multi-step chains."""
        from openbot.bus import close_work_job
        import openbot.bus as bus_mod
        old_root = store_mod.ROOT
        old_bus_root = bus_mod.ROOT
        old_org = bus_mod.ORG
        old_log = bus_mod.ACTION_LOG
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.ROOT = Path(tmp)
            bus_mod.ROOT = Path(tmp)
            bus_mod.ORG = Path(tmp) / "org"
            bus_mod.ACTION_LOG = bus_mod.ORG / "ACTION_LOG.md"
            try:
                # Single-step job (no handoff metadata)
                receipt1 = {
                    "id": "job1",
                    "preset": "builder",
                    "message": "Fix the bug",
                    "handoff": ["cos", "builder"],
                    "engine": "OpenCode",
                }
                result1 = close_work_job(receipt1, "Bug fixed")
                self.assertIn("handoff_path", result1)
                # Multi-step chain should add handoff metadata
                self.assertEqual(result1.get("handoff_from"), "cos")
                self.assertEqual(result1.get("handoff_to"), "builder")
                
                # Another multi-step: think → builder
                receipt2 = {
                    "id": "job2",
                    "preset": "builder",
                    "message": "Implement the design",
                    "handoff": ["think", "builder"],
                    "engine": "OpenCode",
                }
                result2 = close_work_job(receipt2, "Implementation ready")
                self.assertEqual(result2.get("handoff_from"), "think")
                self.assertEqual(result2.get("handoff_to"), "builder")
            finally:
                store_mod.ROOT = old_root
                bus_mod.ROOT = old_bus_root
                bus_mod.ORG = old_org
                bus_mod.ACTION_LOG = old_log


if __name__ == "__main__":
    unittest.main()
