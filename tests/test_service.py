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


class BuildPlistTests(unittest.TestCase):
    def test_plist_content_is_absolute_and_serializable(self):
        state = Path("/abs/state")
        config = service.build_plist("/abs/python", state, {"PATH": "/a:/b"})
        self.assertEqual(config["Label"], service.LABEL)
        self.assertEqual(config["ProgramArguments"], ["/abs/python", "-m", "snooze_mcp", "worker"])
        self.assertEqual(config["WorkingDirectory"], "/abs/state")
        self.assertEqual(config["StandardOutPath"], "/abs/state/worker.log")
        self.assertEqual(config["StandardErrorPath"], "/abs/state/worker-error.log")
        self.assertTrue(config["RunAtLoad"] and config["KeepAlive"])
        self.assertEqual(
            config["EnvironmentVariables"], {"PATH": "/a:/b", "SNOOZE_STATE": "/abs/state"}
        )
        self.assertEqual(plistlib.loads(plistlib.dumps(config)), config)

    def test_plist_carries_delivery_settings_only_when_set(self):
        env = {"SNOOZE_CODEX": "/c", "SNOOZE_DELIVERY_COMMAND": "/bin/agent {thread} {message}"}
        config = service.build_plist("/p", Path("/s"), {**env, "OTHER": "no"})
        self.assertEqual(
            config["EnvironmentVariables"],
            {"PATH": "/usr/bin:/bin", "SNOOZE_STATE": "/s", **env},
        )

    def test_default_plist_location_is_user_launch_agents(self):
        self.assertEqual(service.PLIST.parent, Path.home() / "Library/LaunchAgents")

    def test_uninstall_unloads_and_removes_without_touching_state(self):
        with tempfile.TemporaryDirectory() as directory:
            plist = Path(directory) / "test.plist"
            plist.write_text("x")
            with (
                patch.object(service, "PLIST", plist),
                patch.object(service.sys, "platform", "darwin"),
                patch.object(service.sys, "argv", ["snooze-service", "uninstall"]),
                patch.object(service.subprocess, "run") as run,
            ):
                service.main()
            self.assertFalse(plist.exists())
            self.assertEqual(run.call_args.args[0][:2], ["launchctl", "bootout"])
