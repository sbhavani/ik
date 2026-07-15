"""ik CLI - Infomaniak CLI tool."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from . import KDriveClient, KDriveError
from .driver import add_drive_commands
from .mail import add_mail_commands
from .vps import add_vps_commands

CONFIG_DIR = os.path.expanduser("~/.config/ik")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


class _NoDefaultProfile(Exception):
    """Raised when no profiles exist in the config at all."""


def _make_globals(suppress: bool) -> argparse.ArgumentParser:
    """Build a parent parser for the global flags.

    When `suppress=False`, the parser is for the top-level — defaults are
    concrete (`output="text"`, `token=None`, `quiet=False`, `yes=False`)
    so the namespace always has the keys.

    When `suppress=True`, the parser is for subcommands — every default
    is `argparse.SUPPRESS` so the subparser's namespace merge doesn't
    clobber a value set by the top-level parser.
    """
    p = argparse.ArgumentParser(add_help=False)
    default: Any = argparse.SUPPRESS if suppress else None
    output_default: Any = argparse.SUPPRESS if suppress else "text"
    bool_default: Any = argparse.SUPPRESS if suppress else False

    p.add_argument("--token", help="API token override", default=default)
    p.add_argument(
        "--profile",
        default=default,
        help="Configuration profile to use (overrides `default` in config)",
    )
    p.add_argument(
        "--output",
        choices=["text", "json"],
        default=output_default,
        help="Output format (default: text)",
    )
    p.add_argument(
        "--quiet", action="store_true", default=bool_default, help="Suppress non-essential output"
    )
    p.add_argument(
        "--yes",
        action="store_true",
        default=bool_default,
        help="Skip confirmation prompts (for scripts)",
    )
    return p


GLOBAL = _make_globals(suppress=False)
GLOBAL_SUB = _make_globals(suppress=True)


# ── Config (v0.3 nested schema) ───────────────────────────────────────


def _read_config() -> dict:
    """Read config; normalize v0.1 flat shape to v0.3 in memory.

    Returns {} if the file is missing. Exits on corrupt JSON.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(
            f"Error: Config file is corrupt ({CONFIG_PATH}): {e}. Fix it or delete it to start fresh."
        )
    return _migrate_v1_to_v3(data)


def _migrate_v1_to_v3(data: dict) -> dict:
    """Convert a v0.1 flat config in memory to a v0.3 nested shape.

    A v0.1 file has top-level 'token'/'account_id' keys. We treat it as
    a single implicit profile named 'default'. No disk write.
    """
    if "profiles" in data:
        return data
    flat = {k: v for k, v in data.items() if k in ("token", "account_id")}
    if not flat:
        return data
    return {"default": "default", "profiles": {"default": flat}}


def _write_config(config: dict, path: str = CONFIG_PATH) -> None:
    """Serialize v0.3 config to disk (indent=2). Creates parent dir.

    Tightens file mode to 0o600 on POSIX so the stored API token is
    only readable by the owning user. Windows is unaffected.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    if os.name == "posix":
        os.chmod(path, 0o600)


def _write_profile(
    config: dict,
    profile: str,
    token: str,
    account_id: int | None,
    *,
    default_drive: int | None = None,
    default_mail: int | None = None,
    set_default_if_first: bool = True,
) -> dict:
    """Return a NEW config dict with `profile` added/updated.

    Pure function. If `set_default_if_first` and config has no
    'default' key after the update, set it to `profile`. The
    'default_drive' / 'default_mail' fields are only written when
    non-None, so profiles that don't set them stay clean.
    """
    new = {k: v for k, v in config.items() if k != "profiles"}
    profiles = dict(config.get("profiles") or {})
    entry: dict = {"token": token, "account_id": account_id}
    if default_drive is not None:
        entry["default_drive"] = default_drive
    if default_mail is not None:
        entry["default_mail"] = default_mail
    profiles[profile] = entry
    new["profiles"] = profiles
    if set_default_if_first and "default" not in new:
        new["default"] = profile
    return new


def _resolve_default_profile(config: dict) -> str:
    """Return the active profile name from config.

    Raises _NoDefaultProfile if no profiles exist. Exits on ambiguous
    config (multiple profiles, no default; or default points to a
    missing profile).
    """
    profiles = config.get("profiles") or {}
    if not profiles:
        raise _NoDefaultProfile

    default = config.get("default")
    if default is None:
        sys.exit(
            "Error: Multiple profiles configured but no default. "
            "Pass --profile <name> or set one with `ik configure`."
        )
    if default not in profiles:
        sys.exit(
            f"Error: Default profile '{default}' not found in config. "
            f"Run `ik configure` to repair, or set 'default' to an existing profile."
        )
    return default


def _validate_profile_name(name: str) -> None:
    if not PROFILE_NAME_RE.match(name):
        sys.exit(f"Error: Invalid profile name '{name}'. Must match [a-zA-Z0-9._-]{{1,64}}.")


def _resolve_token(args: argparse.Namespace, profile: str | None) -> str:
    """Resolve API token from flag, env, or named profile."""
    if args.token:
        return args.token

    token = os.environ.get("INFOMANIAK_TOKEN")
    if token:
        return token

    if profile is not None:
        config = _read_config()
        prof = (config.get("profiles") or {}).get(profile)
        if prof and prof.get("token"):
            return prof["token"]
        existing = sorted((config.get("profiles") or {}).keys())
        if existing:
            sys.exit(
                f"Error: Profile '{profile}' not found. "
                f"Run `ik configure --profile {profile}` to create it, "
                f"or use one of: {', '.join(existing)}."
            )
        sys.exit(
            f"Error: No API token found for profile '{profile}'. "
            f"Set INFOMANIAK_TOKEN env, pass --token, or run `ik configure`."
        )

    sys.exit("Error: No API token found. Set INFOMANIAK_TOKEN env or run `ik configure`")


def _resolve_account_id(profile: str | None) -> int | None:
    """Resolve account ID from env or named profile."""
    account_id = os.environ.get("INFOMANIAK_ACCOUNT_ID")
    if account_id:
        return int(account_id)

    if profile is not None:
        config = _read_config()
        prof = (config.get("profiles") or {}).get(profile)
        if prof and prof.get("account_id") is not None:
            return int(prof["account_id"])

    return None


def _cmd_configure_list(config: dict, output_format: str = "text") -> None:
    """Print profiles with default marker. Honors --output format."""
    if output_format == "json":
        sys.stdout.write(json.dumps(config, indent=2) + "\n")
        return

    profiles = config.get("profiles") or {}
    if not profiles:
        print("(no profiles configured)")
        return

    default = config.get("default")
    missing_default = default is not None and default not in profiles
    name_width = max(len(n) for n in profiles)
    if missing_default:
        name_width = max(name_width, len(default))
    for name in sorted(profiles):
        marker = "*" if name == default else " "
        prof = profiles[name]
        account_id = prof.get("account_id")
        print(f"{marker} {name:<{name_width}}  {account_id if account_id is not None else ''}")
    if missing_default:
        print(f"! {default:<{name_width}}  (missing)")


def cmd_configure(args: argparse.Namespace) -> None:
    """Interactive configuration, or list profiles with --list."""
    if getattr(args, "list", False):
        _cmd_configure_list(_read_config(), output_format=getattr(args, "output", "text"))
        return

    if getattr(args, "default_drive", None) is not None:
        _cmd_configure_set_default_drive(args)
        return

    if getattr(args, "default_mail", None) is not None:
        _cmd_configure_set_default_mail(args)
        return

    profile_name: str
    explicit = getattr(args, "profile", None)
    if explicit:
        _validate_profile_name(explicit)
        profile_name = explicit
    else:
        config = _read_config()
        existing_default = config.get("default")
        if existing_default and (config.get("profiles") or {}).get(existing_default):
            profile_name = existing_default
        else:
            profile_name = "default"

    print("ik CLI Configuration")
    print(f"Profile: {profile_name}\n")

    token = input("Enter your Infomaniak API token: ").strip()
    if not token:
        sys.exit("Error: Token required")

    config = _read_config()
    config = _write_profile(config, profile_name, token, None)
    _write_config(config, CONFIG_PATH)
    print(f"Token saved to {CONFIG_PATH}\n")

    try:
        client = KDriveClient(token)
        account_id = client.account_id
        print(f"Authenticated successfully. Account ID: {account_id}")
        config = _read_config()
        config = _write_profile(config, profile_name, token, account_id)
        _write_config(config, CONFIG_PATH)
    except KDriveError as e:
        sys.exit(f"Error: {e}")


def _cmd_configure_set_default_drive(args: argparse.Namespace) -> None:
    """Set default_drive on the active profile after validating the drive exists."""
    explicit = getattr(args, "profile", None)
    if explicit:
        _validate_profile_name(explicit)
        config = _read_config()
        if explicit not in (config.get("profiles") or {}):
            sys.exit(
                f"Error: Profile '{explicit}' not found. "
                f"Run `ik configure --profile {explicit}` to create it first."
            )
        profile = explicit
    else:
        config = _read_config()
        try:
            profile = _resolve_default_profile(config)
        except _NoDefaultProfile:
            sys.exit(
                "Error: No configured profile. Run `ik configure` first, or pass --profile <name>."
            )

    drive_id: int = args.default_drive
    entry = config["profiles"][profile]
    token = entry.get("token")
    if not token:
        sys.exit(
            f"Error: Profile '{profile}' has no token. Run `ik configure --profile {profile}` first."
        )

    client = KDriveClient(token)
    try:
        drives = client.list_drives()
    except KDriveError as e:
        sys.exit(f"Error: {e}")
    if not any(d.id == drive_id for d in drives):
        names = ", ".join(f"{d.id} ({d.name})" for d in drives) or "(none)"
        sys.exit(f"Error: Drive {drive_id} not found on this account. Available: {names}.")

    config = _write_profile(
        config,
        profile,
        token,
        entry.get("account_id"),
        default_drive=drive_id,
    )
    _write_config(config, CONFIG_PATH)
    print(f"Default drive set to {drive_id} for profile '{profile}'.")


def _cmd_configure_set_default_mail(args: argparse.Namespace) -> None:
    """Set default_mail on the active profile after validating the hosting exists."""
    explicit = getattr(args, "profile", None)
    if explicit:
        _validate_profile_name(explicit)
        config = _read_config()
        if explicit not in (config.get("profiles") or {}):
            sys.exit(
                f"Error: Profile '{explicit}' not found. "
                f"Run `ik configure --profile {explicit}` to create it first."
            )
        profile = explicit
    else:
        config = _read_config()
        try:
            profile = _resolve_default_profile(config)
        except _NoDefaultProfile:
            sys.exit(
                "Error: No configured profile. Run `ik configure` first, or pass --profile <name>."
            )

    mail_hosting_id: int = args.default_mail
    entry = config["profiles"][profile]
    token = entry.get("token")
    if not token:
        sys.exit(
            f"Error: Profile '{profile}' has no token. Run `ik configure --profile {profile}` first."
        )

    client = KDriveClient(token)
    try:
        client.list_mailboxes(mail_hosting_id)
    except KDriveError as e:
        sys.exit(f"Error: Mail hosting {mail_hosting_id} not reachable on this account: {e}")

    config = _write_profile(
        config,
        profile,
        token,
        entry.get("account_id"),
        default_mail=mail_hosting_id,
    )
    _write_config(config, CONFIG_PATH)
    print(f"Default mail hosting set to {mail_hosting_id} for profile '{profile}'.")


_COMPLETION_FILES = {
    "bash": "ik.bash",
    "zsh": "ik.zsh",
    "fish": "ik.fish",
}


def cmd_completion(args: argparse.Namespace) -> None:
    """Print a shell completion script to stdout.

    The user installs it via `eval "$(ik completion bash)"` (bash),
    `ik completion zsh > "${fpath[1]}/_ik"` (zsh), or
    `ik completion fish | source` (fish).
    """
    try:
        text = resources.files("ik.completions").joinpath(_COMPLETION_FILES[args.shell]).read_text()
    except (KeyError, FileNotFoundError):
        sys.exit(f"Error: No completion script for shell '{args.shell}'.")
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def cmd_drives(args: argparse.Namespace, client: KDriveClient) -> None:
    """List all drives."""
    drives = client.list_drives()
    if not drives:
        print("No drives found.")
        return

    for d in drives:
        used_gb = d.used_size / 1024**3
        total_gb = d.size / 1024**3
        status = "active" if not d.is_locked else "locked"
        print(f"  {d.id}  {d.name}  ({used_gb:.1f}/{total_gb:.1f} GB) [{status}]")


def cmd_whoami(args: argparse.Namespace, client: KDriveClient) -> None:
    """Show current user info."""
    body = client._request("GET", "/1/accounts")
    accounts = body.get("data", [])
    if not accounts:
        sys.exit("No accounts found.")

    for acc in accounts:
        print(f"Account ID: {acc['id']}")
        print(f"Name: {acc.get('name', 'N/A')}")
        print(f"Email: {acc.get('email', 'N/A')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ik",
        description="Infomaniak CLI - AWS CLI style for Infomaniak Cloud",
        parents=[GLOBAL],
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # configure
    configure_p = sub.add_parser("configure", help="Configure credentials", parents=[GLOBAL_SUB])
    configure_p.add_argument("--list", action="store_true", help="List configured profiles")
    configure_p.add_argument(
        "--default-drive",
        type=int,
        default=None,
        metavar="ID",
        help="Set the default kDrive ID for the active profile",
    )
    configure_p.add_argument(
        "--default-mail",
        type=int,
        default=None,
        metavar="ID",
        help="Set the default mail hosting ID for the active profile",
    )

    # whoami
    sub.add_parser("whoami", help="Show current user", parents=[GLOBAL_SUB])

    # drives
    sub.add_parser("drives", help="List all kDrives", parents=[GLOBAL_SUB])

    # drive subcommands
    add_drive_commands(sub, GLOBAL_SUB)

    # vps subcommands
    add_vps_commands(sub, GLOBAL_SUB)

    # mail subcommands
    add_mail_commands(sub, GLOBAL_SUB)

    # completion
    completion_p = sub.add_parser(
        "completion",
        help="Print shell completion script",
        parents=[GLOBAL_SUB],
    )
    completion_p.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to generate a completion script for",
    )

    args = parser.parse_args()

    if args.cmd == "configure":
        cmd_configure(args)
        return

    if args.cmd == "completion":
        cmd_completion(args)
        return

    # Resolve active profile: explicit --profile wins, else config default.
    profile: str | None = None
    explicit = getattr(args, "profile", None)
    if explicit:
        _validate_profile_name(explicit)
        config = _read_config()
        profiles = config.get("profiles") or {}
        if explicit not in profiles:
            existing = sorted(profiles.keys())
            if existing:
                sys.exit(
                    f"Error: Profile '{explicit}' not found. "
                    f"Run `ik configure --profile {explicit}` to create it, "
                    f"or use one of: {', '.join(existing)}."
                )
            sys.exit(
                f"Error: Profile '{explicit}' not found. "
                f"Run `ik configure --profile {explicit}` to create it."
            )
        profile = explicit
    else:
        try:
            profile = _resolve_default_profile(_read_config())
        except _NoDefaultProfile:
            profile = None

    # Token & account_id
    token = _resolve_token(args, profile)
    account_id = _resolve_account_id(profile)
    if account_id is not None:
        os.environ["INFOMANIAK_ACCOUNT_ID"] = str(account_id)

    # Inject default_drive from the active profile (if set) so drive
    # commands can read it without re-reading the config.
    if profile is not None:
        config = _read_config()
        default_drive = (config.get("profiles") or {}).get(profile, {}).get("default_drive")
        if default_drive is not None:
            args.default_drive = default_drive
        # Inject default_mail for mail subcommands that need a hosting id.
        # Only present when a subcommand like mailboxes/messages/message
        # was selected (those subparsers declare the arg; others don't).
        if getattr(args, "mail_hosting_id", None) is None:
            default_mail = (config.get("profiles") or {}).get(profile, {}).get("default_mail")
            if default_mail is not None:
                args.mail_hosting_id = default_mail

    # Create client
    client = KDriveClient(token)

    # Dispatch
    if args.cmd == "whoami":
        cmd_whoami(args, client)
    elif args.cmd == "drives":
        cmd_drives(args, client)
    elif args.cmd == "drive":
        try:
            args.func(args, client)
        except KDriveError as e:
            sys.exit(f"Error: {e}")
    elif args.cmd == "vps":
        try:
            args.func(args, client)
        except KDriveError as e:
            sys.exit(f"Error: {e}")
    elif args.cmd == "mail":
        try:
            args.func(args, client)
        except KDriveError as e:
            sys.exit(f"Error: {e}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
