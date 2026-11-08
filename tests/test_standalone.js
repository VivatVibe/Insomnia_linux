import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import { parseDurationSeconds, formatTimeRemaining, LogindInhibitor, shouldCutoffSession, ScreenLockManager, DisplayInhibitor } from '../lib/utils.js';

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

print('==> [1/5] Testing Duration Parsing and Formatting...');
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

print('==> [2/5] Testing Battery Floor Cutoff Logic...');
// Test 1: onBattery=true, batteryPercent below endFloor -> cutoff
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 15, cutoffEnabled: true, endFloor: 20 }) === true,
    'Cutoff triggered when on battery and level below threshold');
// Test 2: onBattery=true, batteryPercent at endFloor -> cutoff
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 20, cutoffEnabled: true, endFloor: 20 }) === true,
    'Cutoff triggered when on battery and level exactly at threshold');
// Test 3: onBattery=true, batteryPercent above endFloor -> no cutoff
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 25, cutoffEnabled: true, endFloor: 20 }) === false,
    'No cutoff when battery level is above threshold');
// Test 4: AC power (onBattery=false) -> no cutoff regardless of percentage
assert(shouldCutoffSession({ onBattery: false, batteryPercent: 10, cutoffEnabled: true, endFloor: 20 }) === false,
    'No cutoff when on AC power');
// Test 5: cutoff disabled (cutoffEnabled=false) -> no cutoff
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 5, cutoffEnabled: false, endFloor: 20 }) === false,
    'No cutoff when cutoff feature is disabled');
// Test 6: invalid/zero endFloor -> no cutoff
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 5, cutoffEnabled: true, endFloor: 0 }) === false,
    'No cutoff when endFloor is 0');
// Test 7: strict boolean check (truthy string is rejected)
assert(shouldCutoffSession({ onBattery: true, batteryPercent: 5, cutoffEnabled: "true", endFloor: 20 }) === false,
    'No cutoff when cutoffEnabled is not strict boolean true');
// Test 8: null/undefined params tolerance
assert(shouldCutoffSession(null) === false, 'Safe return false on null parameter');
assert(shouldCutoffSession(undefined) === false, 'Safe return false on undefined parameter');
assert(shouldCutoffSession() === false, 'Safe return false on empty invocation');
print('    Battery Floor Cutoff logic tests passed.');

print('==> [3/5] Testing Direct Systemd Logind Inhibit Lock...');
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

print('==> [4/5] Testing UPower and PowerProfiles D-Bus interfaces...');
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

print('==> [5/5] Testing ScreenLockManager and DisplayInhibitor...');
const screenLockMgr = new ScreenLockManager();
assert(screenLockMgr.isActive === false, 'ScreenLockManager initially inactive');
screenLockMgr.apply(false);
assert(screenLockMgr.isActive === false, 'apply(false) does not activate');

const displayInhibitor = new DisplayInhibitor();
assert(displayInhibitor.isActive === false, 'DisplayInhibitor initially inactive');
displayInhibitor.release();
assert(displayInhibitor.isActive === false, 'release() when inactive is safe');
print('    ScreenLockManager and DisplayInhibitor baseline verified.');

const loop = new GLib.MainLoop(null, false);
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
    loop.quit();
    return GLib.SOURCE_REMOVE;
});
loop.run();

print('==> All Standalone Extension Tests PASSED!');
