# Tools and CLI

Stored timestamps are Unix seconds. Use absolute paths where specified.

| MCP tool | Purpose |
| --- | --- |
| `schedule_check` | Save one timer, file, or command check |
| `list_jobs` | Paginated summaries, active first |
| `get_job` | Full specification, continuation, and status by `job_id` |
| `cancel_job` | Cancel an active check by `job_id` |
| `read_events` | Paginated events and delivery results, newest first |
| `retry_delivery` | Re-attempt a `failed` or `unknown` delivery by integer `event_id` |
| `scheduler_health` | Inspect worker lock and heartbeat |

Listings accept `limit` (1–100, default 50) and `offset` (nonnegative, default 0).

## schedule_check

| Parameter | Default | Meaning |
| --- | --- | --- |
| `title` | Required | Nonblank description, up to 256 characters |
| `kind` | `timer` | `timer`, `file`, or `command` |
| `delay_seconds` | `600` | Wait before first check; zero allowed |
| `interval_seconds` | `600` | Base polling interval; minimum one second |
| `max_interval_seconds` | Base interval | Exponential backoff ceiling |
| `path` | None | Absolute file path for `file` |
| `argv` | None | Argument array with an absolute executable for `command` |
| `cwd` | Server directory | Existing directory; explicitly required for commands |
| `timeout_seconds` | `30` | Command timeout, 1–300 seconds |
| `expires_in_seconds` | `604800` | Wait deadline; must exceed first delay |
| `thread_id` | None | Exact local Codex chat UUID; omit for inbox-only |
| `instruction` | `Report the result.` | Continuation, up to 8192 characters |

Timing values other than probe timeouts cannot exceed 31,536,000 seconds. Command
arrays allow at most 128 arguments and 65,536 total characters. No implicit shell
is used. Schedule status probes, not commands that repeat the actual work.

If no worker is running, the returned job includes a `warning` field; the check
will not run until a worker starts.

## retry_delivery

Explicit, single attempt, only for events whose `delivery` is `failed` or `unknown`
and whose job has a `thread_id`. Other states are refused. An `unknown` event may
already have woken the agent, so retrying can **run it twice**; inspect the chat
first. Nothing retries automatically.

## CLI

```sh
snooze-mcp --version
snooze-mcp serve
snooze-mcp worker
snooze-mcp worker --once
snooze-mcp add '{"title":"Check later","delay_seconds":600}'
snooze-mcp jobs --limit 20 --offset 0
snooze-mcp get JOB_UUID
snooze-mcp events --limit 20 --offset 0
snooze-mcp cancel JOB_UUID
snooze-mcp health
snooze-mcp retry-delivery EVENT_ID   # failed/unknown only
snooze-mcp --state /absolute/path/to/state worker
```

`--state` precedes the subcommand. CLI results are JSON; invalid input exits with
code 2. Standard output from `serve` is reserved for MCP. `worker --once` processes
due checks and pending deliveries before exiting.

```sh
snooze-service install       # macOS user LaunchAgent
snooze-service status
snooze-service uninstall     # retains saved jobs
snooze-demo                  # real MCP + worker, no AI calls
snooze-demo --wake-current-chat  # opts into one Codex wake
```

## Environment

| Variable | Meaning |
| --- | --- |
| `SNOOZE_STATE` | Alternate durable state directory |
| `SNOOZE_CODEX` | Codex executable override; use an absolute path |
| `SNOOZE_DELIVERY_COMMAND` | Delivery argv template replacing `codex queue`; see below |
| `CODEX_THREAD_ID` | Calling chat UUID used by the wake demo |

The macOS installer captures PATH, state path, `SNOOZE_CODEX`, and
`SNOOZE_DELIVERY_COMMAND`. Reinstall the worker if those change.

### Custom delivery

When `SNOOZE_DELIVERY_COMMAND` is set and nonblank it replaces the Codex adapter,
so other agents can be woken:

```sh
export SNOOZE_DELIVERY_COMMAND='/abs/path/agent-wake --session {thread} --message {message}'
```

The template is split with shell-style quoting (`shlex`) but never run by a shell.
`{thread}` and `{message}` are replaced inside their argument after splitting, in
one pass: the message stays one argument whatever it contains and is never
re-expanded. The executable (first word) cannot contain placeholders. Exit 0 is
`queued`; nonzero, a bad template, or a start failure is `failed`; timeout (30s) or
output over 1 MiB is `unknown`. Each event still gets one automatic attempt.

The worker sleeps until the earliest job is due, between 0.1 and 5 seconds, so jobs
added by other processes are noticed within 5 seconds.
