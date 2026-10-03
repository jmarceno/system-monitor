from __future__ import annotations

from typing import Any

from PySide6.QtCore import QProcess

from .. import parse
from .base import Collector

LSBLK_CMD = [
    "lsblk",
    "-bP",
    "-o",
    "PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME",
]


class StorageCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.volumes: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.ready = False
        self.query_failed = False
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_finished)
        self._timer = self._start_timer(config.storage_interval_ms, self.poll)

    def poll(self) -> None:
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._proc.start(LSBLK_CMD[0], LSBLK_CMD[1:])

    def _on_finished(self, exit_code: int, _status) -> None:
        output = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if exit_code != 0:
            self.ready = False
            self.query_failed = True
            self.volumes = []
            self.rows = []
            self.updated.emit()
            return
        volumes = self._decorate(parse.parse_lsblk(output))
        self.volumes = volumes
        self.rows = self._make_rows(volumes)
        self.ready = True
        self.query_failed = False
        self.updated.emit()

    def _fallback_name(self, volume: dict[str, Any]) -> str:
        mount = volume.get("mountPoint") or ""
        if mount in ("/", "/home"):
            return "Internal drive"
        bits = [bit for bit in mount.split("/") if bit]
        if bits:
            return bits[-1]
        return str(volume.get("path") or "").split("/")[-1]

    def _decorate(self, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for volume in parsed:
            size = volume["sizeBytes"] if volume["sizeBytes"] > 0 else -1
            available = volume["availableBytes"] if volume["availableBytes"] >= 0 else -1
            used = volume["usedBytes"]
            out.append({
                "path": volume["path"],
                "blockName": volume["blockName"],
                "label": volume["label"],
                "name": volume["label"] or self._fallback_name(volume),
                "fsType": volume["fsType"],
                "sizeBytes": size,
                "availableBytes": available,
                "usedBytes": used,
                "usedPct": max(0.0, min(100.0, 100.0 * used / size)) if size > 0 and used >= 0 else -1,
                "mountPoint": volume["mountPoint"],
                "mountPoints": volume["mountPoints"],
                "isRemovable": volume["isRemovable"],
                "transport": volume["transport"],
                "type": volume["type"],
            })
        out.sort(key=lambda item: (item["isRemovable"], item["name"].lower()))
        return out

    def _make_rows(self, volumes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        internal = [volume for volume in volumes if not volume["isRemovable"]]
        removable = [volume for volume in volumes if volume["isRemovable"]]
        rows: list[dict[str, Any]] = []
        if internal:
            rows.append({"kind": "section", "label": "Internal drives"})
            rows.extend({"kind": "volume", "volume": volume} for volume in internal)
        if removable:
            rows.append({"kind": "section", "label": "Removable drives"})
            rows.extend({"kind": "volume", "volume": volume} for volume in removable)
        return rows
