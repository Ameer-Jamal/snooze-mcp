"""Command-line interface."""

import argparse
import json
from pathlib import Path

from . import __version__
from .core import DEFAULT_STATE, Scheduler
from .server import serve


def main():
    parser = argparse.ArgumentParser(
        description="Durable local scheduling without idle model calls."
    )
    parser.add_argument("--version", action="version", version=f"snooze-mcp {__version__}")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("serve")
    worker = subs.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    for name in ("jobs", "events"):
        listing = subs.add_parser(name)
        listing.add_argument("--limit", type=int, default=50)
        listing.add_argument("--offset", type=int, default=0)
    get = subs.add_parser("get")
    get.add_argument("job_id")
    subs.add_parser("health")
    add = subs.add_parser("add")
    add.add_argument("json", help="JSON arguments for schedule")
    cancel = subs.add_parser("cancel")
    cancel.add_argument("job_id")
    args = parser.parse_args()
    try:
        scheduler = Scheduler(args.state)
        if args.action == "serve":
            serve(scheduler)
        elif args.action == "worker":
            scheduler.worker(args.once)
        else:
            if args.action == "add":
                arguments = json.loads(args.json)
                if not isinstance(arguments, dict):
                    raise ValueError("Schedule JSON must be an object")
                result = scheduler.schedule(**arguments)
            elif args.action in ("cancel", "get"):
                result = getattr(scheduler, args.action)(args.job_id)
            elif args.action in ("jobs", "events"):
                result = getattr(scheduler, args.action)(args.limit, args.offset)
            else:
                result = scheduler.health()
            print(json.dumps(result, indent=2))
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"snooze-mcp: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130)


if __name__ == "__main__":
    main()
