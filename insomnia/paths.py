from __future__ import annotations

import os
from pathlib import Path


class Paths:
    """XDG-compliant storage paths for Insomnia."""

    def __init__(self, base_override: Path | str | None = None) -> None:
        if base_override is not None:
            base = Path(base_override).expanduser().resolve()
            self.data_dir = base / "share"
            self.config_dir = base / "config"
            self.state_dir = base / "state"
        elif "INSOMNIA_HOME" in os.environ:
            base = Path(os.environ["INSOMNIA_HOME"]).expanduser().resolve()
            self.data_dir = base / "share"
            self.config_dir = base / "config"
            self.state_dir = base / "state"
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME")
            self.data_dir = (
                Path(xdg_data).expanduser().resolve() / "insomnia"
                if xdg_data
                else Path.home() / ".local" / "share" / "insomnia"
            )

            xdg_config = os.environ.get("XDG_CONFIG_HOME")
            self.config_dir = (
                Path(xdg_config).expanduser().resolve() / "insomnia"
                if xdg_config
                else Path.home() / ".config" / "insomnia"
            )

            xdg_state = os.environ.get("XDG_STATE_HOME")
            self.state_dir = (
                Path(xdg_state).expanduser().resolve() / "insomnia"
                if xdg_state
                else Path.home() / ".local" / "state" / "insomnia"
            )

        self.session_file = self.data_dir / "session.json"
        self.state_file = self.data_dir / "state.json"
        self.lock_file = self.data_dir / "recovery.lock"
        self.config_file = self.config_dir / "config.json"
        self.log_file = self.state_dir / "insomnia.log"

    def ensure_directories(self) -> None:
        """Create parent directories with safe 0700 permissions."""
        for directory in (self.data_dir, self.config_dir, self.state_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
