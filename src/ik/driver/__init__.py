"""kDrive commands for ik CLI."""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from .. import Drive, File, KDriveClient, KDriveError


def _format_size(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f}G"
    if size >= 1024**2:
        return f"{size / 1024**2:.1f}M"
    if size >= 1024:
        return f"{size / 1024:.1f}K"
    return f"{size}B"


def _print_file_entry(f: File, show_id: bool = False) -> None:
    marker = "d" if f.is_directory else "-"
    size_str = _format_size(f.size) if not f.is_directory else "DIR"
    name = f.name
    if show_id:
        print(f"  {marker} {f.id:>10}  {size_str:>8}  {name}")
    else:
        print(f"  {marker} {size_str:>8}  {name}")


# ── Command Implementations ──────────────────────────────────────────

def cmd_ls(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """List files in a directory."""
    drive_id = args.drive or _get_default_drive(client)
    directory_id = _resolve_directory(client, drive_id, args.path)

    files = list(client.list_files(drive_id, directory_id))
    if not files:
        out.write("(empty)\n")
        return

    for f in files:
        _print_file_entry(f, show_id=args.show_id)


def cmd_tree(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Display directory tree."""
    drive_id = args.drive or _get_default_drive(client)
    root_id = _resolve_directory(client, drive_id, args.path)

    def walk(directory_id: int, prefix: str = "", is_last: bool = True) -> None:
        files = list(client.list_files(drive_id, directory_id))
        # Separate dirs and files
        dirs = [f for f in files if f.is_directory]
        regular_files = [f for f in files if not f.is_directory]

        all_items = dirs + regular_files
        for i, f in enumerate(all_items):
            is_last_item = i == len(all_items) - 1
            connector = "`--" if is_last_item else "|--"
            out.write(f"{prefix}{connector} {f.name}\n")

            if f.is_directory:
                extension = "`   " if is_last_item else "|  "
                walk(f.id, prefix + extension, is_last_item)

    out.write(f".\n")
    walk(root_id)


def cmd_mkdir(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Create a directory."""
    drive_id = args.drive or _get_default_drive(client)

    path = args.path.rstrip("/")
    if "/" in path:
        parent_path, dir_name = path.rsplit("/", 1)
        parent_id = client.resolve_path(drive_id, parent_path)
    else:
        parent_id = 1
        dir_name = path

    result = client.create_directory(drive_id, parent_id, dir_name)
    out.write(f"Created: {result.name} (id: {result.id})\n")


def cmd_upload(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Upload a file."""
    from pathlib import Path

    drive_id = args.drive or _get_default_drive(client)
    local_path = Path(args.local)
    directory_id = args.dir or 1

    if not local_path.exists():
        raise KDriveError(f"File not found: {local_path}")

    file_data = local_path.read_bytes()
    out.write(f"Uploading {local_path.name} ({len(file_data) / 1024:.1f}KB)...\n")

    result = client.upload_file(drive_id, directory_id, local_path.name, file_data)
    out.write(f"Uploaded: {result.name} (id: {result.id})\n")


def cmd_download(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Download a file."""
    from pathlib import Path

    drive_id = args.drive or _get_default_drive(client)
    file_id = int(args.file)
    info = client.get_file(drive_id, file_id)

    local_path = Path(args.local) if args.local else Path(info.name)
    if local_path.is_dir():
        local_path = local_path / info.name

    out.write(f"Downloading {info.name}...\n")
    resp = client.download_file(drive_id, file_id)
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    out.write(f"Saved: {local_path} ({local_path.stat().st_size / 1024:.1f}KB)\n")


def cmd_search(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Search for files by name."""
    drive_id = args.drive or _get_default_drive(client)
    results = list(client.search(drive_id, args.query))

    if not results:
        out.write("No results.\n")
        return

    for f in results:
        _print_file_entry(f, show_id=args.show_id)


def cmd_rm(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Move a file to trash."""
    drive_id = args.drive or _get_default_drive(client)
    path = args.path

    if path.isdigit():
        file_id = int(path)
    else:
        file_id = client.resolve_path(drive_id, path)

    client.trash_file(drive_id, file_id)
    out.write(f"Trashed: {path}\n")


def cmd_info(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Get detailed file information."""
    import json

    drive_id = args.drive or _get_default_drive(client)
    path = args.path

    if path.isdigit():
        file_id = int(path)
    else:
        file_id = client.resolve_path(drive_id, path)

    info = client.get_file(drive_id, file_id)

    data = {
        "id": info.id,
        "name": info.name,
        "type": "directory" if info.is_directory else "file",
        "size": info.size,
        "created_at": info.created_at.isoformat() if info.created_at else None,
        "modified_at": info.modified_at.isoformat() if info.modified_at else None,
        "parent_id": info.parent_id,
    }
    out.write(json.dumps(data, indent=2) + "\n")


# ── Helpers ───────────────────────────────────────────────────────────

def _get_default_drive(client: KDriveClient) -> int:
    """Get the configured default drive or prompt."""
    drives = client.list_drives()
    if not drives:
        raise KDriveError("No drives found. Check your account.")
    if len(drives) == 1:
        return drives[0].id

    for i, d in enumerate(drives):
        out = sys.stdout
        out.write(f"  [{i+1}] {d.name} ({d.id})\n")
    out.write("\n")
    raise KDriveError("Multiple drives found. Use --drive to specify.")


def _resolve_directory(client: KDriveClient, drive_id: int, path: str | None) -> int:
    """Resolve a path to a directory ID."""
    if path is None:
        return 1
    if path.isdigit():
        return int(path)
    return client.resolve_path(drive_id, path)


def add_drive_commands(parser: argparse.ArgumentParser) -> None:
    """Add kDrive subcommands to the parser."""
    drive_parser = parser.add_parser("drive", help="kDrive commands")
    drive_sub = drive_parser.add_subparsers(dest="drive_cmd", required=True)

    # drive ls
    ls = drive_sub.add_parser("ls", help="List directory contents")
    ls.add_argument("path", nargs="?", default=None)
    ls.add_argument("--drive", type=int, help="Drive ID")
    ls.add_argument("--id", dest="show_id", action="store_true", help="Show file IDs")
    ls.set_defaults(func=cmd_ls)

    # drive tree
    tree = drive_sub.add_parser("tree", help="Display directory tree")
    tree.add_argument("path", nargs="?", default=None)
    tree.add_argument("--drive", type=int, help="Drive ID")
    tree.set_defaults(func=cmd_tree)

    # drive mkdir
    mkdir = drive_sub.add_parser("mkdir", help="Create a directory")
    mkdir.add_argument("path", help="Directory path")
    mkdir.add_argument("--drive", type=int, help="Drive ID")
    mkdir.set_defaults(func=cmd_mkdir)

    # drive upload
    upload = drive_sub.add_parser("upload", help="Upload a file")
    upload.add_argument("local", help="Local file path")
    upload.add_argument("--drive", type=int, help="Drive ID")
    upload.add_argument("--dir", type=int, default=1, help="Directory ID")
    upload.set_defaults(func=cmd_upload)

    # drive download
    download = drive_sub.add_parser("download", help="Download a file")
    download.add_argument("file", help="File ID or path")
    download.add_argument("--local", help="Local destination path")
    download.add_argument("--drive", type=int, help="Drive ID")
    download.set_defaults(func=cmd_download)

    # drive search
    search = drive_sub.add_parser("search", help="Search for files")
    search.add_argument("query", help="Search query")
    search.add_argument("--drive", type=int, help="Drive ID")
    search.add_argument("--id", dest="show_id", action="store_true", help="Show file IDs")
    search.set_defaults(func=cmd_search)

    # drive rm
    rm = drive_sub.add_parser("rm", help="Move file to trash")
    rm.add_argument("path", help="File ID or path")
    rm.add_argument("--drive", type=int, help="Drive ID")
    rm.set_defaults(func=cmd_rm)

    # drive info
    info = drive_sub.add_parser("info", help="Get file details")
    info.add_argument("path", help="File ID or path")
    info.add_argument("--drive", type=int, help="Drive ID")
    info.set_defaults(func=cmd_info)