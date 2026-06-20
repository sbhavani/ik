# CLAUDE.md

Project context and coding conventions for `ik`, an AWS-CLI-style tool for Infomaniak Cloud Services.

The full product scope and roadmap are in `docs/PRD.md` — read it before proposing changes that go beyond kDrive.

## Commits — conventional commit style

All commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body — wrap at 100 chars; explain WHY, not WHAT>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`.

**Scope** is the affected area: `drive`, `cli`, `client`, `config`, `docs`, `tests`. Omit when the change is project-wide.

**Subject rules:**
- Imperative mood ("add", not "added" or "adds")
- Lowercase first letter, no trailing period
- 72 chars or fewer
- No emoji

**Body:** explain *why* the change is needed; the diff shows *what*. Link to the issue or PRD section it relates to when relevant.

**Footer:** `BREAKING CHANGE: <description>` for any change that alters the public CLI surface, config schema, or Python API.

**Examples:**

```
feat(drive): add mv and cp subcommands

Users currently have to fall back to download-then-upload for moves, which
is wasteful and slow. Wire the existing kDrive move/copy endpoints.

Closes #42
```

```
fix(client): follow pagination cursors in list_files

Previous loop emitted the first page and exited. Discovered when a user
with 5000+ files in a directory saw truncated results.
```

## Code style

- Python 3.12+ syntax: `int | None`, `list[str]`, generics in `collections.abc`.
- `from __future__ import annotations` at the top of every module.
- Type hints on every public function and method. `Any` only at the API boundary if unavoidable — comment why.
- Dataclasses for value objects (`Drive`, `File`). Don't introduce Pydantic or attrs without discussion.
- Ruff is the linter and formatter (config in `pyproject.toml`: line length 100, target py310). Run `ruff check` and `ruff format` before committing.
- Import order: `__future__`, stdlib, third-party, local — one blank line between groups.
- Prefer composition over inheritance. Don't subclass `KDriveClient`; pass it in.

## Architecture

Three-layer split, enforced:

1. **API client** (`src/ik/__init__.py`) — HTTP wrapper. Returns dataclasses. No `print`, no `sys.exit`, no `argparse`. Raises `KDriveError` on failure.
2. **Service modules** (`src/ik/<service>/__init__.py`) — one per Infomaniak service. Each exposes `add_<service>_commands(parser)` and dispatches to the client. No direct `requests` calls.
3. **CLI shell** (`src/ik/cli.py`) — `argparse` setup, config resolution, top-level commands, dispatch. No HTTP.

Adding a new service is one new module + one line in `cli.py`. Anything bigger is a smell — flag it.

## Dependencies

- Runtime: `requests` only. Adding a runtime dep is a design decision, not routine — call it out in the PR.
- Dev: `pytest`, `pytest-cov`, `ruff`. Keep the list short.

## Testing

- Unit tests live in `tests/`, one file per module.
- API client methods are unit-tested with a mocked `requests.Session` — no network in CI.
- CLI commands are tested by calling the `cmd_*` function with a constructed `argparse.Namespace` and an injected `KDriveClient`. No subprocess tests.
- Every new command needs a happy-path test and at least one error-path test.

## Don't

- Don't introduce a sync engine, TUI, or telemetry — out of scope per the PRD.
- Don't add `print` to the API client layer. Errors raise; the CLI layer formats.
- Don't silently retry API calls. Surface the error and let the user decide.
- Don't add backwards-compatibility shims for unreleased code. v0.x is allowed to break.
- Don't write multi-paragraph docstrings or comments that restate the code. The diff shows *what*; the commit and PR description explain *why*.
