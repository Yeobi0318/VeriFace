"""Filesystem locations used by VeriFace.

All user data lives under %LOCALAPPDATA%\\VeriFace so that an uninstall is a
single folder delete and nothing is scattered across the system.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(root) / "VeriFace"


# --- user data (writable) ---------------------------------------------------
DATA_DIR: Path = _base_dir()
MODELS_DIR: Path = DATA_DIR / "models"
CONFIG_PATH: Path = DATA_DIR / "config.json"
TEMPLATES_PATH: Path = DATA_DIR / "templates.vfb"   # DPAPI-encrypted face templates
VAULT_PATH: Path = DATA_DIR / "vault.vfb"           # DPAPI-encrypted password vault
LOG_PATH: Path = DATA_DIR / "veriface.log"


def ensure_dirs() -> None:
    """Create the data/model directories if they do not yet exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def resource_dir() -> Path:
    """Directory holding bundled read-only assets.

    Works both from source and from a PyInstaller one-file build (where files
    are unpacked to ``sys._MEIPASS``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "assets"
    return Path(__file__).resolve().parents[3] / "assets"
