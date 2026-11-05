from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.recovery_lock import LockTimeoutError, RecoveryLock
from insomnia.session import Session
from insomnia.store import Store
from insomnia.system.freezer import ProcessFreezer, ProcessIdentity

logger = logging.getLogger("insomnia.backstop")


class BackstopRunner:
    """Safely reconciles and cleans up keep-awake state on session expiry or abnormal exit."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def run(self, force: bool = False) -> int:
        """Runs single backstop reconciliation cycle. Returns exit code (0 = success, 75 = lock busy)."""
        try:
            with RecoveryLock(self.paths, timeout=5.0):
                return self._reconcile(force=force)
        except LockTimeoutError:
            logger.info("Recovery lock is busy; backstop deferring to next run.")
            return 75
        except Exception as err:
            logger.error("Backstop error: %s", err, exc_info=True)
            return 1

    def _reconcile(self, force: bool = False) -> int:
        session_data = Store.read_json(self.paths.session_file)
        state = Store.read_json(self.paths.state_file) or {}

        now = datetime.now(timezone.utc)
        session: Optional[Session] = None
        if session_data:
            try:
                session = Session.from_dict(session_data)
            except Exception:
                session = None

        is_active = session is not None and not session.is_expired(now)

        if is_active and not force:
            # Active session running normally, no backstop action needed
            return 0

        # Session has expired, is corrupted, or --force was given
        dirty = False

        # 1. Unfreeze any frozen processes recorded in state.json
        frozen_entries = state.get("frozenProcesses", [])
        if frozen_entries:
            for entry in frozen_entries:
                try:
                    ident = ProcessIdentity.from_dict(entry)
                    ProcessFreezer.resume(ident)
                except Exception as err:
                    logger.warning("Failed to resume process %s: %s", entry, err)
            state["frozenProcesses"] = []
            dirty = True

        # 2. Restore power profile if modified by Insomnia
        if state.get("lowPowerSetByUs", False):
            prev_profile = state.get("previousPowerProfile", "balanced")
            BatteryMonitor.set_power_profile(prev_profile)
            state["lowPowerSetByUs"] = False
            state.pop("previousPowerProfile", None)
            dirty = True

        # 3. Restore audio mute if muted by Insomnia
        if state.get("savedMuted", False):
            self._unmute_audio()
            state["savedMuted"] = False
            dirty = True

        # 4. Remove expired session file
        if self.paths.session_file.exists():
            try:
                self.paths.session_file.unlink()
                dirty = True
            except OSError:
                pass

        if dirty or state:
            state["cleanedAt"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            Store.write_json(self.paths.state_file, state)

        return 0

    def _unmute_audio(self) -> None:
        if shutil.which("wpctl"):
            try:
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], capture_output=True, timeout=5)
                return
            except Exception:
                pass
        if shutil.which("pactl"):
            try:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], capture_output=True, timeout=5)
                return
            except Exception:
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    force = "--force" in sys.argv
    runner = BackstopRunner(Paths())
    sys.exit(runner.run(force=force))


if __name__ == "__main__":
    main()
