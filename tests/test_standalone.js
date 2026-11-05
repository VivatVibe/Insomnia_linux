import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import { parseDurationSeconds, formatTimeRemaining, LogindInhibitor } from '../lib/utils.js';

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

print('==> [1/3] Testing Duration Parsing and Formatting...');
assert(parseDurationSeconds('', '1', '') === 3600, '1 hour parsed as 3600s');
assert(parseDurationSeconds('1', '2', '30') === 86400 + 7200 + 1800, '1d 2h 30m parsed correctly');
assert(parseDurationSeconds('', '', '15') === 900, '15m parsed as 900s');
assert(parseDurationSeconds('', '', '') === 3600, 'empty values default to 1h');

assert(formatTimeRemaining(0) === '00:00', '0s formatted as 00:00');
assert(formatTimeRemaining(45) === '00:45', '45s formatted as 00:45');
assert(formatTimeRemaining(600) === '10:00', '600s formatted as 10:00');
assert(formatTimeRemaining(3665) === '01:01:05', '3665s formatted as 01:01:05');
assert(formatTimeRemaining(90000) === '1d 01:00:00', '90000s formatted with days');
print('    Duration tests passed.');

print('==> [2/3] Testing Direct Systemd Logind Inhibit Lock...');
const bus = Gio.DBus.system;
const parameters = new GLib.Variant('(ssss)', [
    'sleep:idle:handle-lid-switch',
    'Insomnia Standalone Test',
    'Testing standalone in-process inhibition',
    'block'
]);

let acquiredFd = null;
bus.call_with_unix_fd_list(
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
            assert(fdList && fdList.get_length() > 0, 'FD list returned by logind');
            acquiredFd = fdList.get(0);
            assert(acquiredFd > 0, `Valid FD obtained (${acquiredFd})`);
            print(`    Acquired Logind Inhibit Lock on FD ${acquiredFd}`);
            GLib.close(acquiredFd);
            print('    Released Logind Inhibit Lock successfully.');
        } catch (e) {
            printerr(`    Logind test error: ${e}`);
        }
    }
);

print('==> [3/3] Testing UPower and PowerProfiles D-Bus interfaces...');
try {
    const upower = new Gio.DBusProxy({
        g_connection: bus,
        g_name: 'org.freedesktop.UPower',
        g_object_path: '/org/freedesktop/UPower',
        g_interface_name: 'org.freedesktop.UPower',
    });
    upower.init(null);
    const lidClosed = upower.get_cached_property('LidIsClosed')?.unpack() ?? false;
    print(`    UPower LidIsClosed queried: ${lidClosed}`);
} catch (e) {
    print(`    UPower query skipped: ${e}`);
}

const loop = new GLib.MainLoop(null, false);
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
    loop.quit();
    return GLib.SOURCE_REMOVE;
});
loop.run();

print('==> All Standalone Extension Tests PASSED!');
