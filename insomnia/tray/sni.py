from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import dbus
import dbus.service
from gi.repository import GLib

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.session import Session, format_remaining_time
from insomnia.session_manager import SessionManager
from insomnia.system.browser_throttle import BrowserThrottle
from insomnia.system.tmux_nudge import TmuxNudge
from insomnia.ui.settings_dialog import SettingsDialog


class StatusNotifierTray(dbus.service.Object):
    """Full implementation of org.kde.StatusNotifierItem and com.canonical.dbusmenu."""

    def __init__(
        self,
        bus: dbus.SessionBus,
        session_mgr: SessionManager,
        paths: Paths,
        config: Config,
        icons_dir: Path,
    ) -> None:
        self.bus = bus
        self.session_mgr = session_mgr
        self.paths = paths
        self.config = config
        self.icons_dir = icons_dir

        self.service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.bus_name = dbus.service.BusName(self.service_name, self.bus)

        # Register SNI and Menu paths
        super().__init__(self.bus, "/StatusNotifierItem")

        self.menu_revision = 1
        self._menu_actions: Dict[int, Callable[[], None]] = {}

        # Set up menu service object
        self._setup_dbusmenu()

        # Connect session manager callbacks
        self.session_mgr.add_on_change_callback(self.on_session_changed)

        # Register with watcher
        self._register_with_watcher()

    def _register_with_watcher(self) -> None:
        try:
            watcher = self.bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
            watcher.RegisterStatusNotifierItem(self.service_name, dbus_interface="org.kde.StatusNotifierWatcher")
        except Exception as err:
            sys.stderr.write(f"Notice: Could not register with StatusNotifierWatcher: {err}\n")

    def on_session_changed(self, session: Optional[Session]) -> None:
        self.menu_revision += 1
        self.LayoutUpdated(dbus.UInt32(self.menu_revision), 0)
        self.NewIcon()
        self.NewTitle()
        self.NewToolTip()
        self.NewStatus(self.GetStatus())

    def GetStatus(self) -> str:
        session = self.session_mgr.get_active_session()
        return "Active" if session is not None else "Passive"

    def GetIconName(self) -> str:
        session = self.session_mgr.get_active_session()
        if session is not None:
            icon_path = self.icons_dir / "insomnia-32.png"
        else:
            icon_path = self.icons_dir / "insomnia-idle-32.png"
        return str(icon_path) if icon_path.exists() else "weather-clear"

    def GetTitle(self) -> str:
        session = self.session_mgr.get_active_session()
        if session is not None:
            return f"Insomnia ({format_remaining_time(session.remaining())})"
        return "Insomnia"

    # --- org.kde.StatusNotifierItem DBus Interface ---

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def ContextMenu(self, x: int, y: int) -> None:
        pass

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def Activate(self, x: int, y: int) -> None:
        # Clicking icon toggles quick 4h session if idle, or extends by 30m if active
        session = self.session_mgr.get_active_session()
        if session is None:
            self.session_mgr.start_session(self.config.default_preset)
        else:
            self.session_mgr.extend_session(1800.0)

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def SecondaryActivate(self, x: int, y: int) -> None:
        self.session_mgr.end_session()

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="is", out_signature="")
    def Scroll(self, delta: int, orientation: str) -> None:
        pass

    # Signals
    @dbus.service.signal("org.kde.StatusNotifierItem")
    def NewTitle(self) -> None:
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem")
    def NewIcon(self) -> None:
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem")
    def NewAttentionIcon(self) -> None:
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem")
    def NewOverlayIcon(self) -> None:
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem")
    def NewToolTip(self) -> None:
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem", signature="s")
    def NewStatus(self, status: str) -> None:
        pass

    # Properties
    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str) -> Any:
        props = self.GetAll(interface_name)
        return props.get(property_name, "")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str) -> Dict[str, Any]:
        session = self.session_mgr.get_active_session()
        rem_str = format_remaining_time(session.remaining()) if session else "Inactive"
        icon_name = self.GetIconName()
        title = self.GetTitle()

        return {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String("insomnia"),
            "Title": dbus.String(title),
            "Status": dbus.String("Active" if session else "Passive"),
            "WindowId": dbus.Int32(0),
            "IconName": dbus.String(icon_name),
            "IconThemePath": dbus.String(str(self.icons_dir)),
            "OverlayIconName": dbus.String(""),
            "AttentionIconName": dbus.String(""),
            "AttentionMovieName": dbus.String(""),
            "ItemIsMenu": dbus.Boolean(True),
            "Menu": dbus.ObjectPath("/MenuBar"),
            "ToolTip": dbus.Struct(
                (
                    dbus.String(icon_name),
                    dbus.Array([], signature="(iiay)"),
                    dbus.String(f"Insomnia Keep-Awake: {rem_str}"),
                    dbus.String("Prevents sleep and lid-close suspension via systemd logind"),
                ),
                signature="(sa(iiay)ss)",
            ),
        }

    # --- com.canonical.dbusmenu Interface ---

    def _setup_dbusmenu(self) -> None:
        class DBusMenuProxy(dbus.service.Object):
            def __init__(proxy_self, parent: StatusNotifierTray):
                super().__init__(parent.bus, "/MenuBar")
                proxy_self.parent = parent

            @dbus.service.method("com.canonical.dbusmenu", in_signature="iias", out_signature="u(ia{sv}av)")
            def GetLayout(proxy_self, parent_id: int, recursion_depth: int, property_names: List[str]):
                return proxy_self.parent._get_menu_layout(parent_id)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="aias", out_signature="a(ia{sv})")
            def GetGroupProperties(proxy_self, ids: List[int], property_names: List[str]):
                return dbus.Array([], signature="(ia{sv})")

            @dbus.service.method("com.canonical.dbusmenu", in_signature="isvu", out_signature="")
            def Event(proxy_self, item_id: int, event_id: str, data: Any, timestamp: int):
                if event_id == "clicked":
                    proxy_self.parent._handle_menu_click(item_id)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="i", out_signature="b")
            def AboutToShow(proxy_self, item_id: int) -> bool:
                return dbus.Boolean(True)

            @dbus.service.signal("com.canonical.dbusmenu", signature="ui")
            def LayoutUpdated(proxy_self, revision: int, parent_id: int):
                pass

        self._menu_proxy = DBusMenuProxy(self)
        self.LayoutUpdated = self._menu_proxy.LayoutUpdated

    def _get_menu_layout(self, parent_id: int) -> Any:
        self._menu_actions.clear()
        session = self.session_mgr.get_active_session()
        is_active = session is not None

        items: List[Any] = []
        item_id = 1

        def add_item(label: str, action: Optional[Callable[[], None]] = None, enabled: bool = True, is_sep: bool = False):
            nonlocal item_id
            current_id = item_id
            item_id += 1

            props: Dict[str, Any] = {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(enabled),
                "visible": dbus.Boolean(True),
            }
            if is_sep:
                props["type"] = dbus.String("separator")

            if action is not None:
                self._menu_actions[current_id] = action

            struct_item = dbus.Struct(
                (current_id, dbus.Dictionary(props, signature="sv"), dbus.Array([], signature="v")),
                signature="ia{sv}av",
            )
            items.append(struct_item)

        # 1. Status header
        if is_active:
            rem = format_remaining_time(session.remaining())
            add_item(f"● Active ({rem} remaining)", enabled=False)
        else:
            add_item("○ Inactive (Sleep allowed)", enabled=False)

        add_item("", is_sep=True)

        # 2. Quick Durations
        add_item("Keep Awake: 30 Minutes", lambda: self.session_mgr.start_session(1800.0))
        add_item("Keep Awake: 1 Hour", lambda: self.session_mgr.start_session(3600.0))
        add_item("Keep Awake: 2 Hours", lambda: self.session_mgr.start_session(7200.0))
        add_item("Keep Awake: 4 Hours (Default)", lambda: self.session_mgr.start_session(14400.0))
        add_item("Keep Awake: 8 Hours", lambda: self.session_mgr.start_session(28800.0))

        add_item("", is_sep=True)

        # 3. Add Time
        add_item("+15 Minutes", lambda: self.session_mgr.extend_session(900.0), enabled=is_active)
        add_item("+30 Minutes", lambda: self.session_mgr.extend_session(1800.0), enabled=is_active)
        add_item("+1 Hour", lambda: self.session_mgr.extend_session(3600.0), enabled=is_active)

        # 4. End Early
        add_item("End Session Early", lambda: self.session_mgr.end_session(), enabled=is_active)

        add_item("", is_sep=True)

        # 5. Battery and power status
        pct, stat = BatteryMonitor.get_battery_info()
        prof = BatteryMonitor.get_power_profile() or "default"
        if pct is not None:
            add_item(f"Battery: {pct}% ({stat}) - Profile: {prof}", enabled=False)

        # 6. Helpers: Tmux nudge & Browser unthrottling
        add_item("Unthrottle Chromium Browsers", self._unthrottle_browsers)
        if self.config.tmux_targets:
            add_item("Nudge Tmux Panes Now", self._nudge_tmux)

        add_item("", is_sep=True)

        # 7. Settings and Quit
        add_item("Settings...", self._open_settings)
        add_item("Quit Insomnia", self._quit)

        root_props = dbus.Dictionary({"children-display": dbus.String("submenu")}, signature="sv")
        layout = dbus.Struct(
            (0, root_props, dbus.Array(items, signature="v")),
            signature="ia{sv}av",
        )
        return dbus.UInt32(self.menu_revision), layout

    def _handle_menu_click(self, item_id: int) -> None:
        action = self._menu_actions.get(item_id)
        if action:
            try:
                action()
            except Exception as err:
                sys.stderr.write(f"Menu action error: {err}\n")

    def _unthrottle_browsers(self) -> None:
        browsers = BrowserThrottle.get_throttled_browsers()
        for b in browsers:
            BrowserThrottle.relaunch_unthrottled(b)

    def _nudge_tmux(self) -> None:
        TmuxNudge.nudge_all(self.config.tmux_targets, self.config.tmux_nudge_presses_enter)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.paths, self.config)
        res = dialog.run()
        if res == 1:  # GTK OK
            dialog.apply_settings()
        dialog.destroy()

    def _quit(self) -> None:
        self.session_mgr.end_session()
        sys.exit(0)
