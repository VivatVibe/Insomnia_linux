import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences, gettext as _} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class InsomniaPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({
            title: _('General'),
            icon_name: 'preferences-system-symbolic',
        });
        window.add(page);

        // Group: Power & Safety
        const powerGroup = new Adw.PreferencesGroup({
            title: _('Power & Safety'),
            description: _('Configure battery thresholds and lid-switch behavior during awake sessions.'),
        });
        page.add(powerGroup);

        // Prevent lid sleep switch
        const lidRow = new Adw.SwitchRow({
            title: _('Keep Awake When Lid Closes'),
            subtitle: _('Prevents laptop suspension when the lid is closed while a session is active.'),
        });
        settings.bind('prevent-lid-sleep', lidRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        powerGroup.add(lidRow);

        // Auto power saver switch
        const autoSaverRow = new Adw.SwitchRow({
            title: _('Auto Low Power Mode'),
            subtitle: _('Automatically switch to power-saver profile when battery falls below threshold.'),
        });
        settings.bind('auto-power-saver', autoSaverRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        powerGroup.add(autoSaverRow);

        // Low power threshold spin row
        const lowPowerRow = new Adw.SpinRow({
            title: _('Low Power Battery Threshold'),
            subtitle: _('Percentage below which the power-saver profile is engaged.'),
            adjustment: new Gtk.Adjustment({
                lower: 10,
                upper: 80,
                step_increment: 5,
                page_increment: 10,
            }),
        });
        settings.bind('low-power-floor', lowPowerRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        powerGroup.add(lowPowerRow);

        // Battery Floor Cutoff Switch
        const cutoffSwitchRow = new Adw.SwitchRow({
            title: _('Battery Floor Cutoff'),
            subtitle: _('Automatically end keep-awake session and permit sleep when battery is low.'),
        });
        settings.bind('battery-cutoff-enabled', cutoffSwitchRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        powerGroup.add(cutoffSwitchRow);

        // Battery Floor Cutoff SpinRow
        const endFloorRow = new Adw.SpinRow({
            title: _('Cutoff Battery Threshold'),
            subtitle: _('Stop session and permit sleep if battery falls below this percentage.'),
            adjustment: new Gtk.Adjustment({
                lower: 5,
                upper: 50,
                step_increment: 5,
                page_increment: 10,
            }),
        });
        settings.bind('end-floor', endFloorRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        cutoffSwitchRow.bind_property(
            'active',
            endFloorRow,
            'sensitive',
            GObject.BindingFlags.SYNC_CREATE
        );
        powerGroup.add(endFloorRow);
    }
}
