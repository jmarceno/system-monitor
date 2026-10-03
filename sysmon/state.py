"""Persisted window position and UI toggles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import window_state_path


@dataclass
class WindowState:
    pos_x: int = 24
    pos_y: int = 24
    width: int = 0
    height: int = 0
    pinned: bool = False
    collapsed: bool = False
    screen_name: str = ""

    def save(self, path: Path | None = None) -> None:
        target = path or window_state_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "posX": self.pos_x,
                "posY": self.pos_y,
                "width": self.width,
                "height": self.height,
                "pinned": self.pinned,
                "collapsed": False,
                "screenName": self.screen_name,
            }
            target.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    @classmethod
    def load(cls, path: Path | None = None) -> WindowState:
        target = path or window_state_path()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        state = cls()
        if isinstance(data.get("posX"), (int, float)):
            state.pos_x = int(data["posX"])
        if isinstance(data.get("posY"), (int, float)):
            state.pos_y = int(data["posY"])
        if isinstance(data.get("width"), (int, float)) and data["width"] > 0:
            state.width = int(data["width"])
        if isinstance(data.get("height"), (int, float)) and data["height"] > 0:
            state.height = int(data["height"])
        if isinstance(data.get("pinned"), bool):
            state.pinned = data["pinned"]
        if isinstance(data.get("collapsed"), bool):
            state.collapsed = data["collapsed"]
        if isinstance(data.get("screenName"), str):
            state.screen_name = data["screenName"]
        return state
