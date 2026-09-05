"""Builder validation gate. Syntax/lint checks before Accept."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def validate_changes(folder: str, diff_text: str, untracked: list[str]) -> tuple[bool, str]:
    """
    Validate pending changes in the work folder.
    
    Returns (ok, detail):
      - ok=True: validation passed
      - ok=False: validation failed, detail contains error message
    """
    if not folder or not Path(folder).is_dir():
        return False, "no folder"
    
    changed_files = _extract_changed_files(diff_text, untracked)
    if not changed_files:
        # No files to validate (e.g. only deleted files)
        return True, "no files to validate"
    
    # Run validators on changed files
    errors: list[str] = []
    
    for fpath in changed_files:
        full_path = Path(folder) / fpath
        if not full_path.is_file():
            continue
        
        # Python files: py_compile
        if fpath.endswith(".py"):
            ok, err = _validate_python(full_path)
            if not ok:
                errors.append(f"{fpath}: {err}")
        
        # JavaScript/TypeScript: node --check or similar
        elif fpath.endswith((".js", ".mjs", ".cjs")):
            ok, err = _validate_javascript(full_path)
            if not ok:
                errors.append(f"{fpath}: {err}")
    
    # Check if repo has linters (ruff, eslint) and use them if present
    repo_errors = _run_repo_linters(folder, changed_files)
    errors.extend(repo_errors)
    
    if errors:
        detail = "\n".join(errors[:10])  # Cap to first 10 errors
        if len(errors) > 10:
            detail += f"\n... and {len(errors) - 10} more errors"
        return False, detail
    
    return True, "validation passed"


def _extract_changed_files(diff_text: str, untracked: list[str]) -> list[str]:
    """Extract list of changed file paths from diff and untracked list."""
    files = set(untracked)
    
    # Parse diff headers: +++ b/path/to/file.py
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            fpath = line[6:].strip()
            if fpath and fpath != "/dev/null":
                files.add(fpath)
    
    return sorted(files)


def _validate_python(fpath: Path) -> tuple[bool, str]:
    """Validate Python file with py_compile."""
    try:
        import py_compile
        py_compile.compile(str(fpath), doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        # Extract just the error message, not full traceback
        msg = str(e).split("\n")[0] if e.msg else "syntax error"
        return False, msg
    except Exception as e:
        return False, str(e)


def _validate_javascript(fpath: Path) -> tuple[bool, str]:
    """Validate JavaScript file with node --check."""
    try:
        proc = subprocess.run(
            ["node", "--check", str(fpath)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "syntax error").strip()
            # Simplify error message
            lines = err.splitlines()
            msg = lines[0] if lines else "syntax error"
            return False, msg
        return True, ""
    except FileNotFoundError:
        # node not on PATH - skip JS validation
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "validation timeout"
    except Exception as e:
        return False, str(e)


def _run_repo_linters(folder: str, changed_files: list[str]) -> list[str]:
    """Run repo linters (ruff, eslint) if they exist in the repo."""
    errors: list[str] = []
    root = Path(folder)
    
    # Check for ruff (Python linter)
    if _has_ruff(root) and any(f.endswith(".py") for f in changed_files):
        py_files = [f for f in changed_files if f.endswith(".py")]
        ok, err = _run_ruff(root, py_files)
        if not ok and err:
            errors.append(f"ruff: {err}")
    
    # Check for eslint (JS/TS linter)
    if _has_eslint(root) and any(f.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx")) for f in changed_files):
        js_files = [f for f in changed_files if f.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx"))]
        ok, err = _run_eslint(root, js_files)
        if not ok and err:
            errors.append(f"eslint: {err}")
    
    return errors


def _has_ruff(root: Path) -> bool:
    """Check if repo has ruff configured."""
    return (
        (root / "ruff.toml").is_file()
        or (root / ".ruff.toml").is_file()
        or (root / "pyproject.toml").is_file()
    )


def _has_eslint(root: Path) -> bool:
    """Check if repo has eslint configured."""
    return (
        (root / ".eslintrc").is_file()
        or (root / ".eslintrc.json").is_file()
        or (root / ".eslintrc.js").is_file()
        or (root / "eslint.config.js").is_file()
        or (root / "package.json").is_file()
    )


def _run_ruff(root: Path, files: list[str]) -> tuple[bool, str]:
    """Run ruff check on specified files."""
    try:
        proc = subprocess.run(
            ["ruff", "check", "--quiet", *files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            out = (proc.stdout or proc.stderr or "").strip()
            # Return first few lines of output
            lines = out.splitlines()[:5]
            return False, "\n".join(lines)
        return True, ""
    except FileNotFoundError:
        # ruff not on PATH - skip
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception:
        return True, ""


def _run_eslint(root: Path, files: list[str]) -> tuple[bool, str]:
    """Run eslint on specified files."""
    try:
        proc = subprocess.run(
            ["npx", "eslint", "--quiet", *files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            out = (proc.stdout or proc.stderr or "").strip()
            lines = out.splitlines()[:5]
            return False, "\n".join(lines)
        return True, ""
    except FileNotFoundError:
        # npx not on PATH - skip
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception:
        return True, ""
