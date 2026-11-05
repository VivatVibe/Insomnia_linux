from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import dbus
import psutil

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.recovery_lock import RecoveryLock
from insomnia.store import Store
from insomnia.system.freezer import ProcessFreezer, ProcessIdentity


class LidController:
    """Manages lid close actions (audio mute, low power, display darkening, app freezing)."""

    def __init__(self, paths: Paths, config: Config) -> None:
        self.paths = paths
        self.config = config

    @staticmethod
    def is_lid_closed() -> bool:
        # Check systemd logind over D-Bus
        try:
            bus = dbus.SystemBus()
            proxy = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
            props = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
            return bool(props.Get("org.freedesktop.login1.Manager", "LidClosed"))
        except Exception:
            pass

        # Fallback to sysfs/proc
        for state_file in Path("/proc/acpi/button/lid").glob("*/state"):
            try:
                content = state_file.read_text().lower()
                return "closed" in content
            except OSError:
                continue

        return False

    def handle_lid_closed(self) -> None:
        with RecoveryLock(self.paths):
            state = Store.read_json(self.paths.state_file) or {}

            # 1. Low power mode
            if self.config.low_power_on_lid_close and not state.get("lowPowerSetByUs", False):
                prev_profile = BatteryMonitor.get_power_profile()
                if prev_profile and prev_profile != "power-saver":
                    if BatteryMonitor.set_power_profile("power-saver"):
                        state["lowPowerSetByUs"] = True
                        state["previousPowerProfile"] = prev_profile

            # 2. Audio mute
            if self.config.mute_on_lid_close and not state.get("savedMuted", False):
                muted = self._mute_audio()
                if muted:
                    state["savedMuted"] = True

            # 3. Freeze background applications
            if self.config.freeze_list:
                frozen = self._freeze_matching_apps(state.get("frozenProcesses", []))
                state["frozenProcesses"] = frozen

            Store.write_json(self.paths.state_file, state)

    def handle_lid_opened(self) -> None:
        with RecoveryLock(self.paths):
            state = Store.read_json(self.paths.state_file) or {}

            # 1. Restore power profile
            if state.get("lowPowerSetByUs", False):
                prev_profile = state.get("previousPowerProfile", "balanced")
                BatteryMonitor.set_power_profile(prev_profile)
                state["lowPowerSetByUs"] = False
                state.pop("previousPowerProfile", None)

            # 2. Restore audio
            if state.get("savedMuted", False):
                self._unmute_audio()
                state["savedMuted"] = False

            # 3. Resume frozen processes
            frozen = state.get("frozenProcesses", [])
            if frozen:
                remaining_frozen = []
                for entry in frozen:
                    try:
                        ident = ProcessIdentity.from_dict(entry)
                        if not ProcessFreezer.resume(ident):
                            # Process might have exited on its own
                            pass
                    except Exception:
                        pass
                state["frozenProcesses"] = remaining_frozen

            Store.write_json(self.paths.state_file, state)

    def _mute_audio(self) -> bool:
        if shutil.which("wpctl"):
            try:
                res = subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], capture_output=True, timeout=5)
                return res.returncode == 0
            except Exception:
                pass
        if shutil.which("pactl"):
            try:
                res = subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], capture_output=True, timeout=5)
                return res.returncode == 0
            except Exception:
                pass
        return False

    def _unmute_audio(self) -> bool:
        if shutil.which("wpctl"):
            try:
                res = subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], capture_output=True, timeout=5)
                return res.returncode == 0
            except Exception:
                pass
        if shutil.which("pactl"):
            try:
                res = subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], capture_output=True, timeout=5)
                return res.returncode == 0
            except Exception:
                pass
        return False

    def _freeze_matching_apps(self, existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        frozen_list = list(existing)
        existing_pids = {e.get("pid") for e in frozen_list if "pid" in e}
        agent_names = set(self.config.agent_list)

        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = p.info["pid"]
                if pid in existing_pids or pid == psutil.Process().pid:
                    continue

                name = (p.info["name"] or "").lower()
                cmd = " ".join(p.info["cmdline"] or []).lower()

                # Guard: Never freeze agents
                if any(agent.lower() in name or agent.lower() in cmd for agent in agent_names):
                    continue

                # Match freeze list
                if any(target.lower() in name or target.lower() in cmd for target in self.config.freeze_list):
                    ident = ProcessFreezer.freeze(pid)
                    if ident:
                        frozen_list.append(ident.to_dict())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return frozen_list
