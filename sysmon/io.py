"""Read-only helpers. Parse failures become None / empty, never exceptions."""

from __future__ import annotations

from pathlib import Path


def read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
