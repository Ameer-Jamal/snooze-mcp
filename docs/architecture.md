# Architecture and compatibility

The package separates the scheduler (`core.py`), MCP tools (`server.py`), CLI
(`cli.py`), macOS service installer (`service.py`), and live demo. The MCP connection
and worker are independent processes sharing SQLite. Set the same `SNOOZE_STATE`
or `--state` directory for both.

SQLite transactions save terminal job changes and their events atomically. An
exclusive `flock` prevents duplicate workers. The database uses `0600` permissions;
new state directories use `0700`. Jobs run serially in batches of at most 100.
A slow probe can delay other jobs; this is not a real-time scheduler. Idle ticks
run approximately once per second.

## Checks

`active` jobs become `completed`, `failed`, `expired`, or `cancelled`.

A timer completes when due. A file check completes when its path is a regular file;
an existing file completes immediately. A command interprets exit `0` as complete,
`1` as pending, and other codes as errors. Three consecutive errors fail the job.
Pending results reset the error counter. Timeouts, missing executables, and excess
output count as errors. A check running beyond expiry produces an expired event.

Pending intervals grow by powers of two from the base interval to the configured
maximum. The default maximum equals the base, giving fixed polling. First check:
after `delay_seconds`. Later checks: relative to the prior check's completion.
Missed intervals are not replayed. Default expiry: seven days. Timing values are
bounded to one year; probe timeouts are capped at 300 seconds.

Cancellation rechecks a job's state before execution and prevents a terminal event
after cancellation. It does not interrupt an already running probe. A crashed probe
may run again after restart, so probes must be repeatable.

## Delivery

No `thread_id` means inbox-only results. With an exact accessible local Codex chat
UUID, the adapter runs `codex queue --thread UUID --message SAVED_CONTINUATION_AND_RESULT`.
`SNOOZE_CODEX` can select an absolute executable; otherwise the worker uses PATH.
The local app-server must be available. Codex controls the chat's model and permissions.

| Delivery | Meaning |
| --- | --- |
| `inbox` | No wake requested |
| `pending` | Awaiting the single attempt |
| `sending` | Attempt claimed and in progress |
| `queued` | Codex returned success; agent execution is not confirmed |
| `failed` | Executable/start failure or nonzero CLI exit |
| `unknown` | Timeout/output failure or restart during an attempt |

There is no automatic delivery retry. A crash after acceptance could otherwise
duplicate AI work. Inspect the chat before manually requeuing. Cancellation cannot
retract terminal events or queued messages.

## Compatibility

| Environment | Support |
| --- | --- |
| macOS, Python 3.11+ | Worker, MCP, CLI, user LaunchAgent |
| Linux, Python 3.11+ | Worker, MCP, CLI; supply your own service manager |
| Native Windows | Unsupported; POSIX process groups and locks are required |
| Local Codex with `queue` | Optional automatic chat wake |
| Other stdio MCP clients | Scheduling and inbox access; no automatic wake adapter |
| Cloud-only Codex chats | Unsupported by the local queue adapter |

Keep the computer awake and logged in for the macOS service. Overdue jobs run
after waking. Snooze does not wake the computer or keep an external build alive.
Polling makes no model calls; delivery uses the selected chat's normal allowance.
