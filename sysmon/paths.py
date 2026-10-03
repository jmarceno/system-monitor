"""XDG paths for the Python Qt app. Secrets stay under qs-system-monitor."""

from __future__ import annotations

import os
from pathlib import Path


APP_ID = "system-monitor"
LEGACY_APP_ID = "qs-system-monitor"


def xdg_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_state() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))


def secrets_path() -> Path:
    override = os.environ.get("QS_AI_SPEND_SECRETS", "").strip()
    if override:
        return Path(override)
    return xdg_config() / LEGACY_APP_ID / "ai-spend.json"


def window_state_path() -> Path:
    return xdg_state() / APP_ID / "window-state.json"
