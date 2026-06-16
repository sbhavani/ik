# ik — Product Requirements Document

**Status:** Draft v0.1
**Owner:** Santosh Bhavani
**Last updated:** 2026-06-15
**Code version:** 0.1.0 (Alpha)

---

## 1. Summary

`ik` is a command-line tool for [Infomaniak Cloud Services](https://www.infomaniak.com/), designed in the spirit of the AWS CLI: a single binary that exposes the full surface of Infomaniak's product APIs through a consistent, scriptable, and composable interface.

The first supported service is **kDrive** (Infomaniak's cloud storage product). The long-term goal is to make `ik` the canonical way to drive every Infomaniak service — hosting, mail, domains, kSuite — from a terminal, in scripts, and in CI.

The tool is distributed as a single Python package (`pip install ik`) and targets Python 3.10+.

---

## 2. Problem

Infomaniak's product surface is broad (storage, mail, hosting, domains, web services) but the official access story is dominated by a web console. Power users and developers who want to:

- Script routine operations (nightly backups, log rotation, bulk file management)
- Integrate Infomaniak services into CI/CD or automation pipelines
- Manage large kDrives without clicking through a web UI
- Treat cloud storage as a primitive (the way `aws s3` lets you treat S3)

…have no good option today. The public REST API exists but requires hand-rolled HTTP plumbing, JSON parsing, and pagination handling on every call. There is no official SDK, and no community CLI in wide use.

`ik` fills that gap with a tool that feels familiar to anyone who has used `aws`, `gcloud`, `gh`, or `doctl`.

---

## 3. Goals

**G1. Drive kDrive from the terminal.** Cover the everyday file-management operations (browse, search, upload, download, organize, delete) with a CLI experience that is faster and more discoverable than the web console.

**G2. Be scriptable and composable.** Every command must work in non-interactive contexts. Output must be machine-parseable on request. Exit codes must be reliable.

**G3. Feel like `aws`.** New users who have used `aws` or `gcloud` should be productive within minutes: same flag conventions (`--drive`, `--output json`), same subcommand structure (`ik <service> <action> <resource>`), same config-file model (`~/.config/ik/config.json`).

**G4. Stay thin and honest.** `ik` is a thin, well-typed wrapper over the Infomaniak REST API. It does not invent abstractions the API does not provide, and it does not silently retry or coalesce operations.

**G5. Expand across Infomaniak services.** The architecture, client, and CLI framework should be designed so adding a new service (mail, hosting, etc.) is a small, additive change.

---

## 4. Non-Goals

- **Not a web client.** `ik` is CLI-first. We will not build a TUI or web frontend in this package.
- **Not a sync engine.** No `ik drive sync` that watches the filesystem in v0.x. Out of scope until the core command surface is stable.
- **Not a replacement for the web admin console.** Settings, billing, account management stay in the web UI for now.
- **Not a generic multi-cloud tool.** Infomaniak only. We will not wrap AWS, GCP, or other providers.
- **Not a daemon or background service.** Each invocation is a single process that exits when work is done.

---

## 5. Target Users

| Persona               | What they do with `ik`                                                       |
| --------------------- | ---------------------------------------------------------------------------- |
| **DevOps engineer**   | Cron a nightly archive of a kDrive to local storage; integrate with backups |
| **Site-reliability engineer** | Drive bulk file operations and incident triage without leaving the terminal |
| **Data engineer**     | Pull log files or dataset snapshots from kDrive into a pipeline              |
| **Power user / hobbyist** | Manage personal kDrive, free up space, find old files                    |
| **Integrator / agency** | Script tenant onboarding and asset handoff for clients                   |

---

## 6. User Stories (v0.x)

These are the jobs the CLI is being built to do. Stories marked **[shipped]** are implemented in 0.1.0; the rest are queued.

### Identity & configuration
- As a new user, I can run `ik configure`, paste my Infomaniak API token, and have it stored in `~/.config/ik/config.json`. **[shipped]**
- As a CI system, I can set `INFOMANIAK_TOKEN` in the environment and skip `configure` entirely. **[shipped]**
- As a user, I can run `ik whoami` to confirm the account and token I am authenticated as. **[shipped]**

### kDrive navigation
- As a user, I can run `ik drives` to see all kDrives on my account, with used/total size. **[shipped]**
- As a user, I can run `ik drive ls` (or `ik drive ls Documents/Photos`) to list files in any directory. **[shipped]**
- As a user, I can run `ik drive tree` to see a directory tree of a kDrive. **[shipped]**
- As a user, I can run `ik drive search "invoice"` to find files by name across a drive. **[shipped]**

### kDrive mutations
- As a user, I can run `ik drive mkdir Projects/new` to create a nested directory. **[shipped]**
- As a user, I can run `ik drive upload report.pdf --dir 5` to upload a file. **[shipped]**
- As a user, I can run `ik drive download 123 --local ./` to download a file by ID. **[shipped]**
- As a user, I can run `ik drive rm 123` to move a file to trash. **[shipped]**
- As a user, I can run `ik drive info 123` to get JSON metadata for a file. **[shipped]**

### Future
- As a user, I can run `ik drive mv src dst` to move/rename a file. **[planned]**
- As a user, I can run `ik drive cp src dst` to copy a file. **[planned]**
- As a user, I can run `ik drive share` to manage public share links. **[planned]**
- As a user, I can run `ik drive restore 123` to restore from trash. **[planned]**
- As a user, I can pipe `ik drive ls --output json` into `jq`. **[planned]**

---

## 7. Functional Requirements

### 7.1 CLI surface (v0.1)

| Command                          | Description                                  | Status      |
| -------------------------------- | -------------------------------------------- | ----------- |
| `ik configure`                   | Interactive setup of credentials             | Shipped     |
| `ik whoami`                      | Show current account info                    | Shipped     |
| `ik drives`                      | List kDrives on the account                  | Shipped     |
| `ik drive ls [path]`             | List directory contents                      | Shipped     |
| `ik drive tree [path]`           | Print directory tree                         | Shipped     |
| `ik drive mkdir <path>`          | Create a directory (with parent creation)    | Shipped     |
| `ik drive upload <local> [--dir]`| Upload a file                                | Shipped     |
| `ik drive download <id> [--local]` | Download a file                            | Shipped     |
| `ik drive search <query>`        | Search files by name                         | Shipped     |
| `ik drive rm <id-or-path>`       | Move file to trash                           | Shipped     |
| `ik drive info <id-or-path>`     | JSON metadata for a file                     | Shipped     |

### 7.2 Global flags

- `--token <token>` — override the stored token for one invocation
- `--profile <name>` — use a named configuration profile (see §7.3)
- `--output json|text` — machine-parseable output

### 7.3 Configuration

- Config file: `~/.config/ik/config.json`
- Schema (v0.3):
    ```json
    {
      "default": "work",
      "profiles": {
        "work":     {"token": "...", "account_id": 12345},
        "personal": {"token": "...", "account_id": 67890}
      }
    }
    ```
- Environment overrides: `INFOMANIAK_TOKEN`, `INFOMANIAK_ACCOUNT_ID`
- Resolution order for token: `--token` flag → `INFOMANIAK_TOKEN` env → profile's `token` (selected by `--profile` or `default`) → error.
- Resolution order for account_id: `INFOMANIAK_ACCOUNT_ID` env → profile's `account_id` (same profile selection as above) → None (auto-detected by client).
- v0.1 flat files (`{"token": "...", "account_id": 12345}`) are read transparently as if the user had a single profile named "default".
- Commands:
    - `ik configure` — interactive; writes to the default profile.
    - `ik configure --profile <name>` — interactive; writes to `<name>`, creating the profile and setting it as default if it's the first.
    - `ik configure --list` — list profiles and mark the default.
- Profile names: must match `[a-zA-Z0-9._-]{1,64}`.

### 7.4 Error handling

- API errors are surfaced as `KDriveError` with the Infomaniak error code and human-readable description.
- HTTP non-2xx responses are treated as errors; raw text is included for debugging.
- Network errors propagate from `requests` and exit non-zero.
- Exit code 0 on success, 1 on user error, 2 on API error, 3 on network error.

---

## 8. Non-Functional Requirements

**NFR-1. Single dependency.** Runtime depends only on `requests`. No transitive surprises.

**NFR-2. Startup time.** Cold start under 200ms on a modern laptop. No plugin loading, no auto-update, no telemetry.

**NFR-3. Testability.** All API client methods are unit-testable with a mocked `requests.Session`. The CLI is structured so commands can be invoked with an injected client.

**NFR-4. Type hygiene.** Python 3.10+ syntax (`X | None`, generics in `collections.abc`). `from __future__ import annotations` is used.

**NFR-5. Portability.** Must work on macOS, Linux, and Windows (anywhere Python 3.10+ runs).

**NFR-6. Logging.** Default is quiet. A `--verbose` flag (planned) raises verbosity to include request/response details for debugging.

**NFR-7. No telemetry.** `ik` does not phone home, does not check for updates, and does not collect usage data.

**NFR-8. License.** MIT.

---

## 9. Architecture

```
ik/
├── pyproject.toml
├── README.md
├── src/ik/
│   ├── __init__.py        # KDriveClient, Drive, File, KDriveError
│   ├── cli.py             # top-level argparse wiring, configure, whoami, drives
│   └── driver/__init__.py # `ik drive ...` subcommands
└── tests/
```

**Layering:**
1. **API client** (`src/ik/__init__.py`) — pure HTTP wrapper over the Infomaniak REST API. Returns dataclasses (`Drive`, `File`). Knows nothing about CLI.
2. **Service commands** (`src/ik/driver/__init__.py`, future `mail/`, `hosting/`) — one module per Infomaniak service. Each exposes a `add_<service>_commands(parser)` function that wires subcommands and dispatches to a `KDriveClient` method.
3. **CLI shell** (`src/ik/cli.py`) — `argparse` setup, config resolution, top-level commands (`configure`, `whoami`, `drives`), and dispatch.

This layering means adding a new service (e.g. mail) is a new module under `src/ik/mail/` plus a single line in `cli.py`.

**API base:** `https://api.infomaniak.com`. API versions are encoded in the path (`/1/accounts`, `/2/drive/...`, `/3/drive/.../files/...`) and pinned per method.

**Pagination:** the client follows `has_more`/`cursor` cursors transparently and exposes an iterator (`list_files`, `search`) so callers never see pagination.

---

## 10. Roadmap

### v0.1 — Alpha (current)
- kDrive read/write surface (shipped)
- Interactive configure
- Python 3.10+, single dependency
- MIT license

### v0.2 — Usability
- `ik drive mv`, `ik drive cp`
- `ik drive restore <id>` (restore from trash)
- `ik drive share` (create/list/remove public links)
- `--output json|text` global flag for every command
- `--quiet`, `--yes` flags for scripting
- Progress bars for upload/download of large files
- Resumable uploads (Infomaniak supports chunked upload; wire it up)

### v0.3 — Operations
- `ik drive sync local remote` — one-way mirror (not bidirectional)
- Trash management: `ik drive trash ls|empty|restore`
- Drive-level operations: usage reports, lock/unlock
- Configuration profiles (`ik configure --profile work`) **(shipped in 0.3.0)**

### v0.4 — Beyond kDrive
- Mail service (`ik mail ...`) — list mailboxes, read messages
- Hosting service (`ik hosting ...`) — manage web hosting
- VPS service (`ik vps ...`) — manage Public Cloud / VPS instances **(shipped in 0.4.0, thin slice: `ls`, `info`)**
- Domains service (`ik domain ...`)
- This is the moment the package earns its "Infomaniak CLI" name rather than "kDrive CLI"

### v1.0 — Stable
- API surface frozen
- Documentation site (mkdocs)
- Tab completion for bash, zsh, fish
- Wheels for PyPI; Homebrew tap; Linux package

---

## 11. Success Metrics

We do not have telemetry, so success is measured by proxy signals:

- **Adoption:** PyPI download count, GitHub stars, Homebrew installs.
- **Issue quality:** bug reports are specific and reproducible; feature requests cluster around the roadmap.
- **Contribution:** external PRs land for new services and bug fixes.
- **API coverage:** the percentage of public Infomaniak endpoints we have wrapped (tracked in §10 of the docs as a checklist).

The v1.0 bar is: a user can do everything they would do in the kDrive web console, from the terminal, without leaving their shell.

---

## 12. Open Questions

- **Auth refresh.** The Infomaniak API uses static bearer tokens today. If/when OAuth or short-lived tokens arrive, the config schema in §7.3 will need to change.
- **Multi-account UX.** `INFOMANIAK_ACCOUNT_ID` lets you pick an account, but a clean `--profile` story (§10 v0.3) is the right answer. Until then, the env var is the workaround. *(resolved — see §7.3)*
- **Sync semantics.** Bidirectional sync (`ik drive sync`) has a long history of subtle bugs (see Dropbox, Syncthing). v0.3 scopes to one-way mirror to keep the surface honest. Bidirectional is explicitly out of scope.
- **Output format stability.** When `--output json` lands, the schema becomes a public contract. We will version it (`--output json-v2`) rather than break it silently.
- **Service priority for v0.4.** Mail, hosting, and domains are all candidates. The order will be set by user demand — feature requests are the signal.

---

## 13. Risks

| Risk                                                         | Mitigation                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------ |
| Infomaniak API changes break the client                      | Pin API versions in path; integration tests against real endpoint  |
| Token leakage via shell history or process listings          | Document that `configure` uses a stdin prompt; warn on `--token`   |
| Upload of large files exceeds available memory              | Wire chunked upload (v0.2) and stream in chunks, not bytes-in-RAM  |
| Confusing UX when an account has many drives                 | `--drive` flag everywhere; future: default-drive in config         |
| Scope creep into non-kDrive services before kDrive is solid  | v0.x commits to kDrive-first; v0.4 adds services                   |
