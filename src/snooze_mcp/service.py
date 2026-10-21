"""Install/remove the macOS user worker; no root privileges required."""

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .core import DEFAULT_STATE

LABEL = "local.snooze-mcp.worker"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
DOMAIN = f"gui/{os.getuid()}"


def main():
    if sys.platform != "darwin":
        raise SystemExit(
            "snooze-service supports macOS only. On Linux, run snooze-mcp worker under your service manager."
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall", "status"])
    args = parser.parse_args()
    if args.action == "status":
        raise SystemExit(subprocess.call(["launchctl", "print", f"{DOMAIN}/{LABEL}"]))
    if args.action == "uninstall":
        subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], check=False)
        PLIST.unlink(missing_ok=True)
        print("Worker removed; saved jobs retained. MCP config is unchanged.")
        return
    if PLIST.exists():
        raise SystemExit(f"Already installed: {PLIST}. Uninstall before reinstalling.")
    DEFAULT_STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "snooze_mcp", "worker"],
        "WorkingDirectory": str(DEFAULT_STATE.resolve()),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(DEFAULT_STATE / "worker.log"),
        "StandardErrorPath": str(DEFAULT_STATE / "worker-error.log"),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "SNOOZE_STATE": str(DEFAULT_STATE.resolve()),
            **(
                {"SNOOZE_CODEX": os.environ["SNOOZE_CODEX"]} if "SNOOZE_CODEX" in os.environ else {}
            ),
        },
    }
    PLIST.write_bytes(plistlib.dumps(config))
    result = subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)])
    if result.returncode:
        PLIST.unlink(missing_ok=True)
        raise SystemExit(result.returncode)
    print(f"Installed {PLIST}")


if __name__ == "__main__":
    main()
