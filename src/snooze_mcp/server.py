"""MCP stdio tools for the durable scheduler."""

from .core import Scheduler


def serve(scheduler: Scheduler):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "snooze",
        instructions=(
            "Use for work blocked on external progress. Save a continuation and stop polling in the AI loop. "
            "Polling uses no AI. With thread_id the worker queues a message on completion/failure/expiry; "
            "without it results are inbox-only. Worker must be running. "
            "Use absolute paths. Command probes must be repeatable status checks: 0=done,1=pending,other=error. "
            "Prefer files or commands over waking AI on a timer. Never schedule recursively from a wake message."
        ),
    )

    @mcp.tool()
    def schedule_check(
        title: str,
        kind: str = "timer",
        delay_seconds: float = 600,
        interval_seconds: float = 600,
        max_interval_seconds: float | None = None,
        path: str | None = None,
        argv: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 30,
        expires_in_seconds: float = 604800,
        thread_id: str | None = None,
        instruction: str = "Report the result.",
    ) -> dict:
        """Persist one check. Thread UUID opts into one Codex wake, which uses model tokens.

        timer: wakes once after delay. file: finishes when absolute path exists.
        command: argv exit 0 done, 1 pending, other error (fails after 3 consecutive errors).
        Pending checks back off from interval up to max_interval; default is fixed interval.
        expires_in_seconds bounds the wait. Choose an interval matching expected runtime.
        """
        return scheduler.schedule(
            title=title,
            kind=kind,
            delay_seconds=delay_seconds,
            interval_seconds=interval_seconds,
            max_interval_seconds=max_interval_seconds,
            path=path,
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            expires_in_seconds=expires_in_seconds,
            thread_id=thread_id,
            instruction=instruction,
        )

    @mcp.tool()
    def list_jobs(limit: int = 50, offset: int = 0) -> list[dict]:
        """Show paginated jobs, active first. Times are Unix seconds; limit 1–100."""
        return scheduler.jobs(limit, offset)

    @mcp.tool()
    def get_job(job_id: str) -> dict:
        """Read a job's saved continuation, check specification, and full status."""
        return scheduler.get(job_id)

    @mcp.tool()
    def cancel_job(job_id: str) -> dict:
        """Cancel an active check. Cannot retract an already queued wake."""
        return scheduler.cancel(job_id)

    @mcp.tool()
    def read_events(limit: int = 50, offset: int = 0) -> list[dict]:
        """Read paginated events, newest first; limit 1–100. Does not acknowledge events."""
        return scheduler.events(limit, offset)

    @mcp.tool()
    def scheduler_health() -> dict:
        """Check worker heartbeat before relying on a scheduled wake."""
        return scheduler.health()

    mcp.run(transport="stdio")
