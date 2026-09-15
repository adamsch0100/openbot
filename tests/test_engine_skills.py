"""Engine skills land in job packets; Cos stays blind."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import openbot.playskills as skills_mod


class EngineSkillPacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._org = skills_mod.ORG
        self._root = skills_mod.SKILLS_ROOT
        skills_mod.ORG = self.home / "org"
        skills_mod.SKILLS_ROOT = skills_mod.ORG / "skills"
        # Seed from DOGFOOD into the temp skills root.
        skills_mod.seed_dogfood_skills()

    def tearDown(self):
        skills_mod.ORG = self._org
        skills_mod.SKILLS_ROOT = self._root
        self.tmp.cleanup()

    def test_cos_gets_no_engine_skills(self):
        packet = skills_mod.skill_packet("openbot", "cos")
        self.assertNotIn("engine-hermes", packet)
        self.assertNotIn("engine-opencode", packet)
        self.assertNotIn("hermes-tool-discipline", packet)

    def test_think_gets_hermes_menu_and_discipline(self):
        packet = skills_mod.skill_packet("saa-homes", "think")
        self.assertIn("SKILL engine-hermes", packet)
        self.assertIn("SKILL hermes-tool-discipline", packet)
        self.assertNotIn("SKILL engine-opencode", packet)
        # Menu before domain craft order: engine skills lead the packet.
        hermes_at = packet.index("SKILL engine-hermes")
        discipline_at = packet.index("SKILL hermes-tool-discipline")
        self.assertLess(hermes_at, discipline_at)

    def test_ops_and_research_get_hermes_skills(self):
        for preset in ("ops", "research"):
            packet = skills_mod.skill_packet("openbot", preset)
            self.assertIn("SKILL engine-hermes", packet, preset)
            self.assertIn("SKILL hermes-tool-discipline", packet, preset)

    def test_builder_gets_opencode_menu_only(self):
        packet = skills_mod.skill_packet("openbot", "builder")
        self.assertIn("SKILL engine-opencode", packet)
        self.assertNotIn("SKILL engine-hermes", packet)
        self.assertNotIn("SKILL hermes-tool-discipline", packet)
        self.assertIn("diff card", packet.lower())

    def test_engine_skills_exist_on_disk_shape(self):
        for name in ("engine-hermes", "engine-opencode", "hermes-tool-discipline"):
            skill = skills_mod.read_skill(name)
            self.assertIsNotNone(skill, name)
            body = (skill or {}).get("body") or ""
            self.assertIn("## Owns", body, name)
            self.assertIn("## Stopline", body, name)
            self.assertIn("## Steps", body, name)


if __name__ == "__main__":
    unittest.main()
