from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from insomnia.store import format_iso8601, parse_iso8601


def parse_duration_string(text: str) -> float:
    """Parse duration string like '30m', '1h', '2h30m', '7200' to seconds."""
    text = text.strip().lower()
    if not text:
        raise ValueError("Empty duration string")

    if text.isdigit():
        return float(text)

    pattern = re.compile(r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?")
    match = pattern.fullmatch(text)
    if not match:
        raise ValueError(f"Invalid duration format: '{text}'")

    days, hours, minutes, seconds = match.groups()
    total = 0.0
    if days:
        total += float(days) * 86400
    if hours:
        total += float(hours) * 3600
    if minutes:
        total += float(minutes) * 60
    if seconds:
        total += float(seconds)

    if total <= 0:
        raise ValueError(f"Duration must be greater than zero: '{text}'")
    return total


def format_remaining_time(seconds: float) -> str:
    """Format remaining seconds as HH:MM:SS or MM:SS or Xh Ym."""
    if seconds <= 0:
        return "00:00"
    secs = int(round(seconds))
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    remaining_s = secs % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{remaining_s:02d}"
    return f"{mins:02d}:{remaining_s:02d}"


@dataclass
class Session:
    started_at: datetime
    ends_at: datetime
    extensions: List[float] = field(default_factory=list)

    @classmethod
    def create(cls, duration_seconds: float) -> Session:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        ends_at = datetime.fromtimestamp(int(now.timestamp() + duration_seconds), tz=timezone.utc)
        return cls(started_at=now, ends_at=ends_at, extensions=[])

    def remaining(self, at: Optional[datetime] = None) -> float:
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        diff = self.ends_at.timestamp() - now.timestamp()
        return max(0.0, diff)

    def is_expired(self, at: Optional[datetime] = None) -> bool:
        return self.remaining(at) <= 0.0

    def extend(self, additional_seconds: float) -> None:
        if additional_seconds <= 0:
            return
        new_timestamp = self.ends_at.timestamp() + additional_seconds
        self.ends_at = datetime.fromtimestamp(new_timestamp, tz=timezone.utc)
        self.extensions.append(additional_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "startedAt": format_iso8601(self.started_at),
            "endsAt": format_iso8601(self.ends_at),
            "extensions": self.extensions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Session:
        started_at = parse_iso8601(data["startedAt"])
        ends_at = parse_iso8601(data["endsAt"])
        extensions = [float(x) for x in data.get("extensions", [])]
        return cls(started_at=started_at, ends_at=ends_at, extensions=extensions)
