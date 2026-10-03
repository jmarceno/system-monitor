from __future__ import annotations

from typing import Any

from .. import parse
from ..io import read_text
from .base import Collector


class StorageIoCollector(Collector):
    def __init__(self, config, storage, parent=None) -> None:
        super().__init__(config, parent)
        self._storage = storage
        self.samples: list[dict[str, Any]] = []
        self.generation = 0
        self.history_max = 40
        self._previous: dict[str, dict[str, float]] | None = None
        self._timer = self._start_timer(config.disk_io_interval_ms, self.poll)

    @property
    def ready(self) -> bool:
        return self._previous is not None

    def _on_compact_changed(self) -> None:
        if self._compact:
            self._timer.stop()
        else:
            self._timer.start()

    def sample_for(self, volume: dict[str, Any] | None) -> dict[str, Any]:
        key = self._key_for(volume)
        if not key:
            return self._empty_sample()
        return self._sample_for_key(key) or self._empty_sample()

    def _key_for(self, volume: dict[str, Any] | None) -> str:
        if not volume:
            return ""
        if volume.get("blockName"):
            return str(volume["blockName"])
        path = str(volume.get("path") or "")
        return path.split("/")[-1] if path else ""

    def _sample_for_key(self, key: str) -> dict[str, Any] | None:
        for sample in self.samples:
            if sample["blockName"] == key:
                return sample
        return None

    def _empty_sample(self) -> dict[str, Any]:
        return {
            "blockName": "",
            "readKBps": 0.0,
            "writeKBps": 0.0,
            "totalKBps": 0.0,
            "history": [],
        }

    def poll(self) -> None:
        text = read_text("/proc/diskstats")
        if text is None:
            return
        records = parse.parse_block_diskstats(text)
        current = {
            record["name"]: {
                "readSectors": record["readSectors"],
                "writeSectors": record["writeSectors"],
            }
            for record in records
        }
        previous = self._previous
        seconds = self.config.disk_io_interval_ms / 1000
        next_samples: list[dict[str, Any]] = []
        for volume in self._storage.volumes:
            block_name = self._key_for(volume)
            now = current.get(block_name)
            before = previous.get(block_name) if previous else None
            read_kbps = 0.0
            write_kbps = 0.0
            if now and before and seconds > 0:
                read_kbps = max(0.0, 0.5 * (now["readSectors"] - before["readSectors"]) / seconds)
                write_kbps = max(0.0, 0.5 * (now["writeSectors"] - before["writeSectors"]) / seconds)
            old = self._sample_for_key(block_name)
            history = list(old["history"][-(self.history_max - 1) :]) if old else []
            if now and before:
                history.append(read_kbps + write_kbps)
            elif not now:
                history = []
            next_samples.append({
                "blockName": block_name,
                "readKBps": read_kbps,
                "writeKBps": write_kbps,
                "totalKBps": read_kbps + write_kbps,
                "history": history,
            })
        self.samples = next_samples
        self._previous = current
        self.generation += 1
        self.updated.emit()
