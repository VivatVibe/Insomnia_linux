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

const InsomniaIface = `
<node>
  <interface name="org.vivatvibe.Insomnia">
    <method name="StartSession">
      <arg type="s" direction="in" name="duration"/>
      <arg type="b" direction="out" name="success"/>
      <arg type="s" direction="out" name="remaining"/>
    </method>
    <method name="ExtendSession">
      <arg type="s" direction="in" name="duration"/>
      <arg type="b" direction="out" name="success"/>
      <arg type="s" direction="out" name="remaining"/>
    </method>
    <method name="EndSession">
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="GetState">
      <arg type="b" direction="out" name="active"/>
      <arg type="x" direction="out" name="remaining_seconds"/>
      <arg type="s" direction="out" name="formatted_remaining"/>
      <arg type="s" direction="out" name="lid_state"/>
      <arg type="s" direction="out" name="battery_str"/>
    </method>
    <method name="OpenSettings">
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="OpenControlCenter">
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="Quit">
      <arg type="b" direction="out" name="success"/>
    </method>
    <signal name="StateChanged">
      <arg type="b" name="active"/>
      <arg type="x" name="remaining_seconds"/>
      <arg type="s" name="formatted_remaining"/>
      <arg type="s" name="lid_state"/>
      <arg type="s" name="battery_str"/>
    </signal>
  </interface>
</node>`;

const InsomniaProxy = Gio.DBusProxy.makeProxyWrapper(InsomniaIface);

// Vector Eye Mark drawing widget matching EyeMarkGeometry on 24x24 grid
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
    _init() {
        super._init(0.5, 'Insomnia Keep-Awake', false);

        this._mode = 'IDLE'; // 'IDLE' | 'ENTERING' | 'RUNNING'
        this._remainingSec = 0;
        this._localTimer = null;

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

        this._daysEntry = this._createPillEntry('Days');
        this._hoursEntry = this._createPillEntry('Hours');
        this._minsEntry = this._createPillEntry('Mins');

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
        this._endButton.set_visible(false);
        this._box.add_child(this._endButton);

        // Setup Right-Click Popup Menu
        this._buildMenu();

        // Connect D-Bus
        this._initDBus();
    }

    _createPillEntry(hint) {
        const entry = new St.Entry({
            style_class: 'insomnia-pill',
            can_focus: true,
        });
        entry.set_hint_text(hint);

        entry.clutter_text.connect('key-press-event', (actor, event) => {
            const symbol = event.get_key_symbol();
            if (symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter) {
                this._commitPillDuration();
                return Clutter.EVENT_STOP;
            } else if (symbol === Clutter.KEY_Escape) {
                this._cancelPills();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

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
            ['15 Minutes', '15m'],
            ['30 Minutes', '30m'],
            ['1 Hour', '1h'],
            ['2 Hours', '2h'],
            ['4 Hours', '4h'],
            ['8 Hours', '8h'],
        ];
        for (const [label, dur] of quickDurations) {
            this.menu.addAction(label, () => {
                this._startDuration(dur);
            });
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.menu.addAction('End Session', () => {
            this._endSession();
        });

        this.menu.addAction('Insomnia Control Center…', () => {
            if (this._proxy) this._proxy.OpenControlCenterRemote(() => {});
        });

        this.menu.addAction('Settings…', () => {
            if (this._proxy) this._proxy.OpenSettingsRemote(() => {});
        });

        this.menu.addAction('Quit Insomnia', () => {
            if (this._proxy) this._proxy.QuitRemote(() => {});
        });
    }

    _initDBus() {
        try {
            this._proxy = new InsomniaProxy(
                Gio.DBus.session,
                'org.vivatvibe.Insomnia',
                '/org/vivatvibe/Insomnia'
            );

            this._sigId = this._proxy.connectSignal('StateChanged', (_proxy, _sender, [active, rem_sec, rem_str, lid, batt]) => {
                this._updateState(active, rem_sec, rem_str, lid, batt);
            });

            // Initial fetch
            this._proxy.GetStateRemote(([active, rem_sec, rem_str, lid, batt], err) => {
                if (!err) {
                    this._updateState(active, rem_sec, rem_str, lid, batt);
                }
            });
        } catch (err) {
            logError(err, 'Failed to connect Insomnia D-Bus proxy');
        }
    }

    _updateState(active, remSec, remStr, lidState, battStr) {
        this._remainingSec = Number(remSec);

        this._statusTitleItem.label.text = active
            ? `Insomnia: Active (${remStr} remaining)`
            : 'Insomnia: Idle';
        this._statusDetailItem.label.text = `Lid: ${lidState} · Battery: ${battStr}`;

        if (active) {
            this._mode = 'RUNNING';
            this._eyeMark.setRunning(true);
            this._pillsBox.set_visible(false);
            this._countLabel.set_text(remStr);
            this._countLabel.set_visible(true);
            this._endButton.set_visible(true);
            this._startLocalCountdown();
        } else {
            if (this._mode !== 'ENTERING') {
                this._mode = 'IDLE';
                this._eyeMark.setRunning(false);
                this._pillsBox.set_visible(false);
                this._countLabel.set_visible(false);
                this._endButton.set_visible(false);
            }
            this._stopLocalCountdown();
        }
    }

    _startLocalCountdown() {
        this._stopLocalCountdown();
        this._localTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._remainingSec > 0) {
                this._remainingSec -= 1;
                this._countLabel.set_text(this._formatSeconds(this._remainingSec));
                return GLib.SOURCE_CONTINUE;
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopLocalCountdown() {
        if (this._localTimer) {
            GLib.source_remove(this._localTimer);
            this._localTimer = null;
        }
    }

    _formatSeconds(totalSec) {
        if (totalSec <= 0) return '00:00';
        const hrs = Math.floor(totalSec / 3600);
        const mins = Math.floor((totalSec % 3600) / 60);
        const secs = totalSec % 60;
        const pad = (n) => String(n).padStart(2, '0');
        if (hrs > 0) {
            return `${hrs}:${pad(mins)}:${pad(secs)}`;
        }
        return `${pad(mins)}:${pad(secs)}`;
    }

    _togglePills() {
        if (this._mode === 'ENTERING') {
            this._cancelPills();
        } else {
            this._mode = 'ENTERING';
            this._pillsBox.set_visible(true);
            this._countLabel.set_visible(false);
            this._endButton.set_visible(false);
            this._daysEntry.set_text('');
            this._hoursEntry.set_text('');
            this._minsEntry.set_text('');
            this._hoursEntry.grab_key_focus();
        }
    }

    _cancelPills() {
        this._pillsBox.set_visible(false);
        if (this._proxy) {
            this._proxy.GetStateRemote(([active, rem_sec, rem_str, lid, batt], err) => {
                if (!err) {
                    this._updateState(active, rem_sec, rem_str, lid, batt);
                }
            });
        }
    }

    _commitPillDuration() {
        const d = this._daysEntry.get_text().trim();
        const h = this._hoursEntry.get_text().trim();
        const m = this._minsEntry.get_text().trim();

        let durParts = [];
        if (d && !isNaN(d)) durParts.push(`${d}d`);
        if (h && !isNaN(h)) durParts.push(`${h}h`);
        if (m && !isNaN(m)) durParts.push(`${m}m`);

        const durStr = durParts.length > 0 ? durParts.join(' ') : '1h';
        this._startDuration(durStr);
    }

    _startDuration(durStr) {
        if (!this._proxy) return;

        if (this._mode === 'RUNNING') {
            this._proxy.ExtendSessionRemote(durStr, ([ok, msg], err) => {
                this._cancelPills();
            });
        } else {
            this._proxy.StartSessionRemote(durStr, ([ok, msg], err) => {
                this._cancelPills();
            });
        }
    }

    _endSession() {
        if (this._proxy) {
            this._proxy.EndSessionRemote(() => {
                this._updateState(false, 0, '00:00', 'open', 'AC');
            });
        }
    }

    destroy() {
        this._stopLocalCountdown();
        if (this._sigId && this._proxy) {
            this._proxy.disconnectSignal(this._sigId);
        }
        super.destroy();
    }
});

export default class InsomniaExtension extends Extension {
    enable() {
        this._indicator = new InsomniaIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'right');
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
