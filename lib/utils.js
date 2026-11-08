import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export function parseDurationSeconds(daysStr, hoursStr, minsStr) {
    const d = parseFloat(daysStr) || 0;
    const h = parseFloat(hoursStr) || 0;
    const m = parseFloat(minsStr) || 0;
    let total = (d * 86400) + (h * 3600) + (m * 60);
    if (total <= 0) total = 3600;
    return total;
}

export function formatTimeRemaining(seconds) {
    if (seconds <= 0) return '00:00';
    const total = Math.floor(seconds);
    const d = Math.floor(total / 86400);
    const h = Math.floor((total % 86400) / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n) => String(n).padStart(2, '0');

    if (d > 0) {
        return `${d}d ${pad(h)}:${pad(m)}:${pad(s)}`;
    }
    if (h > 0) {
        return `${pad(h)}:${pad(m)}:${pad(s)}`;
    }
    return `${pad(m)}:${pad(s)}`;
}

export function shouldCutoffSession(params = {}) {
    if (!params || typeof params !== 'object') {
        return false;
    }

    const { cutoffEnabled, onBattery, batteryPercent, endFloor } = params;

    // Strict boolean identity checks
    if (cutoffEnabled !== true || onBattery !== true) {
        return false;
    }

    // Strict finite positive threshold check
    if (typeof endFloor !== 'number' || !Number.isFinite(endFloor) || endFloor <= 0) {
        return false;
    }

    // Strict finite non-negative battery percentage check
    if (typeof batteryPercent !== 'number' || !Number.isFinite(batteryPercent) || batteryPercent < 0) {
        return false;
    }

    return batteryPercent <= endFloor;
}

export class LogindInhibitor {
    constructor() {
        this._inhibitFd = null;
        this._bus = Gio.DBus.system;
        this._acquireGeneration = 0;
    }

    get isActive() {
        return this._inhibitFd !== null;
    }

    acquire(preventLidSleep = true, onAcquired = null) {
        this.release();

        const currentGen = ++this._acquireGeneration;
        const what = preventLidSleep
            ? 'sleep:idle:handle-lid-switch'
            : 'sleep:idle';
        const who = 'Insomnia';
        const why = 'Keep-awake active session';
        const mode = 'block';

        const parameters = new GLib.Variant('(ssss)', [what, who, why, mode]);

        this._bus.call_with_unix_fd_list(
            'org.freedesktop.login1',
            '/org/freedesktop/login1',
            'org.freedesktop.login1.Manager',
            'Inhibit',
            parameters,
            new GLib.VariantType('(h)'),
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            null,
            (conn, res) => {
                try {
                    const [out, fdList] = conn.call_with_unix_fd_list_finish(res);
                    if (fdList && fdList.get_length() > 0) {
                        const fd = fdList.get(0);
                        if (this._acquireGeneration !== currentGen) {
                            try {
                                GLib.close(fd);
                            } catch (e) {}
                            return;
                        }
                        this._inhibitFd = fd;
                        if (onAcquired) onAcquired(this._inhibitFd);
                    }
                } catch (e) {
                    console.error('Insomnia: Failed to acquire logind inhibitor lock', e);
                }
            }
        );
    }

    release() {
        this._acquireGeneration++;
        if (this._inhibitFd !== null) {
            try {
                GLib.close(this._inhibitFd);
            } catch (e) {
                // Ignore if already closed
            }
            this._inhibitFd = null;
        }
    }
}

export class ScreenLockManager {
    constructor() {
        this._screensaverSettings = null;
        this._originalLockEnabled = null;
        this._isActive = false;
        try {
            this._screensaverSettings = new Gio.Settings({ schema_id: 'org.gnome.desktop.screensaver' });
        } catch (e) {
            console.error('Insomnia: Failed to load screensaver settings', e);
        }
    }

    get isActive() {
        return this._isActive;
    }

    apply(disableLock = true) {
        if (!this._screensaverSettings || !disableLock || this._isActive) return;
        this._originalLockEnabled = this._screensaverSettings.get_boolean('lock-enabled');
        if (this._originalLockEnabled) {
            this._screensaverSettings.set_boolean('lock-enabled', false);
            this._isActive = true;
        }
    }

    restore() {
        if (!this._screensaverSettings || !this._isActive) return;
        if (this._originalLockEnabled !== null) {
            this._screensaverSettings.set_boolean('lock-enabled', this._originalLockEnabled);
        }
        this._originalLockEnabled = null;
        this._isActive = false;
    }
}

export class DisplayInhibitor {
    constructor() {
        this._cookie = 0;
        this._bus = Gio.DBus.session;
    }

    get isActive() {
        return this._cookie !== 0;
    }

    acquire(onAcquired = null) {
        if (this._cookie !== 0) return;
        this._bus.call(
            'org.gnome.SessionManager',
            '/org/gnome/SessionManager',
            'org.gnome.SessionManager',
            'Inhibit',
            new GLib.Variant('(susu)', ['Insomnia', 0, 'Keep-awake display lit', 8]),
            new GLib.VariantType('(u)'),
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (conn, res) => {
                try {
                    const out = conn.call_finish(res);
                    this._cookie = out.unpack()[0];
                    if (onAcquired) onAcquired(this._cookie);
                } catch (e) {
                    console.error('Insomnia: Failed to acquire display inhibitor', e);
                }
            }
        );
    }

    release() {
        if (this._cookie !== 0) {
            const cookie = this._cookie;
            this._cookie = 0;
            this._bus.call(
                'org.gnome.SessionManager',
                '/org/gnome/SessionManager',
                'org.gnome.SessionManager',
                'Uninhibit',
                new GLib.Variant('(u)', [cookie]),
                null,
                Gio.DBusCallFlags.NONE,
                -1,
                null,
                null
            );
        }
    }
}
