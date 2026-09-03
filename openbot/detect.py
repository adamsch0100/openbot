"""Detect official engine binaries. Do not vendor them."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


HERMES_INSTALL = "https://hermes-agent.nousresearch.com/docs/user-guide/windows-native"
HERMES_INSTALL_UNIX = "https://github.com/NousResearch/hermes-agent"
OPENCODE_INSTALL = "https://github.com/anomalyco/opencode"
HERMES_INSTALL_CMD_WIN = "iex (irm https://hermes-agent.nousresearch.com/install.ps1)"
HERMES_INSTALL_CMD_UNIX = "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
WIN_SUFFIXES = (".exe", ".cmd", ".bat", ".com")


@dataclass
class Engine:
    name: str
    binary: str
    present: bool
    path: str | None
    install: str


def hermes_home() -> Path:
    explicit = os.environ.get("HERMES_HOME")
    if explicit:
        return Path(explicit)
    d_home = Path("D:/Users") / Path.home().name / "hermes"
    if (d_home / "bin").is_dir() or (d_home / "hermes-agent").exists():
        return d_home
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def extra_bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    appdata = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    home = Path.home()
    if appdata:
        npm = Path(appdata) / "npm"
        dirs.append(npm)
        dirs.append(npm / "node_modules" / "opencode-ai" / "bin")
    if local:
        hermes_root = Path(local) / "hermes"
        dirs.append(hermes_root / "bin")
        dirs.append(hermes_root / "hermes-agent")
    d_home = Path("D:/Users") / home.name / "hermes"
    dirs.append(d_home / "bin")
    dirs.append(d_home / "hermes-agent" / "venv" / "Scripts")
    dirs.append(hermes_home() / "bin")
    dirs.append(hermes_home() / "hermes-agent" / "venv" / "Scripts")
    dirs.append(home / ".opencode" / "bin")
    dirs.append(home / ".local" / "bin")
    return dirs


def _windows_candidate(directory: Path, binary: str) -> Path | None:
    for suffix in WIN_SUFFIXES:
        candidate = directory / f"{binary}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def which(binary: str) -> str | None:
    found = shutil.which(binary)
    if found and os.name == "nt":
        path = Path(found)
        if path.suffix.lower() in WIN_SUFFIXES:
            return found
        sibling = _windows_candidate(path.parent, binary)
        if sibling is not None:
            return str(sibling)
    elif found:
        return found
    for directory in extra_bin_dirs():
        if not directory.is_dir():
            continue
        if os.name == "nt":
            candidate = _windows_candidate(directory, binary)
            if candidate is not None:
                return str(candidate)
        else:
            candidate = directory / binary
            if candidate.is_file():
                return str(candidate)
    return None


def detect() -> dict:
    hermes_path = which("hermes")
    opencode_path = which("opencode")
    hermes_install = HERMES_INSTALL if os.name == "nt" else HERMES_INSTALL_UNIX
    hermes = Engine(
        name="Hermes Agent",
        binary="hermes",
        present=bool(hermes_path),
        path=hermes_path,
        install=hermes_install,
    )
    opencode = Engine(
        name="OpenCode",
        binary="opencode",
        present=bool(opencode_path),
        path=opencode_path,
        install=OPENCODE_INSTALL,
    )
    return {
        "board": {"name": "OpenBot board", "present": True},
        "hermes": {
            **asdict(hermes),
            "install_cmd": HERMES_INSTALL_CMD_WIN if os.name == "nt" else HERMES_INSTALL_CMD_UNIX,
            "home": str(hermes_home()),
        },
        "opencode": asdict(opencode),
    }
