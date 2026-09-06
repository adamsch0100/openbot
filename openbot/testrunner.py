"""Test runner for post-accept validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def detect_test_command(folder: str) -> str | None:
    """Detect test command from repo configuration."""
    root = Path(folder)
    
    # Check package.json for npm test
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            if "test" in scripts:
                return "npm test"
        except Exception:
            pass
    
    # Check for pytest
    if (root / "pytest.ini").is_file() or (root / "setup.cfg").is_file() or (root / "pyproject.toml").is_file():
        # Look for actual test files
        if list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
            return "pytest"
    
    # Check for unittest (Python)
    if list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
        return "python -m pytest"
    
    return None


def run_tests(folder: str, command: str, timeout: int = 60) -> tuple[bool, str]:
    """
    Run test command in folder.
    
    Returns (ok, output):
      - ok=True: tests passed
      - ok=False: tests failed, output contains error
    """
    if not folder or not Path(folder).is_dir():
        return False, "no folder"
    
    try:
        proc = subprocess.run(
            command.split(),
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        
        if proc.returncode == 0:
            return True, out[-2000:]
        else:
            return False, out[-2000:] or f"tests failed (exit {proc.returncode})"
            
    except subprocess.TimeoutExpired:
        return False, f"tests timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"command not found: {command.split()[0]}"
    except Exception as e:
        return False, str(e)
