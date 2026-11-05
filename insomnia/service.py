from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import dbus
import dbus.service

if TYPE_CHECKING:
    from insomnia.config import Config
    from insomnia.paths import Paths
    from insomnia.session_manager import SessionManager

logger = logging.getLogger("insomnia.service")


class InsomniaDBusService(dbus.service.Object):
    """Native D-Bus service exposing the Insomnia control interface.

    Allows the GNOME Shell extension, CLI, and GUI to interact with
    the running Insomnia daemon session in real-time.
    """

    BUS_NAME = "org.vivatvibe.Insomnia"
    OBJECT_PATH = "/org/vivatvibe/Insomnia"
    INTERFACE = "org.vivatvibe.Insomnia"

    def __init__(
        self,
        bus: dbus.SessionBus,
        session_mgr: SessionManager,
        paths: Paths,
        config: Config,
        quit_cb=None,
    ) -> None:
        super().__init__(bus, self.OBJECT_PATH)
        self.bus = bus
        self.session_mgr = session_mgr
        self.paths = paths
        self.config = config
        self.quit_cb = quit_cb

    def _get_current_state_tuple(self):
        from insomnia.power.lid import LidController
        from insomnia.power.battery import BatteryMonitor
        from insomnia.session import format_remaining_time

        session = self.session_mgr.get_active_session()
        if session and not session.is_expired():
            active = True
            rem_sec = max(0, int(session.remaining()))
            rem_str = format_remaining_time(session.remaining())
        else:
            active = False
            rem_sec = 0
            rem_str = ""

        is_closed = LidController.is_lid_closed()
        lid_str = "closed" if is_closed else "open"

        pct, _ = BatteryMonitor.get_battery_info()
        batt_str = f"{pct}%" if pct is not None else "AC"

        return (
            dbus.Boolean(active),
            dbus.Int64(rem_sec),
            dbus.String(rem_str),
            dbus.String(lid_str),
            dbus.String(batt_str),
        )

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="bs")
    def StartSession(self, duration_str: str):
        from insomnia.session import parse_duration_string, format_remaining_time

        try:
            duration = parse_duration_string(str(duration_str))
            session = self.session_mgr.start_session(duration)
            rem = format_remaining_time(session.remaining())
            self.notify_state_changed()
            return dbus.Boolean(True), dbus.String(rem)
        except Exception as e:
            logger.error("Failed to start session via D-Bus: %s", e)
            return dbus.Boolean(False), dbus.String(str(e))

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="bs")
    def ExtendSession(self, duration_str: str):
        from insomnia.session import parse_duration_string, format_remaining_time

        try:
            duration = parse_duration_string(str(duration_str))
            session = self.session_mgr.extend_session(duration)
            if not session:
                return dbus.Boolean(False), dbus.String("No active session to extend")
            rem = format_remaining_time(session.remaining())
            self.notify_state_changed()
            return dbus.Boolean(True), dbus.String(rem)
        except Exception as e:
            logger.error("Failed to extend session via D-Bus: %s", e)
            return dbus.Boolean(False), dbus.String(str(e))

    @dbus.service.method(INTERFACE, in_signature="", out_signature="b")
    def EndSession(self):
        try:
            self.session_mgr.end_session()
            self.notify_state_changed()
            return dbus.Boolean(True)
        except Exception as e:
            logger.error("Failed to end session via D-Bus: %s", e)
            return dbus.Boolean(False)

    @dbus.service.method(INTERFACE, in_signature="", out_signature="bixss")
    def GetState(self):
        return self._get_current_state_tuple()

    @dbus.service.method(INTERFACE, in_signature="", out_signature="b")
    def OpenControlCenter(self):
        import subprocess

        try:
            subprocess.Popen(["insomnia", "gui"])
            return dbus.Boolean(True)
        except Exception as e:
            logger.error("Failed to launch control center: %s", e)
            return dbus.Boolean(False)

    @dbus.service.method(INTERFACE, in_signature="", out_signature="b")
    def OpenSettings(self):
        from insomnia.ui.settings_dialog import SettingsDialog
        from gi.repository import GLib

        def show_dialog():
            dlg = SettingsDialog(self.paths, self.config)
            dlg.run()
            dlg.destroy()
            return False

        GLib.idle_add(show_dialog)
        return dbus.Boolean(True)

    @dbus.service.method(INTERFACE, in_signature="", out_signature="b")
    def Quit(self):
        if self.quit_cb:
            from gi.repository import GLib
            GLib.idle_add(self.quit_cb)
        return dbus.Boolean(True)

    @dbus.service.signal(INTERFACE, signature="bixss")
    def StateChanged(self, active, remaining_seconds, formatted_remaining, lid_state, battery_str):
        pass

    def notify_state_changed(self):
        state = self._get_current_state_tuple()
        self.StateChanged(*state)
