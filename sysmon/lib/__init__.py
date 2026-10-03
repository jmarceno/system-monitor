from __future__ import annotations

# Re-export so `python3 -m sysmon.lib.ai_spend_collect` still works.
from .ai_spend_collect import collect, main

__all__ = ["collect", "main"]
