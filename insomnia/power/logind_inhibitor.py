from __future__ import annotations

import os
from typing import Optional
import dbus


class LogindInhibitor:
    """Manages systemd logind inhibition without root/sudo."""

    WHAT = "sleep:idle:handle-lid-switch"
    WHO = "Insomnia"
    MODE = "block"

    def __init__(self) -> None:
        self._fd: Optional[int] = None
        self._bus: Optional[dbus.SystemBus] = None

    def acquire(self, reason: str = "Keep-awake session active") -> bool:
        """Inhibit sleep, idle, and lid-switch."""
        if self._fd is not None:
            return True

        try:
            if self._bus is None:
                self._bus = dbus.SystemBus()
            login = self._bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
            mgr = dbus.Interface(login, "org.freedesktop.login1.Manager")
            fd_object = mgr.Inhibit(self.WHAT, self.WHO, reason, self.MODE)
            self._fd = fd_object.take()
            return True
        except Exception as err:
            self._fd = None
            raise RuntimeError(f"Failed to acquire systemd logind inhibitor: {err}") from err

    def release(self) -> None:
        """Release the logind inhibitor by closing the file descriptor."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    @property
    def is_active(self) -> bool:
        if self._fd is None:
            return False
        try:
            # Check if fd is still open and valid
            os.fstat(self._fd)
            return True
        except OSError:
            self._fd = None
            return False

    def __enter__(self) -> LogindInhibitor:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
