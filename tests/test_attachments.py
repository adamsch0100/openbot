"""Attachment feature tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openbot.server import _save_attachments, _chat_context
from openbot.router import handle, _packet_extra


class AttachmentTests(unittest.TestCase):
    def test_save_attachments_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import openbot.store
            old_root = openbot.store.ROOT
            try:
                openbot.store.ROOT = Path(tmpdir)
                files = [
                    {"filename": "test.txt", "content": b"hello world"},
                    {"filename": "image.jpg", "content": b"\xff\xd8\xff\xe0"},
                ]
                saved, err = _save_attachments(files, None)
                self.assertIsNone(err)
                self.assertEqual(len(saved), 2)
                self.assertEqual(saved[0]["filename"], "test.txt")
                self.assertEqual(saved[0]["size"], 11)
                self.assertEqual(saved[0]["id"], "staff/test.txt")
                self.assertTrue(Path(saved[0]["path"]).exists())
                self.assertEqual(saved[1]["filename"], "image.jpg")
                self.assertEqual(saved[1]["size"], 4)
            finally:
                openbot.store.ROOT = old_root

    def test_chat_context_includes_attachments(self):
        data = {"message": "test", "preset": "cos"}
        files = [{"filename": "doc.pdf", "content": b"fake pdf"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            import openbot.store
            old_root = openbot.store.ROOT
            try:
                openbot.store.ROOT = Path(tmpdir)
                message, folder, preset, pid, wid, attachments = _chat_context(data, files)
                self.assertEqual(message, "test")
                self.assertEqual(len(attachments), 1)
                self.assertEqual(attachments[0]["filename"], "doc.pdf")
                self.assertEqual(attachments[0]["id"], "staff/doc.pdf")
            finally:
                openbot.store.ROOT = old_root

    def test_packet_extra_includes_attachments(self):
        attachments = [
            {"filename": "spec.md", "path": "/tmp/spec.md", "id": "staff/spec.md", "size": 1024},
            {"filename": "photo.jpg", "path": "/tmp/photo.jpg", "id": "staff/photo.jpg", "size": 2048},
        ]
        extra = _packet_extra(None, attachments=attachments)
        self.assertIn("ATTACHMENTS:", extra)
        self.assertIn("spec.md", extra)
        self.assertIn("photo.jpg", extra)
        self.assertIn("/tmp/spec.md", extra)
        self.assertIn("/tmp/photo.jpg", extra)

    def test_router_handle_accepts_attachments(self):
        attachments = [{"filename": "test.txt", "path": "/tmp/test.txt", "id": "staff/test.txt", "size": 10}]
        result = handle(
            "status please",
            attachments=attachments,
        )
        self.assertIn("id", result)
        self.assertIn("engine", result)
        self.assertEqual(result["engine"], "board")

    def test_save_attachments_rejects_oversized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import openbot.store
            old_root = openbot.store.ROOT
            try:
                openbot.store.ROOT = Path(tmpdir)
                files = [{"filename": "huge.txt", "content": b"x" * (51 * 1024 * 1024)}]
                saved, err = _save_attachments(files, None)
                self.assertIsNotNone(err)
                self.assertIn("too large", err.lower())
                self.assertEqual(len(saved), 0)
            finally:
                openbot.store.ROOT = old_root

    def test_save_attachments_rejects_disallowed_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import openbot.store
            old_root = openbot.store.ROOT
            try:
                openbot.store.ROOT = Path(tmpdir)
                files = [{"filename": "bad.exe", "content": b"fake exe"}]
                saved, err = _save_attachments(files, None)
                self.assertIsNotNone(err)
                self.assertIn("not allowed", err.lower())
                self.assertEqual(len(saved), 0)
            finally:
                openbot.store.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
