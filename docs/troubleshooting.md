# Troubleshooting

## Missing tools

Check `codex mcp get snooze`: the executable must be an installed absolute path,
with `serve` as the argument. Verify `snooze-mcp --version` in that environment,
then reopen the client if needed.

## Jobs never run

Run `snooze-mcp health`. `worker_running` checks the lock;
`worker_recently_seen` also checks its heartbeat. Start the worker if absent.
Worker and MCP process must use the same state directory.

On macOS, inspect `snooze-service status`, `worker.log`, and `worker-error.log` in
the state directory. Keep the computer awake and logged in. On Linux, keep the
worker running under a service manager. Duplicate workers are rejected.

## Completed event, no response

Inspect `snooze-mcp events` and `snooze-mcp get JOB_UUID`:

- `inbox`: no `thread_id` was supplied; no wake requested.
- `queued`: Codex accepted the message; inspect the destination chat and its state.
- `failed`: inspect `delivery_detail`, executable path, CLI support, and UUID.
- `unknown`: acceptance is uncertain; check the chat before retrying manually.

Verify `codex queue --help`. The target must be a locally accessible chat. Use its
exact UUID. The worker captures PATH when installed; set an absolute `SNOOZE_CODEX`
and reinstall the macOS service if Codex moved. Version-manager executables may
need extra environment configuration.

## Command failures

Use an absolute executable and explicit `cwd`. Exit codes: `0` complete, `1`
pending, other values error. Shell syntax is not expanded. A failed external job
should produce an error or use a dedicated adapter, not stay pending indefinitely.
Stored output is bounded to 4 KiB; output above 1 MiB terminates the probe. Default
timeout is 30 seconds.

## State and upgrades

Stop the worker before upgrading the package, then restart it:

```sh
snooze-service uninstall
python -m pip install --upgrade /path/to/snooze_mcp-VERSION-py3-none-any.whl
snooze-service install
snooze-mcp health
```

The default state directory is `~/.local/share/snooze-mcp/`; select another with
`SNOOZE_STATE`. Back it up while both worker and MCP server are stopped for a
consistent copy. Version 0.1.0 preserves the prototype's SQLite tables.

Uninstall retains jobs. Active checks resume if a worker is restarted; cancel them
first if they should not resume. To remove state entirely, stop both processes,
then deliberately delete the state directory. Keep it outside public/shared repos.

## Report a bug

Include OS, Python/package/CLI versions, worker health, redacted check arguments,
and delivery status. Do not upload databases, secrets, or private chat history.
Use [private reporting](../SECURITY.md) for vulnerabilities.
