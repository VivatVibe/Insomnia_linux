from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional
import psutil


@dataclass
class BrowserProcessInfo:
    pid: int
    name: str
    cmdline: List[str]
    missing_flags: List[str]


class BrowserThrottle:
    """Detects and unthrottles background Chromium/Chrome instances."""

    REQUIRED_FLAGS = [
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]

    CHROMIUM_BINARIES = {
        "chrome",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave",
        "brave-browser",
        "edge",
        "microsoft-edge",
    }

    @classmethod
    def get_throttled_browsers(cls) -> List[BrowserProcessInfo]:
        throttled = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (p.info["name"] or "").lower()
                cmdline = p.info["cmdline"] or []
                if not cmdline:
                    continue

                exe = cmdline[0].lower()
                if any(b in name or b in exe for b in cls.CHROMIUM_BINARIES):
                    # Check if this is the main browser process (not zygote, gpu, etc.)
                    if any("--type=" in arg for arg in cmdline):
                        continue

                    cmd_str = " ".join(cmdline)
                    missing = [flag for flag in cls.REQUIRED_FLAGS if flag not in cmd_str]
                    if missing:
                        throttled.append(
                            BrowserProcessInfo(
                                pid=p.info["pid"],
                                name=p.info["name"],
                                cmdline=cmdline,
                                missing_flags=missing,
                            )
                        )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return throttled

    @classmethod
    def relaunch_unthrottled(cls, info: BrowserProcessInfo) -> bool:
        """Launches the browser with unthrottled flags appended."""
        new_cmd = list(info.cmdline)
        for flag in info.missing_flags:
            if flag not in new_cmd:
                new_cmd.append(flag)

        try:
            subprocess.Popen(new_cmd, start_new_session=True)
            return True
        except Exception:
            return False
