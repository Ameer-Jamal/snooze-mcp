# Examples

These are MCP `schedule_check` arguments. Replace paths and UUIDs with your own.
Omit `thread_id` to save results in the inbox without waking AI.

## Completion file every ten minutes

```json
{
  "title": "Wait for export",
  "kind": "file",
  "path": "/absolute/path/to/export.done",
  "delay_seconds": 600,
  "interval_seconds": 600,
  "expires_in_seconds": 86400,
  "thread_id": "REPLACE-WITH-EXACT-CHAT-UUID",
  "instruction": "Read the completed export, validate its record count, and summarize the results. Do not schedule another check."
}
```

Have the producer create a unique marker only after finishing its output. A stale
existing file completes the check immediately. Set `max_interval_seconds: 3600`
to back off between pending checks: 10, 20, 40, then 60 minutes, staying at 60.

## Command probe every hour

```json
{
  "title": "Wait for build 123",
  "kind": "command",
  "argv": ["/absolute/path/to/check-build", "123"],
  "cwd": "/absolute/path/to/project",
  "delay_seconds": 600,
  "interval_seconds": 3600,
  "timeout_seconds": 20,
  "expires_in_seconds": 86400
}
```

The probe returns `0` when complete, `1` while pending, or another code for errors.
It must be safe to repeat. Three consecutive errors fail the check. Do not use a
command that starts the build again.

## Overnight work

A timer can queue a saved task while you are away. Compute the delay until the
next 1 a.m. in your own time zone:

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("America/Phoenix"))
start = now.replace(hour=1, minute=0, second=0, microsecond=0)
if start <= now:
    start += timedelta(days=1)
delay_seconds = start.timestamp() - now.timestamp()
```

Use that delay in a `timer`, with a longer `expires_in_seconds`, the intended chat
UUID, project `cwd`, and a concrete continuation:

> Implement the approved dependency update in the prepared branch. Run the project
> checks, save progress if blocked, and leave a reviewable summary. Do not merge,
> deploy, or schedule recursive follow-ups.

Keep the computer and Codex service available. A delayed worker either runs the
job late or expires it according to its wait deadline.

### Account limits

Overnight scheduling shifts work; it does not create extra allowance. Plan around
the account's **actual reset timestamp**. A 1 a.m. start does not itself guarantee
fresh capacity at 6 a.m. Weekly limits can still apply, and work continuing into
a new window can consume that window. [OpenAI usage guidance](https://learn.chatgpt.com/docs/pricing).

Version 0.1.0 schedules starts only. It does not read account limits, reserve morning
capacity, pause active model turns, enforce a work cutoff, or automatically resume
after a limit reset. `expires_in_seconds` bounds waiting, not AI runtime after delivery.
