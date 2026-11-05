from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def iso8601_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_iso8601(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso8601(text: str) -> datetime:
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


class Store:
    """Atomic JSON storage ensuring mode 0600 and fsync-rename semantics."""

    @staticmethod
    def read_json(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None

        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"Path is not a regular file: {path}")

        # Enforce owner-only permissions if too permissive
        if (st.st_mode & 0o777) != 0o600:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def write_json(path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Temporary file inside the same parent directory ensures atomic rename on POSIX
        prefix = f".{path.name}.tmp."
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=prefix,
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_path_str)

        try:
            os.chmod(fd, 0o600)
            content = json.dumps(data, indent=2, sort_keys=True)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise
