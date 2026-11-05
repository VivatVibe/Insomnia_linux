from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.power.logind_inhibitor import LogindInhibitor
from insomnia.recovery_lock import RecoveryLock
from insomnia.session import Session, format_remaining_time
from insomnia.store import Store

logger = logging.getLogger("insomnia.session_manager")


class SessionManager:
    """Coordinates session lifecycle, journal persistence, and logind inhibitor."""

    def __init__(self, paths: Paths, config: Optional[Config] = None) -> None:
        self.paths = paths
        self.config = config or Config()
        self.inhibitor = LogindInhibitor()
        self._on_change_callbacks: list[Callable[[Optional[Session]], None]] = []

    def add_on_change_callback(self, cb: Callable[[Optional[Session]], None]) -> None:
        self._on_change_callbacks.append(cb)

    def _notify(self, session: Optional[Session]) -> None:
        for cb in self._on_change_callbacks:
            try:
                cb(session)
            except Exception as err:
                logger.error("Callback error: %s", err)

    def get_active_session(self) -> Optional[Session]:
        with RecoveryLock(self.paths):
            data = Store.read_json(self.paths.session_file)
            if not data:
                return None
            try:
                session = Session.from_dict(data)
                if session.is_expired():
                    return None
                return session
            except Exception:
                return None

    def start_session(self, duration_seconds: float) -> Session:
        with RecoveryLock(self.paths):
            # 1. Acquire logind inhibitor
            remaining_str = format_remaining_time(duration_seconds)
            reason = f"Keep-awake session active ({remaining_str})"
            self.inhibitor.acquire(reason=reason)

            # 2. Write state.json with sleepDisabledByUs
            state = Store.read_json(self.paths.state_file) or {}
            state["sleepDisabledByUs"] = True
            Store.write_json(self.paths.state_file, state)

            # 3. Create and write session.json
            session = Session.create(duration_seconds)
            Store.write_json(self.paths.session_file, session.to_dict())

        self._notify(session)
        return session

    def extend_session(self, additional_seconds: float) -> Optional[Session]:
        with RecoveryLock(self.paths):
            data = Store.read_json(self.paths.session_file)
            if not data:
                return None

            session = Session.from_dict(data)
            session.extend(additional_seconds)
            Store.write_json(self.paths.session_file, session.to_dict())

        self._notify(session)
        return session

    def end_session(self) -> None:
        with RecoveryLock(self.paths):
            # 1. Release inhibitor
            self.inhibitor.release()

            # 2. Clean session file
            if self.paths.session_file.exists():
                try:
                    self.paths.session_file.unlink()
                except OSError:
                    pass

            # 3. Update state.json
            state = Store.read_json(self.paths.state_file) or {}
            state["sleepDisabledByUs"] = False
            Store.write_json(self.paths.state_file, state)

        self._notify(None)

    def tick(self) -> Optional[Session]:
        """Periodic tick: checks session expiration and battery safety floors."""
        session = self.get_active_session()
        if session is None:
            if self.inhibitor.is_active:
                self.inhibitor.release()
            return None

        # Check battery safety floor
        pct, _ = BatteryMonitor.get_battery_info()
        if pct is not None:
            if self.config.end_floor > 0 and pct <= self.config.end_floor:
                logger.warning("Battery (%d%%) fell below end floor (%d%%). Ending session.", pct, self.config.end_floor)
                self.end_session()
                return None
            elif pct <= self.config.low_power_floor and self.config.thermal_rules:
                BatteryMonitor.set_power_profile("power-saver")

        if not self.inhibitor.is_active:
            # Reacquire if lost
            remaining_str = format_remaining_time(session.remaining())
            self.inhibitor.acquire(f"Keep-awake session active ({remaining_str})")

        return session
