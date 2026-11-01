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


def build_plist(python: str, state: Path, env: dict) -> dict:
    """Pure LaunchAgent definition; absolute paths only, nothing is read from or written to disk."""
    passthrough = {k: env[k] for k in ("SNOOZE_CODEX", "SNOOZE_DELIVERY_COMMAND") if k in env}
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "snooze_mcp", "worker"],
        "WorkingDirectory": str(state),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(state / "worker.log"),
        "StandardErrorPath": str(state / "worker-error.log"),
        "EnvironmentVariables": {
            "PATH": env.get("PATH", "/usr/bin:/bin"),
            "SNOOZE_STATE": str(state),
            **passthrough,
        },
    }


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
    config = build_plist(sys.executable, DEFAULT_STATE.resolve(), dict(os.environ))
    PLIST.write_bytes(plistlib.dumps(config))
    result = subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)])
    if result.returncode:
        PLIST.unlink(missing_ok=True)
        raise SystemExit(result.returncode)
    print(f"Installed {PLIST}")


if __name__ == "__main__":
    main()
