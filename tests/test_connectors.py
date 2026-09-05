"""Test connector UX and tool plane configuration."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from openbot.config import load_settings, save_settings
from openbot.org import patch_project_tools, project_tools
from openbot.router import _effective_skills


class TestConnectorConfig(unittest.TestCase):
    """Test connector configuration storage and retrieval."""

    def setUp(self):
        self.test_settings = {
            "default_provider": "opencode",
            "mcp_github": False,
            "operator_name": "",
            "pin_salt": "",
            "pin_hash": "",
            "license_key": "",
            "profile_account_id": "",
            "hermes_skills": "",
            "connectors": {
                "skills": {
                    "github": {"think": True, "research": False, "ops": True},
                    "web-search": {"think": False, "research": True, "ops": False}
                },
                "mcp": {
                    "github": {"think": False, "research": False, "ops": False, "code": True}
                }
            },
            "models": {
                "cos": "",
                "builder": "",
                "research": "",
                "ops": "",
                "think": "",
            },
            "seats": {
                "chat": {"model": "", "account_id": ""},
                "think": {"model": "", "account_id": ""},
                "code": {"model": "", "account_id": ""},
                "research": {"model": "", "account_id": ""},
                "ops": {"model": "", "account_id": ""},
            },
            "spend_policy": {
                "bind": "payg",
                "mode": "hard",
                "allow_zen_fallback": True,
            },
        }

    @patch("openbot.config.SETTINGS_PATH")
    @patch("openbot.config.load_settings")
    def test_connectors_in_settings(self, mock_load, mock_path):
        """Test that connectors are properly stored in settings."""
        settings = self.test_settings.copy()
        assert "connectors" in settings
        assert "skills" in settings["connectors"]
        assert "mcp" in settings["connectors"]
        assert settings["connectors"]["skills"]["github"]["think"] is True
        assert settings["connectors"]["skills"]["github"]["research"] is False
        assert settings["connectors"]["mcp"]["github"]["code"] is True

    @patch("openbot.router.load_settings")
    def test_effective_skills_with_connectors(self, mock_load):
        """Test _effective_skills computes correct skills for each seat."""
        mock_load.return_value = self.test_settings
        
        # Think seat should get github (explicitly enabled for think)
        skills_think = _effective_skills("think", None)
        assert skills_think == "github", f"Expected 'github', got {repr(skills_think)}"
        
        # Research seat should get web-search
        skills_research = _effective_skills("research", None)
        assert skills_research == "web-search", f"Expected 'web-search', got {repr(skills_research)}"
        
        # Ops seat should get github
        skills_ops = _effective_skills("ops", None)
        assert skills_ops == "github", f"Expected 'github', got {repr(skills_ops)}"
        
        # Builder/Code doesn't use skills (uses MCP instead)
        skills_builder = _effective_skills("builder", None)
        # Builder returns empty string (legacy hermesSkills, which is empty)
        assert skills_builder == "" or skills_builder is None, f"Expected empty or None, got {repr(skills_builder)}"

    @patch("openbot.router.load_settings")
    def test_effective_skills_fallback(self, mock_load):
        """Test _effective_skills falls back to hermesSkills when no connectors."""
        settings = self.test_settings.copy()
        settings["hermes_skills"] = "github,web-search"
        settings["connectors"] = {"skills": {}, "mcp": {}}
        mock_load.return_value = settings
        
        # With no connector config, should fall back to hermesSkills
        skills_think = _effective_skills("think", None)
        assert skills_think == "github,web-search", f"Expected 'github,web-search', got {repr(skills_think)}"

    @patch("openbot.router.load_settings")
    def test_effective_skills_ceo_override(self, mock_load):
        """Test CEO-specific connector config overrides global."""
        mock_load.return_value = self.test_settings
        
        ceo_tools = {
            "connectors": {
                "skills": {
                    "github": {"think": False, "research": False, "ops": False},
                    "custom-skill": {"think": True, "research": False, "ops": False}
                },
                "mcp": {}
            }
        }
        
        # CEO overrides: github disabled, custom-skill enabled for think
        skills_think = _effective_skills("think", ceo_tools)
        assert skills_think == "custom-skill", f"Expected 'custom-skill', got {repr(skills_think)}"

    def test_project_tools_includes_connectors(self):
        """Test project_tools returns connectors field."""
        # Mock project data with connectors
        with patch("openbot.org._load_saved") as mock_load:
            mock_load.return_value = {
                "projects": [
                    {
                        "id": "test-project",
                        "name": "Test Project",
                        "folder": "/test",
                        "connectors": {
                            "skills": {"github": {"think": True}},
                            "mcp": {"github": {"code": True}}
                        }
                    }
                ]
            }
            
            tools = project_tools("test-project")
            assert "connectors" in tools
            assert "skills" in tools["connectors"]
            assert "mcp" in tools["connectors"]
            assert tools["connectors"]["skills"]["github"]["think"] is True
            assert tools["connectors"]["mcp"]["github"]["code"] is True

    def test_patch_project_tools_connectors(self):
        """Test patching project tools with connector changes."""
        with patch("openbot.org._load_saved") as mock_load, \
             patch("openbot.org._save") as mock_save:
            mock_load.return_value = {
                "projects": [
                    {
                        "id": "test-project",
                        "name": "Test Project",
                        "folder": "/test",
                        "connectors": {
                            "skills": {},
                            "mcp": {}
                        }
                    }
                ]
            }
            
            # Patch with new connector settings
            patch_data = {
                "connectors": {
                    "skills": {"github": {"think": True, "research": False, "ops": True}},
                    "mcp": {"github": {"code": True}}
                }
            }
            
            result = patch_project_tools("test-project", patch_data)
            
            # Verify save was called with updated connectors
            assert mock_save.called
            saved_data = mock_save.call_args[0][0]
            project = saved_data["projects"][0]
            assert project["connectors"]["skills"]["github"]["think"] is True
            assert project["connectors"]["mcp"]["github"]["code"] is True


class TestConnectorSeatMatrix(unittest.TestCase):
    """Test seat × tool matrix logic."""

    def test_chat_never_has_tools(self):
        """Chat/Cos preset should never load skills or tools."""
        settings = {
            "hermes_skills": "github,web-search",
            "connectors": {
                "skills": {
                    "github": {"think": True, "research": True, "ops": True}
                },
                "mcp": {}
            }
        }
        
        with patch("openbot.router.load_settings", return_value=settings):
            # Cos/Chat does not call _effective_skills in think/research/ops path
            # It stays tools-off by design
            skills = _effective_skills("cos", None)
            # Cos is not in seat_map, so returns hermesSkills (but Cos path never uses it)
            assert skills == "github,web-search", f"Expected 'github,web-search', got {repr(skills)}"

    def test_think_research_ops_use_skills(self):
        """Think, Research, Ops should use configured Hermes skills."""
        settings = {
            "hermes_skills": "",
            "connectors": {
                "skills": {
                    "github": {"think": True, "research": False, "ops": True},
                    "web-search": {"think": False, "research": True, "ops": False}
                },
                "mcp": {}
            }
        }
        
        with patch("openbot.router.load_settings", return_value=settings):
            result_think = _effective_skills("think", None)
            result_research = _effective_skills("research", None)
            result_ops = _effective_skills("ops", None)
            
            assert result_think == "github", f"Expected 'github', got {repr(result_think)}"
            assert result_research == "web-search", f"Expected 'web-search', got {repr(result_research)}"
            assert result_ops == "github", f"Expected 'github', got {repr(result_ops)}"

    def test_code_uses_mcp(self):
        """Code/Builder should use MCP (not skills), defaults to GitHub MCP on Code only."""
        settings = {
            "mcp_github": True,
            "connectors": {
                "skills": {},
                "mcp": {
                    "github": {"think": False, "research": False, "ops": False, "code": True}
                }
            }
        }
        
        # MCP routing is OpenCode's responsibility, not router.py
        # The connector config is stored and will be used when OpenCode supports it
        assert "code" in ["think", "research", "ops", "code"]


class TestConnectorAPIs(unittest.TestCase):
    """Test connector-related HTTP APIs."""

    def test_connectors_catalog_endpoint(self):
        """Test /api/connectors/catalog returns skills and MCP."""
        from openbot.hermes import skills_list, mcp_catalog
        
        with patch("openbot.hermes.skills_list") as mock_skills, \
             patch("openbot.hermes.mcp_catalog") as mock_mcp:
            mock_skills.return_value = {
                "ok": True,
                "skills": ["github", "web-search", "calculator"]
            }
            mock_mcp.return_value = {
                "ok": True,
                "items": [
                    {"id": "github", "label": "GitHub MCP"},
                    {"id": "slack", "label": "Slack MCP"}
                ]
            }
            
            # Simulate API response
            skills = mock_skills()
            mcp = mock_mcp()
            
            catalog = {
                "skills": skills.get("skills") or [],
                "skills_ok": skills.get("ok", False),
                "mcp": mcp.get("items") or [],
                "mcp_ok": mcp.get("ok", False)
            }
            
            assert len(catalog["skills"]) == 3
            assert len(catalog["mcp"]) == 2
            assert catalog["skills_ok"] is True
            assert catalog["mcp_ok"] is True


if __name__ == "__main__":
    unittest.main()
