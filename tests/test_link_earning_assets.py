"""Link-earning skill + SAA SEO addendum (citation hub / glossary)."""

from __future__ import annotations

import unittest

from openbot.playskills import parse_skill, skill_packet
from openbot.store import ROOT


class LinkEarningAssets(unittest.TestCase):
    def test_skill_file_is_original_playbook(self):
        path = ROOT / "org" / "skills" / "link-earning-assets" / "SKILL.md"
        self.assertTrue(path.is_file(), "board skill must live in org/skills")
        text = path.read_text(encoding="utf-8")
        skill = parse_skill(text, "link-earning-assets")
        self.assertEqual(skill["name"], "link-earning-assets")
        body = (skill.get("body") or "").lower()
        self.assertIn("citation hub", body)
        self.assertIn("glossary", body)
        self.assertIn("first publisher", body)
        self.assertIn("fair housing", body)
        self.assertIn("do not invent", body)
        self.assertIn("do not unzip, vendor, or redistribute", body)
        self.assertIn("/housing-statistics/", body)
        self.assertNotIn("~/.claude/skills", text)

    def test_saa_think_packet_includes_skill(self):
        packet = skill_packet("saa-homes", "think")
        self.assertIn("SKILL link-earning-assets", packet)
        self.assertIn("Citation gate", packet)
        other = skill_packet("openbot", "think")
        self.assertNotIn("SKILL link-earning-assets", other)

    def test_saa_seo_plan_and_index(self):
        plan = ROOT / "org" / "projects" / "saa-homes" / "SEO-LINK-ASSETS.md"
        self.assertTrue(plan.is_file())
        text = plan.read_text(encoding="utf-8").lower()
        self.assertIn("pillar 5", text)
        self.assertIn("citation hub", text)
        self.assertIn("/glossary/", text)
        self.assertIn("zero outreach", text)
        index = (ROOT / "org" / "projects" / "saa-homes" / "INDEX.md").read_text(encoding="utf-8")
        low = index.lower()
        self.assertIn("housing-statistics", low)
        self.assertIn("glossary", low)


if __name__ == "__main__":
    unittest.main()
