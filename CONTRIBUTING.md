# Contributing

Open an issue for bugs or larger proposals. Keep changes focused, document
user-facing behavior, and add regression tests for scheduling or delivery fixes.

## Local setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m coverage run -m unittest discover -s tests -v
.venv/bin/python -m coverage report
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Run tests with isolated state. Do not invoke real models or queue messages to
another person's chat in tests. Tests mock delivery; the live demo requires an
explicit `--wake-current-chat` flag for real AI usage.

## Design constraints

- Waiting never calls a model. Worker and MCP connection are separate processes.
- Terminal events are durable before delivery. Never automatically retry an
  uncertain queue attempt without an explicit idempotency design.
- Probe arguments are passed without a shell, with bounded output and runtime.
- Native Windows is outside current support; preserve macOS and Linux behavior.
- Keep docs clear about queue acceptance versus actual agent completion.

## Release process

1. Update `pyproject.toml`, `src/snooze_mcp/__init__.py`, and `CHANGELOG.md`.
2. Update versioned install examples and run checks plus clean wheel installation.
3. Push and require the CI workflow to pass on the exact release commit.
4. Build wheel/source distributions, run `twine check`, and generate SHA-256 sums.
5. Tag the reviewed commit and attach the distributions and checksums to a GitHub
   release. Mark early versions as prereleases. No registry publishing is implicit.

Keep state databases, credentials, local chat IDs, machine paths, and test logs out
of commits and release artifacts. Report security issues privately.
