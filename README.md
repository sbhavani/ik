# ik

> AWS CLI-style command-line tool for [Infomaniak Cloud Services](https://www.infomaniak.com/).
> Drive kDrive, VPS Cloud, Mail (kSuite), and more — from your terminal, in scripts, in CI.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-orange.svg)](https://github.com/sbhavani/ik/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/sbhavani/ik/ci.yml?branch=master&label=tests)](https://github.com/sbhavani/ik/actions/workflows/ci.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Single dependency](https://img.shields.io/badge/runtime%20deps-1-blueviolet.svg)](https://github.com/sbhavani/ik/blob/master/pyproject.toml)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()

**`ik`** is a single binary that exposes Infomaniak's product APIs through a familiar, scriptable, composable interface — the way `aws`, `gcloud`, or `gh` does for their respective clouds.

- **Fast** — cold start under 200 ms. No plugins, no auto-update, no telemetry.
- **Scriptable** — every command works non-interactively. Machine-parseable JSON output. Stable exit codes.
- **AWS-style** — `ik <service> <action> <resource>`, `--output json`, profiles in `~/.config/ik/config.json`. Anyone who has used `aws` is productive in minutes.
- **Thin and honest** — a well-typed wrapper over the Infomaniak REST API. It does not invent abstractions the API does not provide, and it does not silently retry or coalesce operations.
- **Multi-service** — kDrive today (browse, search, upload, download, share, trash, activity), VPS Cloud (list, info), Mail / kSuite (list, info). More services on the roadmap.
- **Single runtime dependency** — only `requests`. No transitive surprises.

---

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
  - [Profiles (multi-account)](#profiles-multi-account)
- [Commands](#commands)
  - [Account](#account)
  - [kDrive](#kdrive)
  - [VPS Cloud](#vps-cloud)
  - [Mail (kSuite)](#mail-ksuite)
- [Output](#output)
- [Design](#design)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Install

`ik` is a single Python package, distributed on [PyPI](https://pypi.org/). It targets Python 3.10+.

**Recommended — [`uv`](https://github.com/astral-sh/uv):**
```bash
uv tool install ik
```

**Try it without installing — [`uvx`](https://github.com/astral-sh/uv):**
```bash
uvx ik --help
```

**With [`pipx`](https://pipx.pypa.io/):**
```bash
pipx install ik
```

**With `pip`:**
```bash
pip install ik
```

Upgrading:
```bash
uv tool upgrade ik
```

### Shell completion

Tab-completion for bash, zsh, and fish ships with the binary. Install it once for your shell:

**bash:**
```bash
# Add to ~/.bashrc for a permanent install:
eval "$(ik completion bash)"
```

**zsh:**
```bash
# Save the completion to a directory in $fpath (e.g. ~/.zsh/completions):
ik completion zsh > "${fpath[1]}/_ik"
# Then add ~/.zsh/completions to $fpath in your .zshrc if it is not already.
```

**fish:**
```bash
ik completion fish | source
```

Profile names are read dynamically from `~/.config/ik/config.json` — `ik --profile <TAB>` completes the names you've configured.

---

## Quick start

```bash
# 1. Save your Infomaniak API token
ik configure

# 2. See what kDrives are on your account
ik drives

# 3. List the contents of a kDrive
ik drive ls

# 4. Search for a file
ik drive search "invoice"

# 5. Pull JSON for piping into jq
ik drives --output json | jq '.[].name'
```

That's it. No daemon, no background process, no telemetry. Every invocation is a single process that exits when work is done.

---

## Configuration

`ik` needs an Infomaniak API token. There are three ways to provide it, in priority order:

1. **Flag** — `ik --token <TOKEN> drives` (one-off override)
2. **Environment** — `export INFOMANIAK_TOKEN=...` (good for CI)
3. **Config file** — `~/.config/ik/config.json`, written by `ik configure`

Get a token at <https://manager.infomaniak.com/v3/profile/api> (it lives under your account profile → API).

### Interactive setup

```bash
ik configure
# paste your token
# optionally enter your account_id (or leave blank to auto-detect)
```

### Non-interactive (CI / scripted)

```bash
export INFOMANIAK_TOKEN="abc123..."
ik drives
```

### Profiles (multi-account)

For multiple Infomaniak accounts, store each in a named profile. The first profile you create becomes the default; switch with `--profile`.

```bash
# Save a token under "work"
ik configure --profile work

# Use it for one command
ik --profile work drives

# Add a second profile
ik configure --profile personal

# See all profiles
ik configure --list
```

```
* work       12345
  personal   67890
```

JSON for tooling:

```bash
ik configure --list --output json
```

```json
{
  "default": "work",
  "profiles": {
    "work":     {"token": "...", "account_id": 12345},
    "personal": {"token": "...", "account_id": 67890}
  }
}
```

Ad-hoc override keeps the profile's `account_id` but uses the new token:

```bash
ik --profile work --token OTHER_TOKEN drive info 123
```

Resolution order for token: **`--token` flag** → `INFOMANIAK_TOKEN` env → profile's `token` → error.
Resolution order for account_id: **`INFOMANIAK_ACCOUNT_ID` env** → profile's `account_id` → `None` (auto-detected).

### Default drive

If your account has multiple kDrives, set a per-profile default so you stop passing `--drive` on every command:

```bash
ik drives                   # find the drive ID you want
ik configure --default-drive 1234
ik drive ls                 # no --drive needed
```

The drive ID is validated against the live API before being saved. Pass `--drive <id>` on any command to override for one call.

---

## Commands

The shape is **`ik <service> <action> <resource>`**, with global flags `--token`, `--profile`, `--output`, `--quiet`, `--yes` available everywhere.

### Account

| Command     | Description           |
| ----------- | --------------------- |
| `configure` | Configure credentials (interactive) |
| `whoami`    | Show current user     |
| `drives`    | List all kDrives      |

### kDrive

```
ik drive <subcommand> [args]
```

| Subcommand    | Description                                          |
| ------------- | ---------------------------------------------------- |
| `ls [path]`   | List directory contents                              |
| `tree [path]` | Print a directory tree                               |
| `mkdir <p>`   | Create a directory (with parent creation)            |
| `upload <f>`  | Upload a file (use `--dir <id>` to target a folder)  |
| `download <id>` | Download a file by ID (use `--local <path>`)        |
| `search <q>`  | Search files by name                                 |
| `info <id>`   | Get JSON metadata for a file                          |
| `mv <src> <dst>` | Move or rename a file or directory                 |
| `cp <src> <dst>` | Copy a file or directory                           |
| `rm <id>`     | Move a file to trash                                 |
| `share`       | Manage public share links (`create`, `get`, `update`, `remove`, `ls`) |
| `trash`       | Manage the trash (`ls`, `empty`, `restore`)          |
| `activity`    | List the drive activity log                          |

Examples:

```bash
ik drive ls Documents/Photos
ik drive upload report.pdf --dir 5
ik drive download 12345 --local ./
ik drive mv 12345 Archive/2024/
ik drive share create 12345 --can-download
ik drive trash ls
ik drive activity --action file_mv --limit 50
```

### VPS Cloud

```
ik vps <subcommand> [args]
```

| Subcommand    | Description                       |
| ------------- | --------------------------------- |
| `ls`          | List VPS Cloud service containers |
| `info <id>`   | Show details for one VPS Cloud service |

Example:

```bash
$ ik vps ls
      ID  NAME              STATUS       PROJECTS     PRICE  CREATED
    1001  My VPS Cloud      active              3     12.00  2024-01-15
    1002  Staging           maintenance         1      5.00  2024-03-02
    1003  Frozen            locked               0         -  2023-11-20
```

### Mail (kSuite)

```
ik mail <subcommand> [args]
```

| Subcommand    | Description                       |
| ------------- | --------------------------------- |
| `ls`          | List current kSuite service       |
| `info <id>`   | Show details for one kSuite       |

This is a thin read-only slice: it shows the kSuite service container
that sits behind your Infomaniak mail subscription. Mailbox-level and
message-level commands (read mail, attachments, etc.) are follow-up
slices.

Example:

```bash
$ ik mail ls
      ID  PACK                STATUS      FREE  RENEWAL     TRIAL EXPIRES
    1234  kSuite Standard     active      No    enabled     2027-01-15
```

---

## Output

### Text (default)

Human-readable tables. Designed for direct terminal use.

```bash
$ ik drives
      ID  NAME                  USED       TOTAL
    1234  Personal              12.0G       100.0G
    5678  Work                  45.0G       250.0G
    9012  Archive                1.2G        20.0G
```

### JSON

`--output json` produces a stable, document-shaped contract suitable for piping into `jq`. No envelope — bare lists and objects.

```bash
$ ik drives --output json
```

```json
[
  {
    "id": 1234,
    "name": "Personal",
    "size": 107374182400,
    "used_size": 12884901888,
    "is_locked": false,
    "has_operation_in_progress": false,
    "created_at": "2023-06-12T10:24:31"
  }
]
```

Pipe into `jq` for any transformation:

```bash
ik drives --output json | jq '.[] | select(.used_size > 0) | {id, name}'
ik drive activity --output json | jq '[.[] | select(.action == "file_mv")] | length'
```

### Exit codes

| Code | Meaning       |
| ---- | ------------- |
| `0`  | Success       |
| `1`  | User error    |
| `2`  | API error     |
| `3`  | Network error |

---

## Design

`ik` follows the same three-layer split as `aws` or `gh`:

```
src/ik/
├── __init__.py        # KDriveClient — pure HTTP wrapper over the Infomaniak REST API
├── cli.py             # argparse shell — top-level commands, config resolution, dispatch
├── driver/__init__.py # `ik drive ...` subcommands
├── vps/__init__.py    # `ik vps ...` subcommands
└── mail/__init__.py   # `ik mail ...` subcommands
```

- **API client** — no `print`, no `sys.exit`, no `argparse`. Returns dataclasses. Raises `KDriveError` on failure.
- **Service modules** — one per Infomaniak service. Each exposes an `add_<service>_commands(parser)` function and dispatches to the client. No direct HTTP.
- **CLI shell** — `argparse` setup, config resolution, top-level commands (`configure`, `whoami`, `drives`), and dispatch.

Adding a new service is **one new module + one line in `cli.py`**. That's it.

API conventions:

- Base URL: `https://api.infomaniak.com`. API versions are pinned per endpoint (`/1/accounts`, `/3/drive/.../files/...`).
- Pagination is followed transparently — `list_files`, `search`, and friends return iterators.
- Errors surface as `KDriveError` with the Infomaniak error code and human description.
- No silent retries. The caller decides.

---

## Roadmap

- **v0.1 — Alpha** *(shipped)* — kDrive read/write surface, interactive `configure`, Python 3.10+, single dependency.
- **v0.2 — Usability** — `--output json|text` everywhere, `--quiet`/`--yes`, progress bars, resumable uploads.
- **v0.3 — Operations** — **configuration profiles** *(shipped)*, `ik drive sync local remote` (one-way mirror), trash management, usage reports.
- **v0.4 — Beyond kDrive** — **VPS Cloud commands** *(shipped: `ls`, `info`)*, **Mail (kSuite) commands** *(shipped: `ls`, `info`, thin slice)*, Hosting, Domains.
- **v1.0 — Stable** — frozen API, tab completion, docs site, distribution wheels for PyPI / Homebrew / Linux packages.

The full roadmap, including deferred items, is in [`docs/PRD.md`](./docs/PRD.md).

---

## Contributing

Contributions are welcome. The bar is: every change ships with tests, the diff is small, and the design stays thin.

```bash
git clone https://github.com/sbhavani/ik.git
cd ik
uv sync --group dev

uv run pytest         # run the test suite
uv run ruff check .   # lint
uv run ruff format .  # format
```

A new service is the most common contribution:

1. Add a new module under `src/ik/<service>/__init__.py` exposing `add_<service>_commands(parser)`.
2. Wire it in `src/ik/cli.py` with a single line.
3. Add tests under `tests/test_<service>_cmd.py`.
4. Open a PR.

Bug reports and feature requests go to the [issue tracker](https://github.com/sbhavani/ik/issues). Please make them specific and reproducible.

---

## License

[MIT](./LICENSE) — © Santosh Bhavani.

Infomaniak, kDrive, and VPS Cloud are trademarks of [Infomaniak Network SA](https://www.infomaniak.com/). This project is an unofficial, community-built CLI and is not affiliated with or endorsed by Infomaniak.
