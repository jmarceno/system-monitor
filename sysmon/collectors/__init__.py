from __future__ import annotations

from .ai_spend import AiSpendCollector
from .cpu import CpuCollector
from .meminfo import MemInfoCollector
from .storage import StorageCollector
from .storage_io import StorageIoCollector
from .swap_disk import SwapDiskCollector
from .vram import VramCollector
from .zram import ZramCollector

__all__ = [
    "AiSpendCollector",
    "CpuCollector",
    "MemInfoCollector",
    "StorageCollector",
    "StorageIoCollector",
    "SwapDiskCollector",
    "VramCollector",
    "ZramCollector",
]
