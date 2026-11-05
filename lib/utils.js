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

export class LogindInhibitor {
    constructor() {
        this._inhibitFd = null;
        this._bus = Gio.DBus.system;
    }

    get isActive() {
        return this._inhibitFd !== null;
    }

    acquire(preventLidSleep = true, onAcquired = null) {
        if (this._inhibitFd !== null) {
            this.release();
        }

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
                        this._inhibitFd = fdList.get(0);
                        if (onAcquired) onAcquired(this._inhibitFd);
                    }
                } catch (e) {
                    console.error('Insomnia: Failed to acquire logind inhibitor lock', e);
                }
            }
        );
    }

    release() {
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
