"""Onboarding flow. Verify auth before first real work."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .detect import which


def check_hermes_auth() -> dict:
    """
    Check if Hermes Agent is authenticated.
    Returns: {"authenticated": bool, "method": str | None, "error": str | None}
    """
    hermes_path = which("hermes")
    if not hermes_path:
        return {
            "authenticated": False,
            "method": None,
            "error": "Hermes Agent binary not found",
        }

    try:
        result = subprocess.run(
            [hermes_path, "portal", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        
        if result.returncode == 0:
            output = result.stdout.lower()
            if "authenticated" in output or "logged in" in output or "connected" in output:
                return {
                    "authenticated": True,
                    "method": "portal",
                    "error": None,
                }
        
        result_session = subprocess.run(
            [hermes_path, "session", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        
        if result_session.returncode == 0 and result_session.stdout.strip():
            return {
                "authenticated": True,
                "method": "session",
                "error": None,
            }
        
        return {
            "authenticated": False,
            "method": None,
            "error": None,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return {
            "authenticated": False,
            "method": None,
            "error": str(e),
        }


def check_opencode_auth() -> dict:
    """
    Check if OpenCode is authenticated.
    Returns: {"authenticated": bool, "method": str | None, "error": str | None}
    """
    opencode_path = which("opencode")
    if not opencode_path:
        return {
            "authenticated": False,
            "method": None,
            "error": "OpenCode binary not found",
        }

    try:
        result = subprocess.run(
            [opencode_path, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        
        if result.returncode == 0:
            output = result.stdout.lower()
            if "authenticated" in output or "logged in" in output or "signed in" in output:
                return {
                    "authenticated": True,
                    "method": "oauth",
                    "error": None,
                }
        
        result_list = subprocess.run(
            [opencode_path, "auth", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        
        if result_list.returncode == 0 and result_list.stdout.strip():
            return {
                "authenticated": True,
                "method": "provider",
                "error": None,
            }
        
        return {
            "authenticated": False,
            "method": None,
            "error": None,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return {
            "authenticated": False,
            "method": None,
            "error": str(e),
        }


def onboarding_status() -> dict:
    """
    Check onboarding readiness: engines installed and authenticated.
    Returns: {
        "ready": bool,
        "hermes": {"authenticated": bool, "method": str | None, "error": str | None},
        "opencode": {"authenticated": bool, "method": str | None, "error": str | None}
    }
    """
    hermes = check_hermes_auth()
    opencode = check_opencode_auth()
    
    ready = hermes["authenticated"] and opencode["authenticated"]
    
    return {
        "ready": ready,
        "hermes": hermes,
        "opencode": opencode,
    }


TEST_JOB_PROMPT = """Create a file named hello.txt in the current directory with this exact content:

Hello from OpenBot!

This is a test job to verify that Builder (OpenCode) is working correctly.
Engine: OpenCode
Job: Onboarding test

Just create the file. Do not make any other changes."""


def test_job_prompt() -> str:
    """Return the prompt for the onboarding test job."""
    return TEST_JOB_PROMPT
