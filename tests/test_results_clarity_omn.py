"""String guards: Outcome · Meaning · Next + draft-line guard (SAA Results clarity P0)."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "web" / "app.js"
HTML = ROOT / "web" / "index.html"


class ResultsClarityOmnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_helpers_exist(self):
        self.assertIn("function outcomeMeaningNext", self.js)
        self.assertIn("function omnPrimaryLine", self.js)
        self.assertIn("function gateLineKind", self.js)
        self.assertIn("function draftFileLabel", self.js)
        self.assertIn("function jobIsBusySkip", self.js)
        # Hotspots covered
        self.assertIn("appendWorkDetails", self.js)
        self.assertIn("renderReportCard", self.js)
        self.assertIn("settleLive", self.js)
        self.assertIn("renderTalk", self.js)
        self.assertIn("omn-card", self.js)

    def test_draft_line_guard_no_false_spam(self):
        self.assertNotIn("A draft is ready in files. Nothing public yet.", self.js)
        self.assertIn("Draft ready · ${file}. Nothing published.", self.js)
        self.assertIn("Review draft.", self.js)
        # Guard comment / only real draft
        self.assertIn("Draft-line guard", self.js)
        self.assertIn("never OPS_OK / fail spam", self.js)

    def test_before_after_think_anthropic(self):
        self.assertIn("Failed · Think couldn't start (blocked Anthropic)", self.js)
        self.assertIn("use OpenCode Go pool · Retry", self.js)

    def test_before_after_ops_busy(self):
        self.assertIn("Skipped · Hermes already busy", self.js)
        self.assertIn("wait or stop the other session", self.js)

    def test_before_after_anthropic_401_policy(self):
        self.assertIn("Failed · Auth (Anthropic blocked by policy)", self.js)
        self.assertIn("confirm Go/OpenRouter in Settings", self.js)

    def test_render_report_card_not_null_stub(self):
        # Must not early-return null before building OMN
        block = self.js[self.js.find("function renderReportCard") : self.js.find("function renderHandoffCard")]
        self.assertNotIn("return null;\n  if (!job)", block)
        self.assertIn("report-omn", block)
        self.assertIn("outcomeMeaningNext(job)", block)

    def test_cache_bust(self):
        self.assertIn("app.js?v=153", self.html)
        self.assertIn("styles.css?v=153", self.html)

    def test_node_syntax(self):
        node = __import__("shutil").which("node")
        if not node:
            self.skipTest("node not installed")
        checked = subprocess.run(
            [node, "--check", str(JS)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)


class ResultsClarityOmnRuntime(unittest.TestCase):
    """Tiny Node harness for before/after outcomeMeaningNext examples."""

    def test_omn_examples_via_node(self):
        node = __import__("shutil").which("node")
        if not node:
            self.skipTest("node not installed")
        script = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync("web/app.js", "utf8");
const start = src.indexOf("function humanFailReason");
const end = src.indexOf("function failFingerprint");
const slice = src.slice(start, end);
const sandbox = {
  PRESET_ENGINE: { cos: "board", think: "Hermes Agent", ops: "Hermes Agent", builder: "OpenCode" },
  cleanBotText: (t) => String(t || "").replace(/\b(?:THINK_OK|OPS_OK)\b/g, "").trim(),
  failKindFromBlob: (blob) => {
    const low = String(blob || "").toLowerCase();
    if (/\b401\b|unauthorized|anthropic|x-api-key/.test(low)) return "key";
    if (/busy|already running/.test(low)) return "transient";
    return "unknown";
  },
  failWhyLine: (k, r) => r || "",
  opaqueLaneOk: (t) => !String(t || "").trim() || /^(?:THINK_OK|OPS_OK)$/i.test(String(t || "").trim()),
  cronFailBlob: () => "",
  console
};
// jobIsFailed used by gateLineKind / outcomeMeaningNext — provide stub until later def
sandbox.jobIsFailed = function (job) {
  if (!job || job.stopped) return false;
  if (sandbox.jobIsBusySkip && sandbox.jobIsBusySkip(job)) return false;
  const blocker = String(job.blocker || "").trim();
  if (blocker && blocker !== "—" && blocker !== "ok") return true;
  return /fail|error/i.test(String(job.status || job.last_status || ""));
};
vm.createContext(sandbox);
vm.runInContext(slice + "\nthis.outcomeMeaningNext = outcomeMeaningNext;\nthis.jobIsBusySkip = jobIsBusySkip;\nthis.gateLineKind = gateLineKind;", sandbox);

const think = sandbox.outcomeMeaningNext({
  preset: "think",
  blocker: "hermes think exited 1",
  text: "Anthropic blocked — Think couldn't start",
  engine: "Hermes Agent",
  gate: { label: "reversible · drafts and local files", action: "allow" }
});
if (think.outcome !== "Failed · Think couldn't start (blocked Anthropic)") throw new Error("think outcome: " + think.outcome);
if (think.next !== "use OpenCode Go pool · Retry") throw new Error("think next: " + think.next);
if (think.draftLine) throw new Error("think must not draft");

const busy = sandbox.outcomeMeaningNext({
  preset: "ops",
  text: "Hermes already busy — live owner session",
  blocker: "session busy",
  engine: "Hermes Agent",
  gate: { label: "ops · silent on success", action: "allow" }
});
if (busy.outcome !== "Skipped · Hermes already busy") throw new Error("busy outcome: " + busy.outcome);
if (busy.next !== "wait or stop the other session") throw new Error("busy next: " + busy.next);
if (busy.draftLine) throw new Error("busy must not draft");

const auth = sandbox.outcomeMeaningNext({
  preset: "think",
  text: "Anthropic API 401 Unauthorized blocked by policy",
  blocker: "401",
  engine: "Hermes Agent",
  gate: { label: "stopped", action: "blocked" }
});
if (auth.outcome !== "Failed · Auth (Anthropic blocked by policy)") throw new Error("auth outcome: " + auth.outcome);
if (auth.next !== "confirm Go/OpenRouter in Settings") throw new Error("auth next: " + auth.next);

const draft = sandbox.outcomeMeaningNext({
  preset: "builder",
  text: "patched footer",
  diff_pending: true,
  diff: "diff --git a/x",
  gate: { label: "action gate · Accept / Reject the diff", action: "approval" }
});
if (!/^Draft ready · /.test(draft.outcome)) throw new Error("draft outcome: " + draft.outcome);
if (draft.meaning !== "Nothing published.") throw new Error("draft meaning");
if (draft.next !== "Review draft.") throw new Error("draft next: " + draft.next);
if (!draft.draftLine.includes("Nothing published.")) throw new Error("draft line");

const opsOk = sandbox.outcomeMeaningNext({
  preset: "ops",
  text: "OPS_OK",
  gate: { label: "ops · silent on success", action: "allow" }
});
if (opsOk.draftLine) throw new Error("OPS_OK must not get draft line");
console.log("omn-ok");
"""
        proc = subprocess.run(
            [node, "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("omn-ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
