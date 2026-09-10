"""#92 dogfood: gateway/start must not UnboundLocalError on project_tools."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class GatewayStartUnboundTests(unittest.TestCase):
    def test_do_post_has_no_local_project_tools_import(self):
        src = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "do_POST":
                        for sub in ast.walk(item):
                            if isinstance(sub, ast.ImportFrom) and sub.module == "org":
                                names = {a.name for a in sub.names}
                                self.assertNotIn(
                                    "project_tools",
                                    names,
                                    "local project_tools import shadows module binding",
                                )

    def test_gateway_start_does_not_call_project_tools(self):
        src = (ROOT / "openbot" / "server.py").read_text(encoding="utf-8")
        i = src.find('if path == "/api/hermes/gateway/start":')
        self.assertGreater(i, 0)
        chunk = src[i : i + 900]
        self.assertIn("resolve_ceo_hermes_home", chunk)
        self.assertNotIn("project_tools(", chunk.split("gateway/stop")[0])
        self.assertIn("force", chunk)


if __name__ == "__main__":
    unittest.main()
