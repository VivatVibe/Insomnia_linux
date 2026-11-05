from __future__ import annotations

import os
import signal
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import psutil


@dataclass
class ProcessIdentity:
    pid: int
    start_time: int
    boot_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProcessIdentity:
        return cls(
            pid=int(data["pid"]),
            start_time=int(data["start_time"]),
            boot_id=str(data["boot_id"]),
        )


class ProcessFreezer:
    """Freezes and resumes processes safely by verifying Linux kernel identity."""

    @staticmethod
    def get_boot_id() -> str:
        boot_path = Path("/proc/sys/kernel/random/boot_id")
        if boot_path.exists():
            return boot_path.read_text().strip()
        return "unknown"

    @classmethod
    def get_process_identity(cls, pid: int) -> Optional[ProcessIdentity]:
        try:
            p = psutil.Process(pid)
            create_time = int(p.create_time() * 1000)
            return ProcessIdentity(
                pid=pid,
                start_time=create_time,
                boot_id=cls.get_boot_id(),
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    @classmethod
    def freeze(cls, pid: int) -> Optional[ProcessIdentity]:
        identity = cls.get_process_identity(pid)
        if not identity:
            return None
        try:
            os.kill(pid, signal.SIGSTOP)
            return identity
        except (ProcessLookupError, PermissionError):
            return None

    @classmethod
    def resume(cls, identity: ProcessIdentity) -> bool:
        current = cls.get_process_identity(identity.pid)
        if not current:
            return False

        # Guard against PID reuse: verify boot ID and kernel process start time
        if current.boot_id != identity.boot_id or current.start_time != identity.start_time:
            return False

        try:
            os.kill(identity.pid, signal.SIGCONT)
            return True
        except (ProcessLookupError, PermissionError):
            return False
