"""Git snapshot for Builder Accept / Reject. Wire git; do not invent a VCS."""

from __future__ import annotations

import subprocess
from pathlib import Path


GIT_TIMEOUT = 30


def _run(folder: str, args: list[str], stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", folder, *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out
    except FileNotFoundError:
        return 127, "git not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "git timed out"


def is_repo(folder: str) -> bool:
    code, _ = _run(folder, ["rev-parse", "--verify", "HEAD"])
    return code == 0


def git_status(folder: str | None) -> dict:
    path = str(Path(folder).expanduser()) if folder else ""
    if not path or not Path(path).is_dir():
        return {
            "ok": False,
            "is_repo": False,
            "folder": path,
            "error": "no folder",
        }
    code, out = _run(path, ["rev-parse", "--is-inside-work-tree"])
    if code == 127:
        return {"ok": False, "is_repo": False, "folder": path, "error": "git not on PATH"}
    if code != 0 or "true" not in (out or "").lower():
        return {
            "ok": True,
            "is_repo": False,
            "folder": path,
            "branch": "",
            "remote": "",
            "dirty": False,
            "github": False,
        }
    _, branch = _run(path, ["branch", "--show-current"])
    _, remote = _run(path, ["remote", "get-url", "origin"])
    _, porcelain = _run(path, ["status", "--porcelain"])
    remote_url = (remote or "").strip().splitlines()[0] if remote else ""
    if remote_url.lower().startswith("error:") or "no such remote" in remote_url.lower():
        remote_url = ""
    return {
        "ok": True,
        "is_repo": True,
        "folder": path,
        "branch": (branch or "").strip(),
        "remote": remote_url,
        "dirty": bool((porcelain or "").strip()),
        "github": "github.com" in remote_url.lower(),
    }


def _untracked(folder: str) -> list[str]:
    code, out = _run(folder, ["ls-files", "--others", "--exclude-standard"])
    if code != 0:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def snapshot(folder: str) -> dict:
    if not is_repo(folder):
        return {"is_repo": False, "diff": "", "untracked": []}
    _, diff = _run(folder, ["diff", "HEAD"])
    return {
        "is_repo": True,
        "diff": diff,
        "untracked": _untracked(folder),
    }


def diff_against_head(folder: str) -> str:
    if not is_repo(folder):
        return ""
    _, diff = _run(folder, ["diff", "HEAD"])
    return diff


def new_untracked(folder: str, before: dict) -> list[str]:
    prior = set(before.get("untracked") or [])
    return [path for path in _untracked(folder) if path not in prior]


def _inside(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def restore_snapshot(folder: str, before: dict) -> tuple[bool, str]:
    """Put the worktree back to the pre-job snapshot. Tracked + new untracked only."""
    if not before.get("is_repo"):
        return False, "not a git repo"
    if not is_repo(folder):
        return False, "not a git repo"
    code, out = _run(folder, ["restore", "--source=HEAD", "--staged", "--worktree", "."])
    if code != 0:
        code, out = _run(folder, ["checkout", "--", "."])
        if code != 0:
            return False, out[-2000:] or "git restore failed"
    root = Path(folder)
    for rel in new_untracked(folder, before):
        path = (root / rel).resolve()
        if path.is_file() and _inside(root, path):
            path.unlink()
    prior_diff = before.get("diff") or ""
    if prior_diff.strip():
        code, out = _run(folder, ["apply", "-"], stdin=prior_diff)
        if code != 0:
            return False, out[-2000:] or "git apply of prior dirty tree failed"
    return True, "restored"
