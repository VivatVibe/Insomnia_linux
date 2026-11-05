from __future__ import annotations

from pathlib import Path
from typing import Optional
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.power.lid import LidController
from insomnia.session import Session, format_remaining_time
from insomnia.session_manager import SessionManager
from insomnia.store import Store
from insomnia.ui.animated_eye import AnimatedEye, HoldToEndButton
from insomnia.ui.settings_dialog import SettingsDialog


class MainWindow(Gtk.Window):
    """Modern GNOME Control Center window with vector animated eye and hold-to-end ring."""

    def __init__(self, paths: Paths, config: Config, session_mgr: SessionManager) -> None:
        super().__init__(title="Insomnia")
        self.paths = paths
        self.config = config
        self.session_mgr = session_mgr

        self.set_default_size(440, 540)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Set window icon
        icons_dir = Path(__file__).parent.parent.parent / "Resources" / "icons"
        if not icons_dir.exists():
            icons_dir = Path("/usr/lib/insomnia/Resources/icons")
        if not icons_dir.exists():
            icons_dir = self.paths.data_dir / "icons"

        self.icons_dir = icons_dir
        icon_path = self.icons_dir / "insomnia-128.png"
        if icon_path.exists():
            self.set_icon_from_file(str(icon_path))

        # Main vertical container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        self.add(main_box)

        # 1. Header: Vector Animated Eye + App Name
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        eye_event_box = Gtk.EventBox()
        self.eye = AnimatedEye(size=100)
        eye_event_box.add(self.eye)
        eye_event_box.connect("button-press-event", lambda *_: self.eye.blink())
        header_box.pack_start(eye_event_box, False, False, 0)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span size='large' weight='bold'>Insomnia</span>")
        header_box.pack_start(lbl_title, False, False, 0)

        self.lbl_status = Gtk.Label()
        header_box.pack_start(self.lbl_status, False, False, 0)
        main_box.pack_start(header_box, False, False, 0)

        # 2. Main Action Container: Start Button OR HoldToEndButton
        self.action_stack = Gtk.Stack()
        self.action_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.action_stack.set_transition_duration(200)

        # Inactive state button
        self.btn_start = Gtk.Button(label="Keep Machine Awake (4 Hours)")
        self.btn_start.get_style_context().add_class("suggested-action")
        self.btn_start.set_size_request(-1, 46)
        self.btn_start.connect("clicked", self._on_start_clicked)
        self.action_stack.add_named(self.btn_start, "start")

        # Active state hold-to-end button
        self.btn_hold_end = HoldToEndButton(on_complete=self._on_hold_end_complete)
        self.action_stack.add_named(self.btn_hold_end, "hold_end")

        main_box.pack_start(self.action_stack, False, False, 0)

        # 3. Quick Durations Section
        lbl_quick = Gtk.Label(xalign=0)
        lbl_quick.set_markup("<span size='small' weight='bold' color='#888888'>QUICK DURATIONS</span>")
        main_box.pack_start(lbl_quick, False, False, 0)

        grid_durations = Gtk.Grid()
        grid_durations.set_column_spacing(8)
        grid_durations.set_row_spacing(8)
        grid_durations.set_column_homogeneous(True)

        durations = [
            ("30m", 1800.0),
            ("1h", 3600.0),
            ("2h", 7200.0),
            ("4h", 14400.0),
            ("8h", 28800.0),
        ]
        for idx, (label, secs) in enumerate(durations):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _, s=secs: self._start_custom(s))
            grid_durations.attach(btn, idx, 0, 1, 1)

        main_box.pack_start(grid_durations, False, False, 0)

        # 4. Add Time row (visible & active when session running)
        self.box_extend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_extend.set_homogeneous(True)

        for label, secs in [("+15m", 900.0), ("+30m", 1800.0), ("+1h", 3600.0)]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _, s=secs: self._extend_session(s))
            self.box_extend.pack_start(btn, True, True, 0)

        main_box.pack_start(self.box_extend, False, False, 0)

        # 5. System Status Info Frame
        info_frame = Gtk.Frame()
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_margin_start(12)
        info_box.set_margin_end(12)
        info_box.set_margin_top(8)
        info_box.set_margin_bottom(8)

        self.lbl_battery = Gtk.Label(xalign=0)
        self.lbl_power_profile = Gtk.Label(xalign=0)
        self.lbl_lid = Gtk.Label(xalign=0)

        info_box.pack_start(self.lbl_battery, False, False, 0)
        info_box.pack_start(self.lbl_power_profile, False, False, 0)
        info_box.pack_start(self.lbl_lid, False, False, 0)
        info_frame.add(info_box)
        main_box.pack_start(info_frame, False, False, 0)

        # 6. Bottom Controls: Settings and quit note
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_settings = Gtk.Button(label="Settings...")
        btn_settings.connect("clicked", self._open_settings)
        bottom_box.pack_start(btn_settings, False, False, 0)

        lbl_tray_hint = Gtk.Label(xalign=1)
        lbl_tray_hint.set_markup("<span size='small' color='#888888'>Runs in top bar tray</span>")
        bottom_box.pack_end(lbl_tray_hint, False, False, 0)

        main_box.pack_end(bottom_box, False, False, 0)

        # Initial UI update
        self._update_ui()

        # Connect periodic timer every 1 second for live countdown
        GLib.timeout_add_seconds(1, self._update_ui)

    def _update_ui(self) -> bool:
        session = self.session_mgr.get_active_session()
        is_active = session is not None

        # Update animated vector eye aperture and spring
        self.eye.set_awake(is_active)

        if is_active:
            rem_str = format_remaining_time(session.remaining())
            self.lbl_status.set_markup(
                f"<span size='medium' weight='bold' color='#2ec27e'>● ACTIVE ({rem_str} Remaining)</span>\n"
                f"<span size='small' color='#666666'>Sleep and lid-switch suspension inhibited</span>"
            )
            self.action_stack.set_visible_child_name("hold_end")
            self.box_extend.set_sensitive(True)
        else:
            self.lbl_status.set_markup(
                "<span size='medium' weight='bold' color='#888888'>○ INACTIVE (Sleep Permitted)</span>\n"
                "<span size='small' color='#666666'>Click below to prevent sleep and lid-close suspension</span>"
            )
            self.action_stack.set_visible_child_name("start")
            self.box_extend.set_sensitive(False)

        # Update battery and hardware stats
        pct, status = BatteryMonitor.get_battery_info()
        profile = BatteryMonitor.get_power_profile() or "balanced"
        lid_closed = LidController.is_lid_closed()

        bat_text = f"Battery: {pct}% ({status})" if pct is not None else "Battery: AC Power"
        self.lbl_battery.set_markup(f"<span size='small'>🔋 {bat_text}</span>")
        self.lbl_power_profile.set_markup(f"<span size='small'>⚡ Power Profile: {profile.capitalize()}</span>")
        lid_text = "Closed (Inhibited)" if lid_closed else "Open"
        self.lbl_lid.set_markup(f"<span size='small'>💻 Laptop Lid: {lid_text}</span>")

        return True

    def _on_start_clicked(self, widget: Gtk.Widget) -> None:
        self.session_mgr.start_session(self.config.default_preset)
        self._update_ui()

    def _on_hold_end_complete(self) -> None:
        self.session_mgr.end_session()
        self._update_ui()

    def _start_custom(self, seconds: float) -> None:
        self.session_mgr.start_session(seconds)
        self._update_ui()

    def _extend_session(self, seconds: float) -> None:
        self.session_mgr.extend_session(seconds)
        self._update_ui()

    def _open_settings(self, widget: Gtk.Widget) -> None:
        dialog = SettingsDialog(self.paths, self.config)
        res = dialog.run()
        if res == 1:
            dialog.apply_settings()
        dialog.destroy()
