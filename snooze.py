"""Compatibility entry point; prefer the installed snooze-mcp command."""

from snooze_mcp.cli import main
from snooze_mcp.core import DEFAULT_STATE, Scheduler, run_command  # noqa: F401

if __name__ == "__main__":
    main()
