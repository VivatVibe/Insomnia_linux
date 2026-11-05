from __future__ import annotations

import shutil
import subprocess
from typing import List, Tuple


class TmuxNudge:
    """Sends 'continue' to user-designated tmux panes after network recovery."""

    MARK_OPTION = "@insomnia-nudge"

    @classmethod
    def get_tmux_path(cls) -> str | None:
        return shutil.which("tmux")

    @classmethod
    def is_pane_marked(cls, target: str) -> bool:
        tmux = cls.get_tmux_path()
        if not tmux:
            return False

        try:
            res = subprocess.run(
                [tmux, "show-options", "-p", "-t", target, cls.MARK_OPTION],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Output is format: @insomnia-nudge on
            return "on" in res.stdout.strip().lower()
        except Exception:
            return False

    @classmethod
    def nudge_target(cls, target: str, press_enter: bool = False) -> bool:
        tmux = cls.get_tmux_path()
        if not tmux or not cls.is_pane_marked(target):
            return False

        try:
            cmd = [tmux, "send-keys", "-t", target, "continue"]
            if press_enter:
                cmd.append("Enter")
            res = subprocess.run(cmd, capture_output=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def nudge_all(cls, targets: List[str], press_enter: bool = False) -> int:
        count = 0
        for target in targets:
            if cls.nudge_target(target, press_enter=press_enter):
                count += 1
        return count
