import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import cairo from 'gi://cairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import { parseDurationSeconds, formatTimeRemaining, LogindInhibitor, shouldCutoffSession } from './lib/utils.js';

// UPower & PowerProfiles Monitor
class PowerMonitor {
    constructor(settings, onEmergencyEnd) {
        this._settings = settings;
        this._onEmergencyEnd = onEmergencyEnd;
        this._bus = Gio.DBus.system;
        this._upower = null;
        this._displayDevice = null;
        this._upowerSignalId = null;
        this._displaySignalId = null;
        this._settingsSignalId = null;
        this._batteryPercent = 100;
        this._onBattery = false;
        this._lidIsClosed = false;
        this._initUPower();
    }

    _initUPower() {
        try {
            this._upower = new Gio.DBusProxy({
                g_connection: this._bus,
                g_name: 'org.freedesktop.UPower',
                g_object_path: '/org/freedesktop/UPower',
                g_interface_name: 'org.freedesktop.UPower',
            });
            this._upower.init(null);

            this._displayDevice = new Gio.DBusProxy({
                g_connection: this._bus,
                g_name: 'org.freedesktop.UPower',
                g_object_path: '/org/freedesktop/UPower/devices/DisplayDevice',
                g_interface_name: 'org.freedesktop.UPower.Device',
            });
            this._displayDevice.init(null);

            this._updateProperties();

            this._upowerSignalId = this._upower.connect('g-properties-changed', () => {
                this._updateProperties();
            });

            this._displaySignalId = this._displayDevice.connect('g-properties-changed', () => {
                this._updateProperties();
            });

            if (this._settings) {
                this._settingsSignalId = this._settings.connect('changed', (settings, key) => {
                    if (key === 'battery-cutoff-enabled' || key === 'end-floor' || key === 'auto-power-saver' || key === 'low-power-floor') {
                        this._enforceBatteryRules();
                    }
                });
            }
        } catch (e) {
            console.error('Insomnia: Failed to initialize UPower proxies', e);
        }
    }

    _updateProperties() {
        if (!this._upower) return;
        this._lidIsClosed = this._upower.get_cached_property('LidIsClosed')?.unpack() ?? false;
        this._onBattery = this._upower.get_cached_property('OnBattery')?.unpack() ?? false;

        // Check DisplayDevice for battery percentage
        if (this._displayDevice) {
            try {
                const pct = this._displayDevice.get_cached_property('Percentage')?.unpack();
                if (pct !== undefined) {
                    this._batteryPercent = Math.round(pct);
                }
            } catch (e) {
                // Display device properties not accessible
            }
        }

        this._enforceBatteryRules();
    }

    _enforceBatteryRules() {
        if (!this._onBattery) return;

        const cutoffEnabled = this._settings ? this._settings.get_boolean('battery-cutoff-enabled') : false;
        const endFloor = this._settings ? this._settings.get_int('end-floor') : 0;
        if (shouldCutoffSession({
            onBattery: this._onBattery,
            batteryPercent: this._batteryPercent,
            cutoffEnabled,
            endFloor,
        })) {
            if (this._onEmergencyEnd) {
                this._onEmergencyEnd(this._batteryPercent, endFloor);
            }
            return;
        }

        const autoSaver = this._settings ? this._settings.get_boolean('auto-power-saver') : false;
        const lowPowerFloor = this._settings ? this._settings.get_int('low-power-floor') : 40;
        if (autoSaver && this._batteryPercent <= lowPowerFloor) {
            this.setPowerProfile('power-saver');
        }
    }

    destroy() {
        if (this._settingsSignalId && this._settings) {
            this._settings.disconnect(this._settingsSignalId);
            this._settingsSignalId = null;
        }
        if (this._upowerSignalId && this._upower) {
            this._upower.disconnect(this._upowerSignalId);
            this._upowerSignalId = null;
        }
        if (this._displaySignalId && this._displayDevice) {
            this._displayDevice.disconnect(this._displaySignalId);
            this._displaySignalId = null;
        }
    }

    setPowerProfile(profile) {
        try {
            const proxy = new Gio.DBusProxy({
                g_connection: this._bus,
                g_name: 'net.hadess.PowerProfiles',
                g_object_path: '/net/hadess/PowerProfiles',
                g_interface_name: 'org.freedesktop.DBus.Properties',
            });
            proxy.init(null);
            proxy.Set('(ssv)', [
                'net.hadess.PowerProfiles',
                'ActiveProfile',
                new GLib.Variant('s', profile),
            ]);
        } catch (e) {
            // PowerProfiles daemon not available
        }
    }

    get lidIsClosed() { return this._lidIsClosed; }
    get onBattery() { return this._onBattery; }
    get batteryPercent() { return this._batteryPercent; }
}

// Vector Eye Mark matching EyeMarkGeometry on 24x24 grid
const EyeMarkArea = GObject.registerClass(
class EyeMarkArea extends St.DrawingArea {
    _init(params = {}) {
        super._init(Object.assign({
            width: 22,
            height: 22,
            reactive: true,
            can_focus: false,
        }, params));
        this._isRunning = false;
        this.connect('repaint', this._onRepaint.bind(this));
    }

    setRunning(running) {
        if (this._isRunning !== running) {
            this._isRunning = running;
            this.queue_repaint();
        }
    }

    _onRepaint(area) {
        const cr = area.get_context();
        const [w, h] = area.get_surface_size();

        cr.save();
        const scale = Math.min(w, h) / 24.0;
        const ox = (w - 24.0 * scale) / 2.0;
        const oy = (h - 24.0 * scale) / 2.0;
        cr.translate(ox, oy);
        cr.scale(scale, scale);

        // Outer eye lens: M1.5 12 C7 4.5 17 4.5 22.5 12 C17 19.5 7 19.5 1.5 12 Z
        cr.moveTo(1.5, 12);
        cr.curveTo(7, 4.5, 17, 4.5, 22.5, 12);
        cr.curveTo(17, 19.5, 7, 19.5, 1.5, 12);
        cr.closePath();

        if (!this._isRunning) {
            // Idle state: closed eye with shaded lid and lashes below
            cr.setSourceRGBA(1.0, 1.0, 1.0, 0.92);
            cr.fillPreserve();
            cr.setLineWidth(1.5);
            cr.stroke();

            cr.setLineWidth(1.5);
            cr.setLineCap(cairo.LineCap.ROUND);
            const lashesBelow = [
                [4.55, 17.80, 3.14, 20.17],
                [8.26, 19.38, 7.55, 22.03],
                [12.0, 19.88, 12.0, 22.63],
                [15.74, 19.38, 16.45, 22.03],
                [19.45, 17.80, 20.86, 20.17],
            ];
            for (const [x1, y1, x2, y2] of lashesBelow) {
                cr.moveTo(x1, y1);
                cr.lineTo(x2, y2);
            }
            cr.stroke();
        } else {
            // Running state: open eye with pupil and lashes above
            cr.setSourceRGBA(1.0, 1.0, 1.0, 0.95);
            cr.setLineWidth(1.5);
            cr.setLineCap(cairo.LineCap.ROUND);
            cr.stroke();

            // Pupil with highlight bite
            cr.arc(12, 12, 3.6, 0, 2 * Math.PI);
            cr.fill();

            // Cut highlight bite into upper-right of pupil
            cr.setSourceRGBA(0.12, 0.13, 0.14, 1.0);
            cr.arc(13.6, 10.4, 1.3, 0, 2 * Math.PI);
            cr.fill();

            // Lashes above
            cr.setSourceRGBA(1.0, 1.0, 1.0, 0.95);
            cr.setLineWidth(1.5);
            const lashesAbove = [
                [4.55, 6.20, 3.14, 3.83],
                [8.26, 4.62, 7.55, 1.97],
                [12.0, 4.13, 12.0, 1.38],
                [15.74, 4.62, 16.45, 1.97],
                [19.45, 6.20, 20.86, 3.83],
            ];
            for (const [x1, y1, x2, y2] of lashesAbove) {
                cr.moveTo(x1, y1);
                cr.lineTo(x2, y2);
            }
            cr.stroke();
        }

        cr.restore();
        cr.$dispose();
    }
});

// Hold-to-End Button with circular progress ring
const HoldToEndButton = GObject.registerClass(
class HoldToEndButton extends St.DrawingArea {
    _init(onCompleted) {
        super._init({
            width: 20,
            height: 20,
            reactive: true,
            can_focus: false,
        });
        this._progress = 0.0;
        this._holdingTimer = null;
        this._onCompleted = onCompleted;

        this.connect('repaint', this._onRepaint.bind(this));
        this.connect('button-press-event', this._onButtonPress.bind(this));
        this.connect('button-release-event', this._onButtonRelease.bind(this));
        this.connect('leave-event', this._onLeave.bind(this));
    }

    reset() {
        this._stopTimer();
        this._progress = 0.0;
        this.queue_repaint();
    }

    _stopTimer() {
        if (this._holdingTimer) {
            GLib.source_remove(this._holdingTimer);
            this._holdingTimer = null;
        }
    }

    _onButtonPress(actor, event) {
        if (event.get_button() !== 1) return Clutter.EVENT_PROPAGATE;

        this._stopTimer();
        const intervalMs = 25;
        const totalDurationMs = 600.0; // 0.6s hold as per spec
        const step = intervalMs / totalDurationMs;

        this._holdingTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, intervalMs, () => {
            this._progress += step;
            if (this._progress >= 1.0) {
                this._progress = 1.0;
                this.queue_repaint();
                this._stopTimer();
                if (this._onCompleted) {
                    this._onCompleted();
                }
                this._progress = 0.0;
                this.queue_repaint();
                return GLib.SOURCE_REMOVE;
            }
            this.queue_repaint();
            return GLib.SOURCE_CONTINUE;
        });

        return Clutter.EVENT_STOP;
    }

    _onButtonRelease(actor, event) {
        if (event.get_button() === 1) {
            this.reset();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _onLeave() {
        this.reset();
        return Clutter.EVENT_PROPAGATE;
    }

    _onRepaint(area) {
        const cr = area.get_context();
        const [w, h] = area.get_surface_size();

        cr.save();
        const cx = w / 2.0;
        const cy = h / 2.0;
        const r = Math.min(w, h) / 2.0 - 2.0;

        // Background track circle
        cr.setSourceRGBA(1.0, 1.0, 1.0, 0.16);
        cr.setLineWidth(1.6);
        cr.arc(cx, cy, r, 0, 2 * Math.PI);
        cr.stroke();

        // Progress arc
        if (this._progress > 0) {
            cr.setSourceRGBA(0.65, 0.73, 0.76, 1.0); // #A6BBC3
            cr.setLineWidth(2.2);
            cr.setLineCap(cairo.LineCap.ROUND);
            const startAngle = -Math.PI / 2.0;
            const endAngle = startAngle + (this._progress * 2.0 * Math.PI);
            cr.arc(cx, cy, r, startAngle, endAngle);
            cr.stroke();
        }

        // Center ✕ mark
        const arm = 3.6;
        cr.setSourceRGBA(1.0, 1.0, 1.0, 0.90);
        cr.setLineWidth(1.8);
        cr.setLineCap(cairo.LineCap.ROUND);
        cr.moveTo(cx - arm, cy - arm);
        cr.lineTo(cx + arm, cy + arm);
        cr.moveTo(cx + arm, cy - arm);
        cr.lineTo(cx - arm, cy + arm);
        cr.stroke();

        cr.restore();
        cr.$dispose();
    }
});

// Main Panel Indicator Button
const InsomniaIndicator = GObject.registerClass(
class InsomniaIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, 'Insomnia Keep-Awake', false);
        this._ext = extension;
        this._settings = extension.getSettings();

        this._mode = 'IDLE'; // 'IDLE' | 'ENTERING' | 'RUNNING'
        this._remainingSeconds = 0;
        this._timerId = null;

        this._inhibitor = new LogindInhibitor();
        this._power = new PowerMonitor(this._settings, (batteryPct, threshold) => {
            if (this._mode === 'RUNNING') {
                this._endSession();
                Main.notify(
                    'Insomnia Keep-Awake',
                    `Battery fell to ${batteryPct}% (cutoff floor: ${threshold}%). Session ended.`
                );
            }
        });

        // Container box
        this._box = new St.BoxLayout({
            style_class: 'insomnia-indicator-box',
            reactive: true,
        });
        this.add_child(this._box);

        // 1. Vector Eye Mark
        this._eyeMark = new EyeMarkArea();
        this._box.add_child(this._eyeMark);
        this._eyeMark.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) {
                this._togglePills();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        // 2. Pills Box (Days, Hours, Minutes)
        this._pillsBox = new St.BoxLayout({
            style_class: 'insomnia-pills-box',
            visible: false,
        });
        this._box.add_child(this._pillsBox);

        this._daysEntry = this._createPillEntry('Days', () => this._hoursEntry, null);
        this._hoursEntry = this._createPillEntry('Hours', () => this._minsEntry, () => this._daysEntry);
        this._minsEntry = this._createPillEntry('Mins', null, () => this._hoursEntry);

        this._pillsBox.add_child(this._daysEntry);
        this._pillsBox.add_child(this._hoursEntry);
        this._pillsBox.add_child(this._minsEntry);

        // 3. Countdown Label
        this._countLabel = new St.Label({
            text: '00:00',
            style_class: 'insomnia-countdown-label',
            y_align: Clutter.ActorAlign.CENTER,
            visible: false,
            reactive: true,
        });
        this._box.add_child(this._countLabel);
        this._countLabel.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) {
                this._togglePills();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        // 4. Hold-to-End Button
        this._endButton = new HoldToEndButton(() => {
            this._endSession();
        });
        this._endButton.visible = false;
        this._box.add_child(this._endButton);

        // 5. Popup Menu
        this._buildMenu();
    }

    _createPillEntry(hint, nextEntryGetter = null, prevEntryGetter = null) {
        const entry = new St.Entry({
            style_class: 'insomnia-pill',
            can_focus: true,
            hint_text: hint,
        });

        const onActivate = () => {
            try {
                this._commitPillDuration();
            } catch (err) {
                console.error('Insomnia _commitPillDuration error:', err);
            }
        };

        // 1. St.Entry activate signal
        if (GObject.signal_lookup('activate', St.Entry)) {
            entry.connect('activate', onActivate);
        }

        // 2. Clutter.Text activate signal
        entry.clutter_text.connect('activate', onActivate);

        // 3. Key press handling on clutter_text and entry
        const handleKeyPress = (actor, event) => {
            const symbol = event.get_key_symbol();
            const keyval = typeof event.get_key_unicode === 'function' ? event.get_key_unicode() : 0;

            // Enter key (Return, KP_Enter, ISO_Enter, or \r / \n)
            if (symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter || symbol === 65293 || symbol === 65421 || keyval === 13 || keyval === 10) {
                onActivate();
                return Clutter.EVENT_STOP;
            } else if (symbol === Clutter.KEY_Escape || symbol === 65307) {
                this._cancelPills();
                return Clutter.EVENT_STOP;
            } else if (symbol === Clutter.KEY_Tab || symbol === Clutter.KEY_ISO_Left_Tab) {
                const next = (symbol === Clutter.KEY_ISO_Left_Tab && prevEntryGetter)
                    ? prevEntryGetter()
                    : (nextEntryGetter ? nextEntryGetter() : null);
                if (next && typeof next.grab_key_focus === 'function') {
                    next.grab_key_focus();
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        };

        entry.clutter_text.connect('key-press-event', handleKeyPress);
        entry.connect('key-press-event', handleKeyPress);

        return entry;
    }

    _buildMenu() {
        this._statusTitleItem = new PopupMenu.PopupMenuItem('Insomnia: Idle', { reactive: false });
        this.menu.addMenuItem(this._statusTitleItem);

        this._statusDetailItem = new PopupMenu.PopupMenuItem('Lid: Open · Battery: AC', { reactive: false });
        this.menu.addMenuItem(this._statusDetailItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Quick Durations
        const quickDurations = [
            ['15 Minutes', 900],
            ['30 Minutes', 1800],
            ['1 Hour', 3600],
            ['2 Hours', 7200],
            ['4 Hours', 14400],
            ['8 Hours', 28800],
        ];
        for (const [label, secs] of quickDurations) {
            this.menu.addAction(label, () => {
                this._startSession(secs);
            });
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.menu.addAction('End Session', () => {
            this._endSession();
        });

        this.menu.addAction('Preferences…', () => {
            this._ext.openPreferences();
        });
    }

    _togglePills() {
        if (this._mode === 'ENTERING') {
            this._cancelPills();
        } else {
            this._mode = 'ENTERING';
            this._pillsBox.visible = true;
            this._countLabel.visible = false;
            this._endButton.visible = false;

            const clearEntry = (entry) => {
                if (!entry) return;
                if (typeof entry.set_text === 'function') {
                    entry.set_text('');
                } else {
                    entry.text = '';
                }
            };
            clearEntry(this._daysEntry);
            clearEntry(this._hoursEntry);
            clearEntry(this._minsEntry);

            if (this._daysEntry && typeof this._daysEntry.grab_key_focus === 'function') {
                this._daysEntry.grab_key_focus();
            }
        }
    }

    _cancelPills() {
        this._pillsBox.visible = false;
        if (this._inhibitor.isActive) {
            this._mode = 'RUNNING';
            this._countLabel.visible = true;
            this._endButton.visible = true;
        } else {
            this._mode = 'IDLE';
            this._countLabel.visible = false;
            this._endButton.visible = false;
            this._eyeMark.setRunning(false);
        }
    }

    _commitPillDuration() {
        const getVal = (entry) => {
            if (!entry) return '';
            let val = '';
            if (typeof entry.get_text === 'function') {
                val = entry.get_text();
            } else if (entry.clutter_text && typeof entry.clutter_text.get_text === 'function') {
                val = entry.clutter_text.get_text();
            } else if (entry.text) {
                val = entry.text;
            }
            return (val || '').toString().trim();
        };

        const d = getVal(this._daysEntry);
        const h = getVal(this._hoursEntry);
        const m = getVal(this._minsEntry);

        console.log(`Insomnia _commitPillDuration: days='${d}', hours='${h}', mins='${m}'`);

        const secs = parseDurationSeconds(d, h, m);
        console.log(`Insomnia _commitPillDuration: starting session with ${secs} seconds`);

        if (this._inhibitor.isActive) {
            this._extendSession(secs);
        } else {
            this._startSession(secs);
        }
    }

    _startSession(durationSeconds) {
        if (this._power && this._power.onBattery) {
            const cutoffEnabled = this._settings ? this._settings.get_boolean('battery-cutoff-enabled') : false;
            const endFloor = this._settings ? this._settings.get_int('end-floor') : 0;
            if (shouldCutoffSession({
                onBattery: this._power.onBattery,
                batteryPercent: this._power.batteryPercent,
                cutoffEnabled,
                endFloor,
            })) {
                Main.notify(
                    'Insomnia Keep-Awake',
                    `Battery is low (${this._power.batteryPercent}% <= ${endFloor}%). Cannot start keep-awake session.`
                );
                this._cancelPills();
                return;
            }
        }

        this._remainingSeconds = durationSeconds;
        this._pillsBox.visible = false;

        const preventLid = this._settings ? this._settings.get_boolean('prevent-lid-sleep') : true;
        this._inhibitor.acquire(preventLid, () => {
            this._updateMenuStatus();
        });

        this._mode = 'RUNNING';
        this._eyeMark.setRunning(true);
        const remFormatted = formatTimeRemaining(this._remainingSeconds);
        if (typeof this._countLabel.set_text === 'function') {
            this._countLabel.set_text(remFormatted);
        } else {
            this._countLabel.text = remFormatted;
        }
        this._countLabel.visible = true;
        this._endButton.visible = true;

        this._startTimer();
        this._updateMenuStatus();
    }

    _extendSession(additionalSeconds) {
        this._remainingSeconds += additionalSeconds;
        this._pillsBox.visible = false;
        const remFormatted = formatTimeRemaining(this._remainingSeconds);
        if (typeof this._countLabel.set_text === 'function') {
            this._countLabel.set_text(remFormatted);
        } else {
            this._countLabel.text = remFormatted;
        }
        this._updateMenuStatus();
    }

    _endSession() {
        this._stopTimer();
        this._inhibitor.release();
        this._remainingSeconds = 0;
        this._mode = 'IDLE';

        this._eyeMark.setRunning(false);
        this._pillsBox.visible = false;
        this._countLabel.visible = false;
        this._endButton.visible = false;

        this._updateMenuStatus();
    }

    _startTimer() {
        this._stopTimer();
        this._timerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._remainingSeconds > 0) {
                this._remainingSeconds -= 1;
                const remFormatted = formatTimeRemaining(this._remainingSeconds);
                if (typeof this._countLabel.set_text === 'function') {
                    this._countLabel.set_text(remFormatted);
                } else {
                    this._countLabel.text = remFormatted;
                }
                return GLib.SOURCE_CONTINUE;
            }
            this._endSession();
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopTimer() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = null;
        }
    }

    _updateMenuStatus() {
        const lid = this._power.lidIsClosed ? 'Closed' : 'Open';
        const batt = this._power.onBattery ? `${this._power.batteryPercent}%` : 'AC Power';

        if (this._inhibitor.isActive) {
            this._statusTitleItem.label.text = `Insomnia: Active (${formatTimeRemaining(this._remainingSeconds)} left)`;
            this._statusDetailItem.label.text = `Lid: ${lid} · Battery: ${batt} · Sleep Blocked`;
        } else {
            this._statusTitleItem.label.text = 'Insomnia: Idle';
            this._statusDetailItem.label.text = `Lid: ${lid} · Battery: ${batt}`;
        }
    }

    destroy() {
        this._stopTimer();
        this._inhibitor.release();
        if (this._power) {
            this._power.destroy();
            this._power = null;
        }
        super.destroy();
    }
});

export default class InsomniaExtension extends Extension {
    enable() {
        this._indicator = new InsomniaIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'right');
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
