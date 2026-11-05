from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import dbus


class BatteryMonitor:
    """Monitors battery capacity via sysfs and controls power profiles via D-Bus."""

    SYSFS_POWER_SUPPLY = Path("/sys/class/power_supply")

    @classmethod
    def get_battery_info(cls) -> Tuple[Optional[int], str]:
        """Returns (percentage, status). E.g. (85, 'Discharging') or (None, 'No Battery')."""
        if not cls.SYSFS_POWER_SUPPLY.exists():
            return None, "No Battery"

        batteries = list(cls.SYSFS_POWER_SUPPLY.glob("BAT*"))
        if not batteries:
            return None, "AC Only"

        for bat in batteries:
            cap_file = bat / "capacity"
            stat_file = bat / "status"
            if cap_file.exists():
                try:
                    pct = int(cap_file.read_text().strip())
                    status = stat_file.read_text().strip() if stat_file.exists() else "Unknown"
                    return pct, status
                except (ValueError, OSError):
                    continue

        return None, "Unknown"

    @classmethod
    def get_power_profile(cls) -> Optional[str]:
        """Reads active profile from power-profiles-daemon (power-saver, balanced, performance)."""
        try:
            bus = dbus.SystemBus()
            proxy = bus.get_object("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")
            props = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
            return str(props.Get("net.hadess.PowerProfiles", "ActiveProfile"))
        except Exception:
            return None

    @classmethod
    def set_power_profile(cls, profile: str) -> bool:
        """Sets active profile in power-profiles-daemon."""
        try:
            bus = dbus.SystemBus()
            proxy = bus.get_object("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")
            props = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
            props.Set("net.hadess.PowerProfiles", "ActiveProfile", dbus.String(profile))
            return True
        except Exception:
            return False
