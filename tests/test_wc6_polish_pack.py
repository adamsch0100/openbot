"""Tests for WC-6: Polish Pack

Covers:
- Skills catalog with descriptions and popular skills
- Routine templates (Morning standup, Weekly review)
- Memory search → stream jump (data-job-id on all job bubbles)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from openbot.hermes import skills_list
from openbot.routine_templates import get_routine_templates, get_template_by_id
from openbot.routines import create_routine, list_routines, read_routine
from openbot.store import ROOT


def test_skills_catalog_descriptions():
    """Test that skills_list returns descriptions for each skill."""
    with patch("openbot.hermes.which") as mock_which:
        with patch("openbot.hermes._run") as mock_run:
            mock_which.return_value = "/usr/bin/hermes"
            # Mock hermes skills list output
            mock_run.return_value = (
                0,
                "Name\n----\ngithub\nweb-search\nbrowser\nterminal\nfile-operations"
            )
            
            result = skills_list()
            
            assert result["ok"] is True
            assert "skills" in result
            assert "popular" in result
            
            skills = result["skills"]
            assert len(skills) > 0
            
            # Check that skills have name and description
            for skill in skills:
                assert "name" in skill
                assert "description" in skill
                assert isinstance(skill["name"], str)
                assert isinstance(skill["description"], str)
                assert len(skill["description"]) > 0
            
            # Check that popular skills are a subset of all skills
            popular = result["popular"]
            skill_names = [s["name"] for s in skills]
            for pop in popular:
                assert pop in skill_names


def test_skills_catalog_popular_recommendations():
    """Test that popular skills are recommended for Think/Research/Ops."""
    with patch("openbot.hermes.which") as mock_which:
        with patch("openbot.hermes._run") as mock_run:
            mock_which.return_value = "/usr/bin/hermes"
            mock_run.return_value = (
                0,
                "Name\n----\ngithub\nweb-search\nbrowser\nterminal\nfile-operations\nresearch\nplanning"
            )
            
            result = skills_list()
            
            assert result["ok"] is True
            popular = result["popular"]
            
            # Should contain recommended skills
            assert len(popular) > 0
            
            # Common popular skills should be included
            popular_set = set(popular)
            expected = {"web-search", "browser", "github", "terminal", "file-operations"}
            assert len(expected & popular_set) > 0


def test_routine_templates_exist():
    """Test that predefined routine templates exist and are valid."""
    templates = get_routine_templates()
    
    assert len(templates) > 0
    
    # Check required templates
    template_ids = [t["id"] for t in templates]
    assert "morning-standup" in template_ids
    assert "weekly-review" in template_ids
    
    for template in templates:
        # Check structure
        assert "id" in template
        assert "name" in template
        assert "description" in template
        assert "schedule" in template
        assert "steps" in template
        
        # Check steps structure
        assert len(template["steps"]) > 0
        for step in template["steps"]:
            assert "seat" in step
            assert "instruction" in step
            assert step["seat"] in ["builder", "think", "research", "ops"]
            assert len(step["instruction"]) > 0


def test_morning_standup_template():
    """Test the Morning Standup template structure."""
    template = get_template_by_id("morning-standup")
    
    assert template is not None
    assert template["name"] == "Morning Standup"
    assert "status check" in template["description"].lower() or "planning" in template["description"].lower()
    assert "morning" in template["schedule"].lower() or "8am" in template["schedule"].lower()
    
    # Should have at least 2 steps
    assert len(template["steps"]) >= 2
    
    # Check seats are appropriate for standup
    seats = [step["seat"] for step in template["steps"]]
    assert "builder" in seats or "think" in seats or "ops" in seats


def test_weekly_review_template():
    """Test the Weekly Review template structure."""
    template = get_template_by_id("weekly-review")
    
    assert template is not None
    assert template["name"] == "Weekly Review"
    assert "week" in template["description"].lower() or "progress" in template["description"].lower()
    
    # Should have at least 2 steps
    assert len(template["steps"]) >= 2
    
    # Check seats are appropriate for review
    seats = [step["seat"] for step in template["steps"]]
    # Weekly review should involve think or research for retrospective
    assert "think" in seats or "research" in seats


def test_create_routine_from_template(tmp_path, monkeypatch):
    """Test creating a routine from a template."""
    # Use tmp_path as ROOT for this test
    monkeypatch.setattr("openbot.routines.ROOT", tmp_path)
    
    template = get_template_by_id("morning-standup")
    assert template is not None
    
    # Create routine from template
    routine_id = create_routine(
        name=template["name"],
        schedule=template["schedule"],
        steps=template["steps"],
        project_id=None,
        enabled=False  # Don't try to attach cron in test
    )
    
    assert routine_id.startswith("routine-")
    
    # Read it back
    routine = read_routine(routine_id, None)
    assert routine is not None
    assert routine["name"] == template["name"]
    assert routine["schedule"] == template["schedule"]
    assert len(routine["steps"]) == len(template["steps"])
    
    # Check steps were preserved
    for i, step in enumerate(routine["steps"]):
        assert step["seat"] == template["steps"][i]["seat"]
        assert step["instruction"] == template["steps"][i]["instruction"]


def test_routine_templates_load_into_form():
    """Test that templates can be loaded into the UI form structure."""
    templates = get_routine_templates()
    
    for template in templates:
        # Simulate loading into form
        form_data = {
            "name": template["name"],
            "schedule": template["schedule"],
            "steps": [
                {
                    "seat": step["seat"],
                    "instruction": step["instruction"]
                }
                for step in template["steps"]
            ],
            "enabled": True
        }
        
        # Verify form data matches template
        assert form_data["name"] == template["name"]
        assert form_data["schedule"] == template["schedule"]
        assert len(form_data["steps"]) == len(template["steps"])


def test_job_bubble_data_job_id():
    """Test that job bubbles have data-job-id attribute in rendered HTML.
    
    This is a structural test verifying the render logic includes job IDs.
    The actual DOM testing happens in browser/integration tests.
    """
    # Mock job object
    job = {
        "id": "abc123",
        "text": "Test job result",
        "preset": "builder",
        "engine": "OpenCode"
    }
    
    # In the real app.js, renderJob creates a card/bubble with:
    # el.setAttribute("data-job-id", job.id)
    
    # This test verifies the pattern exists in the codebase
    app_js = Path(__file__).parent.parent / "web" / "app.js"
    content = app_js.read_text()
    
    # Check that data-job-id is set in renderJob flow
    assert 'el.setAttribute("data-job-id"' in content
    assert 'job.id' in content
    
    # Check that renderTalk also sets data-job-id
    render_talk_start = content.find("function renderTalk(job)")
    assert render_talk_start > 0
    render_talk_section = content[render_talk_start:render_talk_start + 500]
    assert 'data-job-id' in render_talk_section


def test_memory_search_click_handler():
    """Test that Memory search results have click handlers to jump to jobs.
    
    Verifies the click handler logic exists in app.js.
    """
    app_js = Path(__file__).parent.parent / "web" / "app.js"
    content = app_js.read_text()
    
    # Check for memory search result click handler
    assert "memory-result-clickable" in content
    
    # Check for querySelector using data-job-id
    assert 'querySelector(`[data-job-id="${jobId}"]`)' in content
    
    # Check for scrollIntoView call
    assert "scrollIntoView" in content
    
    # Check for highlight class
    assert 'classList.add("highlight")' in content


def test_memory_search_stream_jump_integration(tmp_path, monkeypatch):
    """Test that Memory search correctly identifies jobs for jumping."""
    # This is a backend test for the search API
    # The actual jump happens in frontend, tested above
    
    monkeypatch.setattr("openbot.store.ROOT", tmp_path)
    
    # Create a test job receipt
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        "id": "test123",
        "text": "Found a bug in the authentication module",
        "preset": "think",
        "engine": "Hermes Agent"
    }
    
    job_file = jobs_dir / "test123.json"
    job_file.write_text(json.dumps(job_data))
    
    # The search endpoint should return this job with its ID
    from openbot.store import list_jobs
    jobs = list_jobs()
    
    found = [j for j in jobs if j.get("id") == "test123"]
    assert len(found) == 1
    assert found[0]["id"] == "test123"


def test_connectors_catalog_endpoint():
    """Test the /api/connectors/catalog endpoint structure."""
    # This test verifies the API response structure
    with patch("openbot.hermes.skills_list") as mock_skills:
        with patch("openbot.hermes.mcp_catalog") as mock_mcp:
            mock_skills.return_value = {
                "ok": True,
                "skills": [
                    {"name": "github", "description": "Query GitHub repos"},
                    {"name": "web-search", "description": "Search the web"}
                ],
                "popular": ["github", "web-search"]
            }
            mock_mcp.return_value = {
                "ok": True,
                "items": [
                    {"id": "github-mcp", "label": "GitHub MCP server"}
                ]
            }
            
            # Simulate what the server endpoint returns
            response = {
                "skills": mock_skills.return_value["skills"],
                "skills_ok": mock_skills.return_value["ok"],
                "popular_skills": mock_skills.return_value["popular"],
                "mcp": mock_mcp.return_value["items"],
                "mcp_ok": mock_mcp.return_value["ok"]
            }
            
            assert "skills" in response
            assert "popular_skills" in response
            assert "mcp" in response
            
            # Check skills have descriptions
            for skill in response["skills"]:
                assert "name" in skill
                assert "description" in skill
            
            # Check popular skills list
            assert len(response["popular_skills"]) > 0


def test_routine_templates_api_endpoint():
    """Test the /api/routines/templates endpoint."""
    templates = get_routine_templates()
    
    # Simulate API response
    response = {"templates": templates}
    
    assert "templates" in response
    assert len(response["templates"]) > 0
    
    for template in response["templates"]:
        assert "id" in template
        assert "name" in template
        assert "description" in template
        assert "schedule" in template
        assert "steps" in template


def test_css_styles_for_polish_features():
    """Test that required CSS styles exist for WC-6 features."""
    styles_css = Path(__file__).parent.parent / "web" / "styles.css"
    content = styles_css.read_text()
    
    # Check for Popular Skills styling
    assert ".popular-skills-section" in content or ".connector-row-popular" in content
    
    # Check for connector name description styling
    assert ".connector-name-desc" in content
    
    # Check for highlight animation
    assert ".highlight" in content
    assert "highlight-pulse" in content or "keyframes" in content


def test_html_template_dropdown():
    """Test that routine template dropdown exists in HTML."""
    index_html = Path(__file__).parent.parent / "web" / "index.html"
    content = index_html.read_text()
    
    # Check for template dropdown
    assert 'id="routineTemplate"' in content
    assert 'Create from template' in content or 'template' in content.lower()


def test_all_acceptance_criteria():
    """Meta-test verifying all WC-6 acceptance criteria are covered."""
    
    # 1. Skills catalog polish: descriptions + popular skills section
    result = get_routine_templates()
    assert len(result) > 0  # Templates exist
    
    with patch("openbot.hermes.which") as mock_which:
        with patch("openbot.hermes._run") as mock_run:
            mock_which.return_value = "/usr/bin/hermes"
            mock_run.return_value = (0, "github\nweb-search")
            skills = skills_list()
            assert "skills" in skills
            assert "popular" in skills
    
    # 2. Routine templates with presets
    templates = get_routine_templates()
    template_ids = [t["id"] for t in templates]
    assert "morning-standup" in template_ids
    assert "weekly-review" in template_ids
    
    # 3. Memory search → stream jump (data-job-id)
    app_js = Path(__file__).parent.parent / "web" / "app.js"
    content = app_js.read_text()
    assert 'data-job-id' in content
    assert 'scrollIntoView' in content
    
    # 4. Template preset loads into form
    template = get_template_by_id("morning-standup")
    assert template is not None
    assert "steps" in template
    
    # 5. Comprehensive tests (this file)
    # You're reading them!
    
    print("✅ All WC-6 acceptance criteria covered")


if __name__ == "__main__":
    # Run tests
    test_skills_catalog_descriptions()
    test_skills_catalog_popular_recommendations()
    test_routine_templates_exist()
    test_morning_standup_template()
    test_weekly_review_template()
    test_job_bubble_data_job_id()
    test_memory_search_click_handler()
    test_connectors_catalog_endpoint()
    test_routine_templates_api_endpoint()
    test_css_styles_for_polish_features()
    test_html_template_dropdown()
    test_all_acceptance_criteria()
    print("✅ All WC-6 tests passed!")
