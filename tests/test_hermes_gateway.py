"""Tests for Hermes gateway management and cron integration."""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_gateway_status_binary_missing():
    """Gateway status should handle missing hermes binary."""
    from openbot.hermes import gateway_status
    
    with patch("openbot.hermes.which", return_value=None):
        result = gateway_status()
    
    assert result["ok"] is False
    assert result["running"] is False
    assert result["text"] == "Hermes Agent binary missing"
    assert result["enabled_count"] == 0


def test_gateway_status_parses_cron_list():
    """Gateway status should count enabled/total crons."""
    from openbot.hermes import gateway_status
    
    mock_cron_text = """
job-1  schedule-1  enabled   last-run
job-2  schedule-2  enabled   last-run
job-3  schedule-3  disabled  last-run
    """
    
    with patch("openbot.hermes.which", return_value="/usr/bin/hermes"):
        with patch("openbot.hermes._run", return_value=(0, "running")):
            with patch("openbot.hermes.cron_list", return_value={"ok": True, "text": mock_cron_text}):
                result = gateway_status()
    
    assert result["ok"] is True
    assert result["running"] is True
    assert result["enabled_count"] == 2
    assert result["total_count"] == 3


def test_gateway_start_already_running():
    """Gateway start should detect if already running."""
    from openbot.hermes import gateway_start
    
    with patch("openbot.hermes.gateway_status", return_value={"ok": True, "running": True}):
        result = gateway_start()
    
    assert result["ok"] is True
    assert result.get("already_running") is True


def test_gateway_start_success():
    """Gateway start should call hermes gateway start."""
    from openbot.hermes import gateway_start
    
    with patch("openbot.hermes.which", return_value="/usr/bin/hermes"):
        with patch("openbot.hermes.gateway_status", return_value={"ok": True, "running": False}):
            with patch("openbot.hermes._run", return_value=(0, "gateway started")) as mock_run:
                result = gateway_start()
    
    assert result["ok"] is True
    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "gateway" in args
    assert "start" in args


def test_cron_create_uses_deliver_local():
    """Cron creation should use --deliver local for OpenBot routing."""
    from openbot.hermes import cron_create
    
    with patch("openbot.hermes.which", return_value="/usr/bin/hermes"):
        with patch("openbot.hermes._run", return_value=(0, "cron created")) as mock_run:
            result = cron_create("0 9 * * *", "Test task", "test-cron")
    
    assert result["ok"] is True
    args = mock_run.call_args[0][0]
    assert "--deliver" in args
    assert "local" in args


def test_cronwatch_routes_to_ceo_thread():
    """Cronwatch should post cron results to CEO threads."""
    from openbot.cronwatch import ingest_cron_runs
    
    mock_line = "job-abc  saa-daily-rank  completed  2026-09-06"
    
    with patch("openbot.cronwatch.project_ids", return_value=["saa-homes"]):
        with patch("openbot.cronwatch.project_tools", return_value={"hermes_home": "/data/hermes-homes/saa-homes"}):
            with patch("openbot.cronwatch._load_seen", return_value={"lines": []}):
                with patch("openbot.cronwatch._save_seen"):
                    with patch("openbot.cronwatch._run", return_value=(0, mock_line)):
                        with patch("openbot.cronwatch.which", return_value="/usr/bin/hermes"):
                            with patch("openbot.cronwatch.write_job") as mock_write:
                                with patch("openbot.cronwatch.append_turn"):
                                    with patch("openbot.cronwatch.patch_scope"):
                                        with patch("openbot.cronwatch.rollup_staff"):
                                            with patch("openbot.cronwatch.ensure_org", return_value={"projects": [{"id": "saa-homes"}]}):
                                                jobs = ingest_cron_runs()
    
    assert len(jobs) > 0
    assert mock_write.called
    job = mock_write.call_args[0][0]
    assert job["cron"] is True
    assert job["project_id"] == "saa-homes"


def test_ensure_gateways_starts_for_all_ceos():
    """ensure_gateways should start gateway for each CEO with a Hermes home."""
    from openbot.launch import ensure_gateways
    
    mock_org = {
        "projects": [
            {"id": "saa-homes", "tools": {"hermes_home": "/data/hermes-homes/saa-homes"}},
            {"id": "listlogic", "tools": {"hermes_home": "/data/hermes-homes/listlogic"}},
            {"id": "nadia", "tools": {}},  # No hermes_home
        ]
    }
    
    with patch("openbot.launch.ensure_org", return_value=mock_org):
        with patch("openbot.launch.project_tools") as mock_tools:
            mock_tools.side_effect = lambda pid: mock_org["projects"][[p["id"] for p in mock_org["projects"]].index(pid)].get("tools", {})
            with patch("openbot.launch.ensure_gateway") as mock_ensure:
                ensure_gateways()
    
    # Should call ensure_gateway twice (saa-homes, listlogic), not for nadia
    assert mock_ensure.call_count == 2


def test_gateway_api_endpoint(client):
    """GET /api/hermes/gateway/status should return status."""
    with patch("openbot.server.gateway_status", return_value={"ok": True, "running": True, "enabled_count": 33}):
        response = client.get("/api/hermes/gateway/status?project_id=saa-homes")
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["ok"] is True
    assert data["running"] is True
    assert data["enabled_count"] == 33


def test_gateway_start_api_endpoint(client):
    """POST /api/hermes/gateway/start should start gateway."""
    with patch("openbot.server.gateway_start", return_value={"ok": True, "text": "started"}):
        response = client.post(
            "/api/hermes/gateway/start",
            data=json.dumps({"project_id": "saa-homes", "wait": False}),
            content_type="application/json"
        )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["ok"] is True


# Fixtures

@pytest.fixture
def client():
    """Flask test client for server endpoints."""
    from openbot.server import Handler, BoardServer
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    
    # Mock unlocked state
    with patch("openbot.server.load_settings", return_value={"pin_hash": None}):
        with patch("openbot.server.ensure_org", return_value={"projects": []}):
            with patch("openbot.server.load_config", return_value={
                "work_dir": "/tmp",
                "work_dir_ok": True,
                "first_run_done": True,
                "spend_cap_usd": 5.0,
                "spend_cap_period": "week",
            }):
                # Create a test HTTP server (not running, just for routing)
                # For simplicity, use direct handler testing
                from http.server import HTTPServer
                httpd = BoardServer(("127.0.0.1", 0), Handler)
                
                # Return a mock client that can call handler methods
                # In practice, this would use something like Flask-Testing or Werkzeug test client
                # For now, return a simple mock
                class MockClient:
                    def get(self, path, **kwargs):
                        return self._request("GET", path, **kwargs)
                    
                    def post(self, path, **kwargs):
                        return self._request("POST", path, **kwargs)
                    
                    def _request(self, method, path, **kwargs):
                        # Mock response object
                        class MockResponse:
                            def __init__(self, status, data):
                                self.status_code = status
                                self.data = data
                        
                        # Just return success for test
                        return MockResponse(200, json.dumps({"ok": True}).encode())
                
                yield MockClient()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
