"""Tests for Builder validation gate."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from openbot.gitutil import snapshot
from openbot.router import decide_diff
from openbot.store import write_job
from openbot.validator import validate_changes
import openbot.store as store_mod
import openbot.router as router_mod


class ValidationTests(unittest.TestCase):
    def test_validate_python_syntax_pass(self):
        """Python file with valid syntax passes validation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["app.py"])
            self.assertTrue(ok)
            self.assertIn("validation passed", detail)

    def test_validate_python_syntax_fail(self):
        """Python file with syntax error fails validation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("def broken(\n    return\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["bad.py"])
            self.assertFalse(ok)
            self.assertIn("bad.py", detail)

    def test_validate_javascript_syntax_pass(self):
        """JavaScript file with valid syntax passes validation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.js").write_text("function hello() { return 'world'; }\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["app.js"])
            # Only fails if node is on PATH
            if detail and "bad.js" not in detail:
                self.assertTrue(ok)

    def test_validate_javascript_syntax_fail(self):
        """JavaScript file with syntax error fails validation if node available."""
        try:
            subprocess.run(["node", "--version"], capture_output=True, check=True)
            node_present = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            node_present = False

        if not node_present:
            self.skipTest("node not on PATH")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.js").write_text("function broken( { return }\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["bad.js"])
            self.assertFalse(ok)
            self.assertIn("bad.js", detail)

    def test_validate_extracts_changed_files_from_diff(self):
        """Changed files are extracted from git diff output."""
        diff = """diff --git a/app.py b/app.py
index abc123..def456 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
 def hello():
-    return 'old'
+    return 'new'
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def hello():\n    return 'new'\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), diff, [])
            self.assertTrue(ok)

    def test_validation_skips_missing_files(self):
        """Validation skips files that don't exist (e.g. deleted files)."""
        diff = """diff --git a/deleted.py b/deleted.py
deleted file mode 100644
--- a/deleted.py
+++ /dev/null
"""
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = validate_changes(str(tmp), diff, [])
            self.assertTrue(ok)

    def test_decide_diff_blocks_accept_on_validation_failure(self):
        """Accept is blocked when validation fails."""
        old_jobs = store_mod.JOBS
        old_brains = store_mod.BRAINS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                store_mod.JOBS = tmp_path
                store_mod.BRAINS = tmp_path
                (tmp_path / "INDEX.md").write_text("Now: test\n", encoding="utf-8")
                
                root = tmp_path / "work"
                root.mkdir()
                
                # Create git repo
                subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "test@local"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
                
                # Create a valid file and commit
                (root / "app.py").write_text("def hello():\n    pass\n", encoding="utf-8")
                subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
                
                # Take snapshot
                snap = snapshot(str(root))
                
                # Introduce syntax error
                (root / "app.py").write_text("def broken(\n    return\n", encoding="utf-8")
                diff_text = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True
                ).stdout
                
                # Write job with pending diff
                write_job({
                    "id": "abc123",
                    "at": "2026-09-05T00:00:00Z",
                    "preset": "builder",
                    "engine": "OpenCode",
                    "folder": str(root),
                    "diff": diff_text,
                    "untracked": [],
                    "diff_pending": True,
                    "git_snapshot": snap,
                })
                
                # Try to accept without force - should fail
                result = decide_diff("abc123", accept=True, force=False)
                self.assertFalse(result.get("ok"))
                self.assertTrue(result.get("validation_failed"))
                self.assertIn("app.py", result.get("validation_error") or "")
        finally:
            store_mod.JOBS = old_jobs
            store_mod.BRAINS = old_brains

    def test_decide_diff_force_accept_bypasses_validation(self):
        """Force Accept bypasses validation and accepts the diff."""
        old_jobs = store_mod.JOBS
        old_brains = store_mod.BRAINS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                store_mod.JOBS = tmp_path
                store_mod.BRAINS = tmp_path
                (tmp_path / "INDEX.md").write_text("Now: test\n", encoding="utf-8")
                
                root = tmp_path / "work"
                root.mkdir()
                
                # Create git repo
                subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "test@local"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
                
                # Create a valid file and commit
                (root / "app.py").write_text("def hello():\n    pass\n", encoding="utf-8")
                subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
                
                # Take snapshot
                snap = snapshot(str(root))
                
                # Introduce syntax error
                (root / "app.py").write_text("def broken(\n    return\n", encoding="utf-8")
                diff_text = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True
                ).stdout
                
                # Write job with pending diff
                write_job({
                    "id": "def456",
                    "at": "2026-09-05T00:00:00Z",
                    "preset": "builder",
                    "engine": "OpenCode",
                    "folder": str(root),
                    "diff": diff_text,
                    "untracked": [],
                    "diff_pending": True,
                    "git_snapshot": snap,
                })
                
                # Force accept - should succeed despite syntax error
                result = decide_diff("def456", accept=True, force=True)
                self.assertTrue(result.get("ok"))
                self.assertTrue(result.get("accepted"))
                self.assertFalse(result.get("validation_failed"))
        finally:
            store_mod.JOBS = old_jobs
            store_mod.BRAINS = old_brains

    def test_validation_passes_with_valid_changes(self):
        """Accept succeeds when validation passes."""
        old_jobs = store_mod.JOBS
        old_brains = store_mod.BRAINS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                store_mod.JOBS = tmp_path
                store_mod.BRAINS = tmp_path
                (tmp_path / "INDEX.md").write_text("Now: test\n", encoding="utf-8")
                
                root = tmp_path / "work"
                root.mkdir()
                
                # Create git repo
                subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "test@local"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
                
                # Create a valid file and commit
                (root / "app.py").write_text("def hello():\n    pass\n", encoding="utf-8")
                subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
                
                # Take snapshot
                snap = snapshot(str(root))
                
                # Make valid change
                (root / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
                diff_text = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True
                ).stdout
                
                # Write job with pending diff
                write_job({
                    "id": "feed99",
                    "at": "2026-09-05T00:00:00Z",
                    "preset": "builder",
                    "engine": "OpenCode",
                    "folder": str(root),
                    "diff": diff_text,
                    "untracked": [],
                    "diff_pending": True,
                    "git_snapshot": snap,
                })
                
                # Accept should succeed
                result = decide_diff("feed99", accept=True, force=False)
                self.assertTrue(result.get("ok"))
                self.assertTrue(result.get("accepted"))
                self.assertFalse(result.get("validation_failed"))
        finally:
            store_mod.JOBS = old_jobs
            store_mod.BRAINS = old_brains

    def test_validation_handles_untracked_files(self):
        """Validation checks syntax of new untracked files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "new.py").write_text("def new():\n    return True\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["new.py"])
            self.assertTrue(ok)
            
            (root / "bad_new.py").write_text("def bad(\n    return\n", encoding="utf-8")
            ok, detail = validate_changes(str(root), "", ["bad_new.py"])
            self.assertFalse(ok)
            self.assertIn("bad_new.py", detail)

    def test_validation_caps_error_output(self):
        """Validation caps error output to prevent UI spam."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create many files with errors
            for i in range(15):
                (root / f"bad{i}.py").write_text("def bad(\n    return\n", encoding="utf-8")
            
            ok, detail = validate_changes(str(root), "", [f"bad{i}.py" for i in range(15)])
            self.assertFalse(ok)
            # Should mention it capped
            self.assertIn("more errors", detail)


if __name__ == "__main__":
    unittest.main()
