from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Config:
    # Presets in seconds: 30m, 1h, 2h, 4h, 8h
    presets: List[float] = field(
        default_factory=lambda: [1800.0, 3600.0, 7200.0, 14400.0, 28800.0]
    )
    default_preset: float = 14400.0  # 4 hours
    max_duration: float = 30 * 24 * 3600.0  # 30 days

    # Lid-close actions
    freeze_list: List[str] = field(
        default_factory=lambda: [
            "discord",
            "slack",
            "spotify",
            "steam",
            "telegram",
        ]
    )
    freeze_all_apps: bool = False
    mute_on_lid_close: bool = True
    darken_display_on_lid_close: bool = True
    low_power_on_lid_close: bool = True

    # Battery and thermal floors
    low_power_floor: int = 40  # Percent
    end_floor: int = 10  # Percent
    thermal_rules: bool = True

    # Network / tmux nudge
    nudge_threshold: float = 90.0
    tmux_targets: List[str] = field(default_factory=list)
    tmux_nudge_presses_enter: bool = False

    # Agents that should never be frozen or throttled
    agent_list: List[str] = field(
        default_factory=lambda: [
            "python",
            "code",
            "cursor",
            "node",
            "ssh",
            "tmux",
            "bash",
            "zsh",
            "antigravity",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
