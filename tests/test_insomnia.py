from __future__ import annotations

import os
import stat
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from insomnia.backstop import BackstopRunner
from insomnia.config import Config
from insomnia.paths import Paths
from insomnia.power.battery import BatteryMonitor
from insomnia.power.logind_inhibitor import LogindInhibitor
from insomnia.recovery_lock import LockTimeoutError, RecoveryLock
from insomnia.session import Session, format_remaining_time, parse_duration_string
from insomnia.store import Store, format_iso8601, parse_iso8601
from insomnia.system.browser_throttle import BrowserThrottle
from insomnia.system.freezer import ProcessFreezer, ProcessIdentity
from insomnia.system.tmux_nudge import TmuxNudge


class TestInsomnia(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.paths = Paths(base_override=self.base_path)
        self.paths.ensure_directories()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_paths_structure(self) -> None:
        self.assertTrue(self.paths.data_dir.exists())
        self.assertTrue(self.paths.config_dir.exists())
        self.assertTrue(self.paths.state_dir.exists())
        self.assertEqual(self.paths.session_file, self.paths.data_dir / "session.json")
        self.assertEqual(self.paths.lock_file, self.paths.data_dir / "recovery.lock")

    def test_store_permissions_and_atomicity(self) -> None:
        target = self.paths.session_file
        data = {"hello": "world", "num": 42}
        Store.write_json(target, data)

        self.assertTrue(target.exists())
        mode = os.stat(target).st_mode & 0o777
        self.assertEqual(mode, 0o600)

        read_data = Store.read_json(target)
        self.assertEqual(read_data, data)

    def test_recovery_lock_mutual_exclusion(self) -> None:
        with RecoveryLock(self.paths, timeout=1.0):
            # Attempting to acquire a second lock on the same path must fail with LockTimeoutError
            with self.assertRaises(LockTimeoutError):
                with RecoveryLock(self.paths, timeout=0.2, poll_interval=0.05):
                    pass

    def test_session_lifecycle(self) -> None:
        session = Session.create(3600.0)
        self.assertFalse(session.is_expired())
        self.assertGreater(session.remaining(), 3500.0)

        # Extend
        session.extend(1800.0)
        self.assertEqual(len(session.extensions), 1)
        self.assertGreater(session.remaining(), 5000.0)

        # Roundtrip JSON
        data = session.to_dict()
        restored = Session.from_dict(data)
        self.assertEqual(session.ends_at, restored.ends_at)
        self.assertEqual(session.extensions, restored.extensions)

    def test_duration_parsing(self) -> None:
        self.assertEqual(parse_duration_string("30m"), 1800.0)
        self.assertEqual(parse_duration_string("1h"), 3600.0)
        self.assertEqual(parse_duration_string("2h30m"), 9000.0)
        self.assertEqual(parse_duration_string("7200"), 7200.0)
        self.assertEqual(format_remaining_time(3665), "01:01:05")
        self.assertEqual(format_remaining_time(59), "00:59")

    def test_config_defaults(self) -> None:
        cfg = Config()
        self.assertEqual(cfg.low_power_floor, 40)
        self.assertEqual(cfg.end_floor, 10)
        self.assertTrue(cfg.mute_on_lid_close)
        self.assertTrue(cfg.low_power_on_lid_close)

        d = cfg.to_dict()
        cfg2 = Config.from_dict(d)
        self.assertEqual(cfg.low_power_floor, cfg2.low_power_floor)

    def test_logind_inhibitor(self) -> None:
        inhibitor = LogindInhibitor()
        acquired = inhibitor.acquire(reason="Test Insomnia Suite")
        self.assertTrue(acquired)
        self.assertTrue(inhibitor.is_active)
        inhibitor.release()
        self.assertFalse(inhibitor.is_active)

    def test_backstop_reconciliation_flow(self) -> None:
        runner = BackstopRunner(self.paths)

        # 1. Dirty state with expired session
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        past_session = {
            "startedAt": format_iso8601(past - timedelta(hours=2)),
            "endsAt": format_iso8601(past),
            "extensions": [],
        }
        Store.write_json(self.paths.session_file, past_session)
        Store.write_json(
            self.paths.state_file,
            {
                "sleepDisabledByUs": True,
                "lowPowerSetByUs": True,
                "previousPowerProfile": "balanced",
                "savedMuted": True,
                "frozenProcesses": [],
            },
        )

        code = runner.run()
        self.assertEqual(code, 0)

        # Session file should be removed
        self.assertFalse(self.paths.session_file.exists())

        # State should be clean
        cleaned_state = Store.read_json(self.paths.state_file)
        self.assertIsNotNone(cleaned_state)
        self.assertFalse(cleaned_state.get("lowPowerSetByUs"))
        self.assertFalse(cleaned_state.get("savedMuted"))

    def test_browser_throttle_definitions(self) -> None:
        self.assertIn("--disable-backgrounding-occluded-windows", BrowserThrottle.REQUIRED_FLAGS)
        self.assertIn("--disable-renderer-backgrounding", BrowserThrottle.REQUIRED_FLAGS)


if __name__ == "__main__":
    unittest.main()
