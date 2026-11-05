from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GLibUnix, Gtk

from insomnia.backstop import BackstopRunner
from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.power.lid import LidController
from insomnia.session import format_remaining_time, parse_duration_string
from insomnia.session_manager import SessionManager
from insomnia.store import Store
from insomnia.tray.sni import StatusNotifierTray
from insomnia.ui.main_window import MainWindow
from insomnia.ui.settings_dialog import SettingsDialog

logger = logging.getLogger("insomnia")


def cmd_run(args: argparse.Namespace, paths: Paths) -> int:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()

    # Ensure single instance
    try:
        _app_bus_name = dbus.service.BusName(
            "org.vivatvibe.Insomnia",
            bus,
            do_not_queue=True,
        )
    except dbus.exceptions.NameExistsException:
        print("Insomnia is already running in the top bar.")
        return 0

    config_data = Store.read_json(paths.config_file) or {}
    config = Config.from_dict(config_data)

    session_mgr = SessionManager(paths, config)
    lid_ctrl = LidController(paths, config)

    # Locate icons directory
    icons_dir = Path(__file__).parent.parent / "Resources" / "icons"
    if not icons_dir.exists():
        icons_dir = Path("/usr/lib/insomnia/Resources/icons")
    if not icons_dir.exists():
        icons_dir = paths.data_dir / "icons"

    tray = StatusNotifierTray(bus, session_mgr, paths, config, icons_dir)

    loop = GLib.MainLoop()

    # Handle termination signals cleanly
    def handle_signal(*_):
        session_mgr.end_session()
        loop.quit()

    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, handle_signal)
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, handle_signal)

    # Periodic tick every 10 seconds: updates remaining time, enforces battery limits, tracks lid
    was_lid_closed = False

    def periodic_tick():
        nonlocal was_lid_closed
        session = session_mgr.tick()
        tray.on_session_changed(session)

        # Check lid state transition
        is_closed = LidController.is_lid_closed()
        if is_closed and not was_lid_closed:
            was_lid_closed = True
            if session:
                lid_ctrl.handle_lid_closed()
        elif not is_closed and was_lid_closed:
            was_lid_closed = False
            lid_ctrl.handle_lid_opened()

        return True

    GLib.timeout_add_seconds(10, periodic_tick)

    # Also resume any existing valid session
    session = session_mgr.tick()
    tray.on_session_changed(session)

    try:
        loop.run()
    except (KeyboardInterrupt, SystemExit):
        session_mgr.end_session()

    return 0


def cmd_start(args: argparse.Namespace, paths: Paths) -> int:
    duration = parse_duration_string(args.duration)
    mgr = SessionManager(paths)
    session = mgr.start_session(duration)
    rem = format_remaining_time(session.remaining())
    print(f"Insomnia: Session started for {rem}. Sleep and lid-switch suspension inhibited.")
    return 0


def cmd_extend(args: argparse.Namespace, paths: Paths) -> int:
    duration = parse_duration_string(args.duration)
    mgr = SessionManager(paths)
    session = mgr.extend_session(duration)
    if not session:
        print("Insomnia: No active session to extend.", file=sys.stderr)
        return 1
    rem = format_remaining_time(session.remaining())
    print(f"Insomnia: Session extended. Remaining: {rem}.")
    return 0


def cmd_end(args: argparse.Namespace, paths: Paths) -> int:
    mgr = SessionManager(paths)
    mgr.end_session()
    print("Insomnia: Keep-awake session ended. Sleep re-enabled.")
    return 0


def cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    mgr = SessionManager(paths)
    session = mgr.get_active_session()
    pct, bat_status = BatteryMonitor.get_battery_info()
    profile = BatteryMonitor.get_power_profile()
    lid_closed = LidController.is_lid_closed()

    info = {
        "active": session is not None,
        "remaining_seconds": session.remaining() if session else 0.0,
        "remaining_formatted": format_remaining_time(session.remaining()) if session else "00:00",
        "battery_percent": pct,
        "battery_status": bat_status,
        "power_profile": profile,
        "lid_closed": lid_closed,
        "started_at": session.started_at.isoformat() if session else None,
        "ends_at": session.ends_at.isoformat() if session else None,
    }

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        if session:
            print(f"Status: ACTIVE ({info['remaining_formatted']} remaining)")
            print(f"Started: {info['started_at']}")
            print(f"Ends: {info['ends_at']}")
        else:
            print("Status: INACTIVE (Sleep permitted)")
        print(f"Battery: {pct}% ({bat_status})" if pct is not None else "Battery: N/A")
        print(f"Power Profile: {profile or 'N/A'}")
        print(f"Lid Closed: {'Yes' if lid_closed else 'No'}")

    return 0


def cmd_backstop(args: argparse.Namespace, paths: Paths) -> int:
    runner = BackstopRunner(paths)
    return runner.run(force=args.force)


def cmd_settings(args: argparse.Namespace, paths: Paths) -> int:
    config_data = Store.read_json(paths.config_file) or {}
    config = Config.from_dict(config_data)
    dialog = SettingsDialog(paths, config)
    res = dialog.run()
    if res == 1:
        dialog.apply_settings()
        print("Insomnia: Settings saved.")
    dialog.destroy()
    return 0


def cmd_gui(args: argparse.Namespace, paths: Paths) -> int:
    config_data = Store.read_json(paths.config_file) or {}
    config = Config.from_dict(config_data)
    session_mgr = SessionManager(paths, config)

    # If background tray daemon is not running, spawn it in background
    try:
        bus = dbus.SessionBus()
        if not bus.name_has_owner("org.vivatvibe.Insomnia"):
            subprocess.Popen([sys.executable, "-m", "insomnia", "run"], start_new_session=True)
    except Exception:
        pass

    win = MainWindow(paths, config, session_mgr)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def main() -> None:
    if len(sys.argv) == 1:
        sys.argv.append("gui")

    parser = argparse.ArgumentParser(
        prog="insomnia",
        description="Insomnia Linux: keep-awake session manager and lid-close engine for Ubuntu GNOME",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    # gui (default)
    p_gui = subparsers.add_parser("gui", help="Open the Insomnia control center window")
    p_gui.set_defaults(func=cmd_gui)

    # run
    p_run = subparsers.add_parser("run", help="Run the tray indicator and background daemon")
    p_run.set_defaults(func=cmd_run)

    # start
    p_start = subparsers.add_parser("start", help="Start a keep-awake session")
    p_start.add_argument("duration", nargs="?", default="4h", help="Duration (e.g. 30m, 1h, 4h, 8h)")
    p_start.set_defaults(func=cmd_start)

    # extend
    p_extend = subparsers.add_parser("extend", help="Extend the active session")
    p_extend.add_argument("duration", nargs="?", default="30m", help="Additional duration (e.g. 15m, 30m, 1h)")
    p_extend.set_defaults(func=cmd_extend)

    # end
    p_end = subparsers.add_parser("end", help="End the active session early")
    p_end.set_defaults(func=cmd_end)

    # status
    p_status = subparsers.add_parser("status", help="Show current keep-awake status")
    p_status.add_argument("--json", action="store_true", help="Output in JSON format")
    p_status.set_defaults(func=cmd_status)

    # backstop
    p_backstop = subparsers.add_parser("backstop", help="Run backstop reconciliation pass")
    p_backstop.add_argument("--force", action="store_true", help="Force cleanup even if session is not expired")
    p_backstop.set_defaults(func=cmd_backstop)

    # settings
    p_settings = subparsers.add_parser("settings", help="Open configuration dialog")
    p_settings.set_defaults(func=cmd_settings)

    args = parser.parse_args()
    paths = Paths()
    paths.ensure_directories()
    sys.exit(args.func(args, paths))


if __name__ == "__main__":
    main()
