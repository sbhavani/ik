"""ik CLI - Infomaniak CLI tool."""

from __future__ import annotations

import argparse
import os
import sys

from . import KDriveClient, KDriveError
from .driver import add_drive_commands


def _resolve_token(args: argparse.Namespace) -> str:
    """Resolve API token from args or environment."""
    if args.token:
        return args.token

    token = os.environ.get("INFOMANIAK_TOKEN")
    if token:
        return token

    config_path = os.path.expanduser("~/.config/ik/config.json")
    if os.path.exists(config_path):
        import json

        with open(config_path) as f:
            config = json.load(f)
            if config.get("token"):
                return config["token"]

    sys.exit("Error: No API token found. Set INFOMANIAK_TOKEN env or run `ik configure`")


def _resolve_account_id(token: str) -> int | None:
    """Resolve account ID from env or config."""
    account_id = os.environ.get("INFOMANIAK_ACCOUNT_ID")
    if account_id:
        return int(account_id)

    config_path = os.path.expanduser("~/.config/ik/config.json")
    if os.path.exists(config_path):
        import json

        with open(config_path) as f:
            config = json.load(f)
            if config.get("account_id"):
                return int(config["account_id"])

    return None


def cmd_configure(args: argparse.Namespace) -> None:
    """Interactive configuration."""
    import json

    config_dir = os.path.expanduser("~/.config/ik")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.json")

    print("ik CLI Configuration\n")

    token = input("Enter your Infomaniak API token: ").strip()
    if not token:
        sys.exit("Error: Token required")

    # Save token
    config = {"token": token}
    with open(config_path, "w") as f:
        json.dump(config, f)
    print(f"Token saved to {config_path}\n")

    # Verify token and detect account
    try:
        client = KDriveClient(token)
        account_id = _resolve_account_id(token)
        if account_id is None:
            account_id = client.account_id
        print(f"Authenticated successfully. Account ID: {account_id}")
        config["account_id"] = account_id
        with open(config_path, "w") as f:
            json.dump(config, f)
    except KDriveError as e:
        sys.exit(f"Error: {e}")


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
    )
    parser.add_argument("--token", help="API token")
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress non-essential output (status lines)"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip confirmation prompts (for scripts)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # configure
    sub.add_parser("configure", help="Configure credentials")

    # whoami
    sub.add_parser("whoami", help="Show current user")

    # drives
    sub.add_parser("drives", help="List all kDrives")

    # drive subcommands
    add_drive_commands(sub)

    args = parser.parse_args()

    if args.cmd == "configure":
        cmd_configure(args)
        return

    # Get token
    token = _resolve_token(args)

    # Handle account ID override
    account_id = _resolve_account_id(token)
    if account_id:
        os.environ["INFOMANIAK_ACCOUNT_ID"] = str(account_id)

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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
