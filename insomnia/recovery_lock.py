from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

from insomnia.paths import Paths


class LockTimeoutError(Exception):
    """Raised when the recovery lock cannot be acquired within the timeout."""


class RecoveryLock:
    """Exclusive flock-based lock over recovery.lock."""

    def __init__(
        self,
        paths: Paths,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
    ) -> None:
        self.paths = paths
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        self.paths.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.paths.lock_file

        fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        deadline = time.monotonic() + self.timeout

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise LockTimeoutError(
                        f"Timed out after {self.timeout}s waiting for {lock_path}"
                    )
                time.sleep(self.poll_interval)

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self) -> RecoveryLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.release()
