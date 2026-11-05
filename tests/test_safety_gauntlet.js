import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import { LogindInhibitor } from '../lib/utils.js';

const mode = ARGV[0] || 'all';

function assert(cond, msg) {
    if (!cond) {
        printerr(`[FAIL] ${msg}`);
        GLib.exit(1);
    }
}

if (mode === 'hold') {
    // Helper mode: acquires lock and holds until killed
    const inhibitor = new LogindInhibitor();
    inhibitor.acquire(true, (fd) => {
        print(`ACQUIRED_FD=${fd}`);
    });
    const loop = new GLib.MainLoop(null, false);
    loop.run();
} else if (mode === 'unit') {
    print('Testing LogindInhibitor acquire and release lifecycle...');
    const inhibitor = new LogindInhibitor();
    let gotFd = null;

    inhibitor.acquire(true, (fd) => {
        gotFd = fd;
        print(`Acquired FD: ${fd}`);
    });

    const loop = new GLib.MainLoop(null, false);
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
        assert(gotFd !== null && gotFd > 0, 'FD acquired successfully');
        assert(inhibitor.isActive, 'Inhibitor marks active');

        inhibitor.release();
        assert(!inhibitor.isActive, 'Inhibitor marks inactive after release');
        print('Released FD successfully.');
        loop.quit();
        return GLib.SOURCE_REMOVE;
    });
    loop.run();
    print('Unit safety test passed.');
}
