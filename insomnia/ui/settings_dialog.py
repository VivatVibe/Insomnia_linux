from __future__ import annotations

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.store import Store


class SettingsDialog(Gtk.Dialog):
    """GTK3 Settings Dialog for Insomnia configuration."""

    def __init__(self, paths: Paths, config: Config) -> None:
        super().__init__(title="Insomnia Settings", flags=0)
        self.paths = paths
        self.config = config

        self.set_default_size(460, 480)
        self.set_resizable(False)

        box = self.get_content_area()
        box.set_spacing(12)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        notebook = Gtk.Notebook()
        box.pack_start(notebook, True, True, 0)

        # Tab 1: General & Battery
        notebook.append_page(self._create_battery_tab(), Gtk.Label(label="Power & Battery"))

        # Tab 2: Lid Close Actions
        notebook.append_page(self._create_lid_tab(), Gtk.Label(label="Lid Close"))

        # Tab 3: Automation & Tmux
        notebook.append_page(self._create_automation_tab(), Gtk.Label(label="Automation"))

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        save_btn = self.add_button(Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")

        self.show_all()

    def _create_battery_tab(self) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_margin_top(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)

        # Low power floor
        lbl_low = Gtk.Label(label="Low Power Floor (%):", xalign=0)
        self.scale_low = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.scale_low.set_value(self.config.low_power_floor)
        self.scale_low.set_hexpand(True)
        grid.attach(lbl_low, 0, 0, 1, 1)
        grid.attach(self.scale_low, 1, 0, 1, 1)

        # End floor
        lbl_end = Gtk.Label(label="Emergency End Floor (%):", xalign=0)
        self.scale_end = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 50, 5)
        self.scale_end.set_value(self.config.end_floor)
        self.scale_end.set_hexpand(True)
        grid.attach(lbl_end, 0, 1, 1, 1)
        grid.attach(self.scale_end, 1, 1, 1, 1)

        # Thermal rules
        lbl_therm = Gtk.Label(label="Enable Thermal Safeguards:", xalign=0)
        self.switch_thermal = Gtk.Switch()
        self.switch_thermal.set_active(self.config.thermal_rules)
        grid.attach(lbl_therm, 0, 2, 1, 1)
        grid.attach(self.switch_thermal, 1, 2, 1, 1)

        return grid

    def _create_lid_tab(self) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_margin_top(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)

        # Mute on lid close
        lbl_mute = Gtk.Label(label="Mute Audio on Lid Close:", xalign=0)
        self.switch_mute = Gtk.Switch()
        self.switch_mute.set_active(self.config.mute_on_lid_close)
        grid.attach(lbl_mute, 0, 0, 1, 1)
        grid.attach(self.switch_mute, 1, 0, 1, 1)

        # Darken display
        lbl_darken = Gtk.Label(label="Darken Display on Lid Close:", xalign=0)
        self.switch_darken = Gtk.Switch()
        self.switch_darken.set_active(self.config.darken_display_on_lid_close)
        grid.attach(lbl_darken, 0, 1, 1, 1)
        grid.attach(self.switch_darken, 1, 1, 1, 1)

        # Low power on lid close
        lbl_lp = Gtk.Label(label="Switch to Power Saver Profile on Lid Close:", xalign=0)
        self.switch_lp = Gtk.Switch()
        self.switch_lp.set_active(self.config.low_power_on_lid_close)
        grid.attach(lbl_lp, 0, 2, 1, 1)
        grid.attach(self.switch_lp, 1, 2, 1, 1)

        return grid

    def _create_automation_tab(self) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_margin_top(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)

        lbl_tmux = Gtk.Label(label="Tmux Targets (comma separated):", xalign=0)
        self.entry_tmux = Gtk.Entry()
        self.entry_tmux.set_text(", ".join(self.config.tmux_targets))
        grid.attach(lbl_tmux, 0, 0, 1, 1)
        grid.attach(self.entry_tmux, 1, 0, 1, 1)

        lbl_enter = Gtk.Label(label="Tmux Nudge Presses Enter:", xalign=0)
        self.switch_enter = Gtk.Switch()
        self.switch_enter.set_active(self.config.tmux_nudge_presses_enter)
        grid.attach(lbl_enter, 0, 1, 1, 1)
        grid.attach(self.switch_enter, 1, 1, 1, 1)

        return grid

    def apply_settings(self) -> None:
        self.config.low_power_floor = int(self.scale_low.get_value())
        self.config.end_floor = int(self.scale_end.get_value())
        self.config.thermal_rules = self.switch_thermal.get_active()
        self.config.mute_on_lid_close = self.switch_mute.get_active()
        self.config.darken_display_on_lid_close = self.switch_darken.get_active()
        self.config.low_power_on_lid_close = self.switch_lp.get_active()

        tmux_text = self.entry_tmux.get_text().strip()
        self.config.tmux_targets = [t.strip() for t in tmux_text.split(",") if t.strip()]
        self.config.tmux_nudge_presses_enter = self.switch_enter.get_active()

        Store.write_json(self.paths.config_file, self.config.to_dict())
