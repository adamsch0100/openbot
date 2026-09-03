"""Product suite: chat stays simple, engines stay wired, UI stays Grok-light."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CheapChatTests(unittest.TestCase):
    def test_ceo_talk_never_spends_think(self):
        from unittest.mock import patch

        from openbot.router import handle, route_for_node

        self.assertEqual(route_for_node("hello", "ceo"), ["cos"])
        self.assertEqual(route_for_node("hey, what should we do today?", "ceo"), ["cos"])
        self.assertEqual(route_for_node("can you help with ticket 1", "openbot"), ["cos"])
        self.assertEqual(route_for_node("think hard about ticket 1", "ceo"), ["think"])
        self.assertEqual(route_for_node("Change the code: add a footer", "ceo"), ["builder"])
        self.assertEqual(route_for_node("just a simple test", "ceo"), ["cos"])
        self.assertEqual(route_for_node("open opencode and create a md file", "ceo"), ["builder"])
        self.assertEqual(route_for_node("Look at this site https://example.com", "ceo"), ["research"])
        self.assertEqual(route_for_node("Every morning ping the board", "ceo"), ["ops"])

        with patch("openbot.router.seated_or_auto", return_value=""), patch(
            "openbot.router.recommended_chat_id", return_value=""
        ):
            job = handle("hello", project_id="openbot")
        self.assertEqual(job.get("engine"), "board")
        self.assertEqual(job.get("preset"), "cos")
        self.assertTrue(job.get("talk"))
        self.assertFalse(job.get("keep_going"))
        self.assertIn("report to Chief of Staff", job.get("text") or "")
        self.assertIn("openbot", job.get("text") or "")
        self.assertNotIn("session_id", (job.get("text") or "").lower())
        self.assertNotIn("Resumed session", job.get("text") or "")

    def test_status_is_index_only_not_a_dump(self):
        from openbot.router import SKILL, skills_reply, status_reply

        index = "Now: ticket 1\nLast: builder\nNext: folder then diff\nBlocker: —\n## Law\nsecret"
        status = status_reply(index, "What is going on?", "openbot")
        self.assertIn("ticket 1", status)
        self.assertIn("Last: builder", status)
        self.assertNotIn("secret", status)
        talk = status_reply(index, "what should we do?", "openbot")
        self.assertIn("openbot", talk)
        self.assertNotIn("## Law", talk)
        self.assertNotIn("ticket 1", talk)
        self.assertNotIn("Ticket 1", talk)
        self.assertNotIn("What would you like to do?", talk)
        self.assertTrue(SKILL.search("how do I add a skill"))
        self.assertIn("Settings → Models", skills_reply())


class EngineWireTests(unittest.TestCase):
    def test_hermes_and_opencode_read_utf8(self):
        hermes = (ROOT / "openbot" / "hermes.py").read_text(encoding="utf-8")
        router = (ROOT / "openbot" / "router.py").read_text(encoding="utf-8")
        self.assertIn('encoding": "utf-8"', hermes)
        self.assertIn('errors": "replace"', hermes)
        self.assertIn("PYTHONUTF8", hermes)
        self.assertIn('encoding": "utf-8"', router)
        self.assertIn('errors": "replace"', router)

    def test_detect_finds_official_binaries(self):
        from openbot.detect import detect

        engines = detect()
        self.assertTrue(engines["board"]["present"])
        self.assertTrue(engines["hermes"]["present"], engines["hermes"])
        self.assertTrue(engines["opencode"]["present"], engines["opencode"])
        self.assertNotIn("nousresearch/hermes-agent", str(ROOT / "openbot"))

    def test_help_commands_return(self):
        from openbot.detect import which

        for name in ("hermes", "opencode"):
            path = which(name)
            self.assertTrue(path, f"{name} missing")
            ran = subprocess.run(
                [path, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=25,
            )
            blob = (ran.stdout or "") + (ran.stderr or "")
            self.assertTrue(blob.strip(), f"{name} --help was empty, code={ran.returncode}")

    def test_chat_packet_stays_conversational(self):
        from openbot.hermes import chat_packet, clean_hermes_text

        packet = chat_packet("openbot CEO", "Now: ok", "hello")
        self.assertIn("You are the openbot CEO", packet)
        self.assertIn("report to Chief of Staff", packet)
        self.assertIn("Reply like a person", packet)
        self.assertNotIn("Write a short RESULT", packet)
        self.assertIn("STAFF", packet)
        self.assertIn("Now: ok", packet)
        self.assertIn("Do not mention Now, Last, Next", packet)
        self.assertNotIn("four lines", packet)
        empty = chat_packet("Chief of Staff", "", "hello")
        self.assertNotIn("STAFF", empty)
        self.assertIn("triage", empty.lower())
        self.assertIn("specialist", empty.lower())
        cleaned = clean_hermes_text(
            "\x1b[1mWarning: Unknown toolsets: none\x1b[0m\n"
            "No usable credentials found for provider 'opencode-zen'. Set OPENCODE_ZEN_API_KEY.\n"
            "Hello there."
        )
        self.assertEqual(cleaned, "Hello there.")


class SimpleBoardUiTests(unittest.TestCase):
    def test_one_send_stop_and_enter(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="sendBtn"', html)
        self.assertIn('id="workHint"', html)
        self.assertNotIn('id="stopBtn"', html)
        self.assertIn("thinkingBubble", js)
        self.assertIn("event-stream", js)
        self.assertIn("if (job) break;", js)
        self.assertIn("watchdog", js)
        self.assertIn('event.key !== "Enter"', js)
        self.assertIn('textContent = live ? "Stop" : "Send"', js)
        self.assertIn("think-pulse", css)
        self.assertIn("stage-opencode", html)
        self.assertIn("stage-hermes", html)
        self.assertIn('id="composerWho"', html)
        self.assertIn("function syncComposerWho", js)
        self.assertNotIn("Name a helper", js)
        self.assertNotIn("data-add-helper", js)
        self.assertIn("unreadLanes", js)
        self.assertIn("function scrollChatBottom", js)
        self.assertIn("idle: true", js)
        self.assertIn("/chat?resume=", js)
        self.assertIn("--isolated", (ROOT / "openbot" / "launch.py").read_text(encoding="utf-8"))
        self.assertIn("def home_summary", (ROOT / "openbot" / "channel.py").read_text(encoding="utf-8"))
        self.assertIn("_kill_port", (ROOT / "openbot" / "launch.py").read_text(encoding="utf-8"))
        self.assertIn("color-scheme: dark", css)
        self.assertIn("appearance: none", css)
        self.assertIn('id="routeToggle"', html)
        self.assertIn("function setRoute", js)
        self.assertIn("function paintLanes", js)
        self.assertIn("function applyLaneFilter", js)
        self.assertIn("function startReply", js)
        self.assertIn('data-lane="all"', html)
        self.assertIn("reply-chip", css)
        self.assertIn("bubble-quote", css)
        self.assertNotIn('id="chatModel"', html)
        self.assertNotIn("await loadThread(name)", js)
        self.assertIn("extras.telegram", js)
        self.assertIn("def session_hint", (ROOT / "openbot" / "channel.py").read_text(encoding="utf-8"))
        self.assertIn("min(44rem, 100%)", css)
        self.assertIn("chat-shell", css)
        self.assertIn("overflow-wrap: anywhere", css)
        self.assertIn("gate-line", css)
        self.assertIn("action gate", js)
        self.assertIn("handoff_path", js)

    def test_credit_stays_on_the_board(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Not affiliated with, sponsored by, or endorsed by those projects.", html)
        self.assertIn("Hermes Agent", html)
        self.assertIn("OpenCode", html)


class SeamlessTogetherTests(unittest.TestCase):
    def test_classify_splits_chat_code_and_ops(self):
        from openbot.router import classify, route_plan

        self.assertEqual(classify("hello"), "cos")
        self.assertEqual(classify("Change the code: add a footer"), "builder")
        self.assertEqual(route_plan("Change the code after looking at https://example.com/docs", None), ["research", "builder"])

    def test_one_chat_per_who_not_per_mode(self):
        from openbot.router import handle
        from openbot.threadstore import thread_key

        self.assertEqual(thread_key(None, None), "cos")
        self.assertEqual(thread_key("openbot", None), "org:openbot:ceo")
        seen = []

        def progress(text, lane=None):
            seen.append((str(text), lane))

        handle("What is going on?", project_id="openbot", on_progress=progress)
        self.assertTrue(seen)
        blob = " ".join(text for text, _lane in seen)
        self.assertNotIn("DeepSeek", blob)
        self.assertFalse(any("Chief of Staff ·" in text for text, _lane in seen))
        src = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("elif preset in THREAD_PRESETS", src)

    def test_health_shape_names_engines(self):
        from openbot.detect import detect
        from openbot.server import CREDIT

        engines = detect()
        self.assertIn("Hermes Agent", engines["hermes"]["name"])
        self.assertIn("OpenCode", engines["opencode"]["name"])
        self.assertIn("Nous Research", CREDIT)
        self.assertIn("Anomaly", CREDIT)


if __name__ == "__main__":
    unittest.main()
