# Changelog

## 0.1.0 — 2026-10-21

Initial public prerelease.

- Durable timer, file, and command checks through local stdio MCP and CLI.
- Configurable delay, fixed polling or exponential backoff, expiry, and cancellation.
- SQLite events, paginated listings, full job inspection, and worker health.
- Optional one-attempt Codex chat delivery, with explicit failed/unknown states.
- Bounded subprocess output, timeouts, and process-group cleanup.
- macOS user LaunchAgent management; foreground/service-manager operation on Linux.
- Installable wheel, isolated live demo, usage examples, security documentation,
  and automated macOS/Linux checks.

Limitations: native Windows and automatic non-Codex delivery are unsupported.
Quota-aware admission, work cutoffs, and reset-driven pause/resume are not included.
