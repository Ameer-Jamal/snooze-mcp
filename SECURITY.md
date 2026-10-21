# Security policy

## Supported version

Security fixes target the latest published 0.1.x release. This is early software;
review probes and continuations before using it with sensitive projects.

## Trust model

Snooze is a local stdio MCP server, not an authenticated remote service. A client
that can call `schedule_check` can schedule command probes as the OS user running
the worker. Snooze does not sandbox executables or provide a multi-user boundary.
Only connect trusted clients, and use repeatable, read-only probes.

Arguments are passed without a shell. This prevents implicit shell expansion, but
it does not make arbitrary executables safe. Do not schedule code copied from
untrusted logs or treat returned output as instructions. Output and runtime limits
bound accidental resource consumption, not all possible effects of a command.

The database stores paths, continuations, probe arguments, and bounded output.
Avoid putting secrets in any of those fields. Database permissions are owner-only;
choose a private state directory. SQLite is not encrypted. A configured Codex wake
sends its continuation and probe result to the selected chat and its provider.

No automatic retry occurs after failed or uncertain delivery. Inspect the chat
before retrying manually to avoid duplicate work. Account limits and sandbox
permissions remain controlled by the client; Snooze does not bypass them.

## Reporting a vulnerability

Use the repository's **Security → Report a vulnerability** option when available:
[private vulnerability reporting](https://github.com/Ameer-Jamal/snooze-mcp/security/advisories/new).
Include affected versions, a minimal reproduction, and expected impact. Do not
include credentials, databases, or private chat content. Do not post an exploit
or secrets in a public issue. If private reporting is unavailable, open a minimal
issue requesting a private contact channel without technical vulnerability details.
