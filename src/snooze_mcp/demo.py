"""Exercise the real MCP server and installed worker with a simulated file export."""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def demo(wake):
    thread_id = os.environ.get("CODEX_THREAD_ID") if wake else None
    if wake and not thread_id:
        raise SystemExit("Run inside the intended Codex chat; CODEX_THREAD_ID is missing")
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "snooze_mcp", "serve"])
    with tempfile.TemporaryDirectory(prefix="snooze-demo-") as directory:
        marker = Path(directory) / "export.done"
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                health = await session.call_tool("scheduler_health", {})
                if not json.loads(health.content[0].text)["worker_recently_seen"]:
                    raise SystemExit(
                        "Start the worker first: snooze-service install (macOS) or snooze-mcp worker"
                    )
                result = await session.call_tool(
                    "schedule_check",
                    {
                        "title": "Snooze live file completion demo",
                        "kind": "file",
                        "path": str(marker),
                        "delay_seconds": 0,
                        "interval_seconds": 2,
                        "expires_in_seconds": 60,
                        "thread_id": thread_id,
                        "instruction": "This is a Snooze MCP smoke test. Acknowledge that this chat was woken successfully once. Do not schedule any further work.",
                    },
                )
                if result.isError:
                    raise RuntimeError(result)
                job = json.loads(result.content[0].text)
                print(f"Scheduled {job['id']}; simulated export takes 3 seconds.", flush=True)
                await asyncio.sleep(3)
                marker.write_text("Export complete\n")
                for _ in range(80):
                    result = await session.call_tool("read_events", {})
                    # SDK returns lists as individual text blocks.
                    events = []
                    for content in result.content:
                        if content.type == "text":
                            value = json.loads(content.text)
                            events.extend(value if isinstance(value, list) else [value])
                    match = next((event for event in events if event["job_id"] == job["id"]), None)
                    if match and match["delivery"] not in ("pending", "sending"):
                        print(json.dumps(match, indent=2))
                        if match["status"] != "completed" or (
                            wake and match["delivery"] != "queued"
                        ):
                            raise SystemExit("Demo did not complete/deliver successfully")
                        return
                    await asyncio.sleep(0.5)
                raise SystemExit("Timed out waiting for the worker; inspect snooze.py events")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wake-current-chat",
        action="store_true",
        help="Queue one real Codex wake (uses normal Codex usage)",
    )
    asyncio.run(demo(parser.parse_args().wake_current_chat))


if __name__ == "__main__":
    main()
