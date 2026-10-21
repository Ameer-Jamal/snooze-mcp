"""LaunchAgent generation without altering the real user's services."""

import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from snooze_mcp import service


class ServiceTests(unittest.TestCase):
    def test_installer_writes_installed_module_and_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            plist = Path(directory) / "LaunchAgents" / "test.plist"
            with (
                patch.multiple(service, DEFAULT_STATE=state, PLIST=plist),
                patch.object(service.sys, "platform", "darwin"),
                patch.object(service.sys, "argv", ["snooze-service", "install"]),
                patch.object(
                    service.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
                ),
            ):
                service.main()
            config = plistlib.loads(plist.read_bytes())
            self.assertEqual(config["ProgramArguments"][-3:], ["-m", "snooze_mcp", "worker"])
            self.assertEqual(config["EnvironmentVariables"]["SNOOZE_STATE"], str(state.resolve()))
            self.assertTrue(state.is_dir())

    def test_failed_install_does_not_leave_a_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            plist = Path(directory) / "test.plist"
            with (
                patch.multiple(service, DEFAULT_STATE=Path(directory) / "state", PLIST=plist),
                patch.object(service.sys, "platform", "darwin"),
                patch.object(service.sys, "argv", ["snooze-service", "install"]),
                patch.object(
                    service.subprocess, "run", return_value=subprocess.CompletedProcess([], 5)
                ),
                self.assertRaises(SystemExit),
            ):
                service.main()
            self.assertFalse(plist.exists())

    def test_does_not_overwrite_existing_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            plist = Path(directory) / "test.plist"
            plist.write_text("existing")
            with (
                patch.object(service, "PLIST", plist),
                patch.object(service.sys, "platform", "darwin"),
                patch.object(service.sys, "argv", ["snooze-service", "install"]),
                self.assertRaises(SystemExit),
            ):
                service.main()
            self.assertEqual(plist.read_text(), "existing")
