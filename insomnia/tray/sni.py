from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import dbus
import dbus.service
from PIL import Image

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.session import Session, format_remaining_time
from insomnia.session_manager import SessionManager
from insomnia.system.browser_throttle import BrowserThrottle
from insomnia.system.tmux_nudge import TmuxNudge
from insomnia.ui.settings_dialog import SettingsDialog


def make_pixmap_struct(image_path: Path, size: int = 32) -> Optional[dbus.Struct]:
    if not image_path.exists():
        return None
    try:
        img = Image.open(image_path).convert("RGBA").resize((size, size))
        raw = bytearray()
        # SNI expects network byte order ARGB32 (Alpha, Red, Green, Blue)
        for pixel in list(img.getdata()):
            r, g, b, a = pixel
            raw.extend([a, r, g, b])
        return dbus.Struct(
            (dbus.Int32(size), dbus.Int32(size), dbus.ByteArray(bytes(raw))),
            signature="iiay",
        )
    except Exception:
        return None


class StatusNotifierTray(dbus.service.Object):
    """Robust StatusNotifierItem and com.canonical.dbusmenu implementation for GNOME Shell."""

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

        super().__init__(self.bus, "/StatusNotifierItem")

        self.menu_revision = 1
        self._menu_actions: Dict[int, Callable[[], None]] = {}
        self._menu_items: Dict[int, Dict[str, Any]] = {}

        # Pre-generate icon pixmaps
        self._active_pixmap = make_pixmap_struct(self.icons_dir / "insomnia-32.png", 32)
        self._idle_pixmap = make_pixmap_struct(self.icons_dir / "insomnia-idle-32.png", 32)

        self._setup_dbusmenu()
        self.session_mgr.add_on_change_callback(self.on_session_changed)
        self._register_with_watcher()

    def _register_with_watcher(self) -> None:
        try:
            watcher = self.bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
            watcher.RegisterStatusNotifierItem(self.service_name, dbus_interface="org.kde.StatusNotifierWatcher")
        except Exception as err:
            sys.stderr.write(f"Notice: StatusNotifierWatcher registration: {err}\n")

    def on_session_changed(self, session: Optional[Session]) -> None:
        self.menu_revision += 1
        self._refresh_menu_items()
        self.LayoutUpdated(dbus.UInt32(self.menu_revision), dbus.Int32(0))
        self.NewIcon()
        self.NewTitle()
        self.NewToolTip()
        self.NewStatus(self.GetStatus())

    def GetStatus(self) -> str:
        session = self.session_mgr.get_active_session()
        return "Active" if session is not None else "Passive"

    def GetIconName(self) -> str:
        session = self.session_mgr.get_active_session()
        return "insomnia" if session is not None else "insomnia-idle"

    def GetTitle(self) -> str:
        session = self.session_mgr.get_active_session()
        if session is not None:
            return f"Insomnia ({format_remaining_time(session.remaining())})"
        return "Insomnia"

    # --- org.kde.StatusNotifierItem Interface ---

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def ContextMenu(self, x: int, y: int) -> None:
        pass

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def Activate(self, x: int, y: int) -> None:
        # Left click opens settings
        self._open_settings()

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="ii", out_signature="")
    def SecondaryActivate(self, x: int, y: int) -> None:
        # Middle click toggles session
        session = self.session_mgr.get_active_session()
        if session is None:
            self.session_mgr.start_session(self.config.default_preset)
        else:
            self.session_mgr.end_session()

    @dbus.service.method("org.kde.StatusNotifierItem", in_signature="is", out_signature="")
    def Scroll(self, delta: int, orientation: str) -> None:
        pass

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

        pixmaps = []
        target_pix = self._active_pixmap if session else self._idle_pixmap
        if target_pix:
            pixmaps.append(target_pix)

        return {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String("insomnia"),
            "Title": dbus.String(title),
            "Status": dbus.String("Active" if session else "Passive"),
            "WindowId": dbus.Int32(0),
            "IconName": dbus.String(icon_name),
            "IconPixmap": dbus.Array(pixmaps, signature="(iiay)"),
            "IconThemePath": dbus.String(str(self.icons_dir)),
            "OverlayIconName": dbus.String(""),
            "AttentionIconName": dbus.String(""),
            "AttentionMovieName": dbus.String(""),
            "ItemIsMenu": dbus.Boolean(True),
            "Menu": dbus.ObjectPath("/MenuBar"),
            "ToolTip": dbus.Struct(
                (
                    dbus.String(icon_name),
                    dbus.Array(pixmaps, signature="(iiay)"),
                    dbus.String(f"Insomnia Keep-Awake: {rem_str}"),
                    dbus.String("Prevents sleep and lid-close suspension via systemd logind"),
                ),
                signature="(sa(iiay)ss)",
            ),
        }

    # --- com.canonical.dbusmenu Interface ---

    def _setup_dbusmenu(self) -> None:
        tray = self

        class DBusMenuService(dbus.service.Object):
            def __init__(self, bus, path):
                super().__init__(bus, path)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="iias", out_signature="u(ia{sv}av)")
            def GetLayout(self, parent_id: int, recursion_depth: int, property_names: List[str]):
                return tray._get_menu_layout(parent_id)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="aias", out_signature="a(ia{sv})")
            def GetGroupProperties(self, ids: List[int], property_names: List[str]):
                return tray._get_group_properties(ids, property_names)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="is", out_signature="v")
            def GetProperty(self, item_id: int, name: str) -> Any:
                return tray._get_single_property(item_id, name)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="isvu", out_signature="")
            def Event(self, item_id: int, event_id: str, data: Any, timestamp: int):
                if event_id == "clicked":
                    tray._handle_menu_click(item_id)

            @dbus.service.method("com.canonical.dbusmenu", in_signature="i", out_signature="b")
            def AboutToShow(self, item_id: int) -> bool:
                return dbus.Boolean(True)

            @dbus.service.signal("com.canonical.dbusmenu", signature="ui")
            def LayoutUpdated(self, revision: int, parent_id: int):
                pass

        self._menu_service = DBusMenuService(self.bus, "/MenuBar")
        self.LayoutUpdated = self._menu_service.LayoutUpdated
        self._refresh_menu_items()

    def _refresh_menu_items(self) -> None:
        self._menu_actions.clear()
        self._menu_items.clear()
        session = self.session_mgr.get_active_session()
        is_active = session is not None

        item_id = 1

        def register(label: str, action: Optional[Callable[[], None]] = None, enabled: bool = True, is_sep: bool = False) -> int:
            nonlocal item_id
            cid = item_id
            item_id += 1

            props: Dict[str, Any] = {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(enabled),
                "visible": dbus.Boolean(True),
            }
            if is_sep:
                props["type"] = dbus.String("separator")

            self._menu_items[cid] = props
            if action:
                self._menu_actions[cid] = action
            return cid

        # Status
        if is_active:
            rem = format_remaining_time(session.remaining())
            register(f"● Active ({rem} remaining)", enabled=False)
        else:
            register("○ Inactive (Sleep allowed)", enabled=False)

        register("", is_sep=True)

        # Quick durations
        register("Keep Awake: 30 Minutes", lambda: self.session_mgr.start_session(1800.0))
        register("Keep Awake: 1 Hour", lambda: self.session_mgr.start_session(3600.0))
        register("Keep Awake: 2 Hours", lambda: self.session_mgr.start_session(7200.0))
        register("Keep Awake: 4 Hours (Default)", lambda: self.session_mgr.start_session(14400.0))
        register("Keep Awake: 8 Hours", lambda: self.session_mgr.start_session(28800.0))

        register("", is_sep=True)

        # Extend & End
        register("+15 Minutes", lambda: self.session_mgr.extend_session(900.0), enabled=is_active)
        register("+30 Minutes", lambda: self.session_mgr.extend_session(1800.0), enabled=is_active)
        register("+1 Hour", lambda: self.session_mgr.extend_session(3600.0), enabled=is_active)
        register("End Session Early", lambda: self.session_mgr.end_session(), enabled=is_active)

        register("", is_sep=True)

        # Battery / helpers
        pct, stat = BatteryMonitor.get_battery_info()
        prof = BatteryMonitor.get_power_profile() or "default"
        if pct is not None:
            register(f"Battery: {pct}% ({stat}) - Profile: {prof}", enabled=False)

        register("Unthrottle Chromium Browsers", self._unthrottle_browsers)
        if self.config.tmux_targets:
            register("Nudge Tmux Panes Now", self._nudge_tmux)

        register("", is_sep=True)
        register("Settings...", self._open_settings)
        register("Quit Insomnia", self._quit)

    def _get_menu_layout(self, parent_id: int) -> Any:
        self._refresh_menu_items()

        items = []
        for cid, props in sorted(self._menu_items.items()):
            struct_item = dbus.Struct(
                (cid, dbus.Dictionary(props, signature="sv"), dbus.Array([], signature="v")),
                signature="ia{sv}av",
            )
            items.append(struct_item)

        root_props = dbus.Dictionary({"children-display": dbus.String("submenu")}, signature="sv")
        layout = dbus.Struct(
            (0, root_props, dbus.Array(items, signature="v")),
            signature="ia{sv}av",
        )
        return dbus.UInt32(self.menu_revision), layout

    def _get_group_properties(self, ids: List[int], property_names: List[str]) -> Any:
        res = []
        for cid in ids:
            if cid == 0:
                props = dbus.Dictionary({"children-display": dbus.String("submenu")}, signature="sv")
                res.append(dbus.Struct((dbus.Int32(0), props), signature="ia{sv}"))
            elif cid in self._menu_items:
                props = dbus.Dictionary(self._menu_items[cid], signature="sv")
                res.append(dbus.Struct((dbus.Int32(cid), props), signature="ia{sv}"))
        return dbus.Array(res, signature="(ia{sv})")

    def _get_single_property(self, item_id: int, name: str) -> Any:
        if item_id == 0 and name == "children-display":
            return dbus.String("submenu")
        if item_id in self._menu_items and name in self._menu_items[item_id]:
            return self._menu_items[item_id][name]
        return dbus.String("")

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
        if res == 1:
            dialog.apply_settings()
        dialog.destroy()

    def _quit(self) -> None:
        self.session_mgr.end_session()
        sys.exit(0)
