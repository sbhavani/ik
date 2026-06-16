"""kDrive commands for ik CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from .. import File, KDriveClient, KDriveError, _UNSET


def _is_json(args: argparse.Namespace) -> bool:
    """True when --output json was passed. Defaults to False for callers
    that don't thread the global flags (e.g. legacy test paths)."""
    return getattr(args, "output", "text") == "json"


CHUNKED_THRESHOLD = 16 * 1024 * 1024  # 16 MB


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


def _make_progress(
    label: str,
    total: int,
    stream: TextIO,
    enabled: bool,
) -> Callable[[int, int], None]:
    """Return a (sent, total) → None callback that renders a TTY progress bar.

    When `enabled` is False or `total <= 0`, returns a no-op so callers
    don't need to branch. When enabled, overwrites the same line via '\\r'
    on `stream` and flushes after each render.
    """
    if not enabled or total <= 0:
        return lambda sent, total: None

    width = 30

    def render(sent: int, total: int) -> None:
        pct = sent / total * 100
        filled = int(width * sent / total)
        bar = "#" * filled + "-" * (width - filled)
        stream.write(
            f"\r{label}: [{bar}] {pct:5.1f}% ({sent / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB)"
        )
        stream.flush()

    return render


# ── Command Implementations ──────────────────────────────────────────


def cmd_ls(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """List files in a directory."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    directory_id = _resolve_directory(client, drive_id, args.path)

    files = list(client.list_files(drive_id, directory_id))
    if _is_json(args):
        out.write(json.dumps([f.to_dict() for f in files], indent=2) + "\n")
        return

    if not files:
        out.write("(empty)\n")
        return

    for f in files:
        _print_file_entry(f, show_id=args.show_id)


def cmd_tree(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Display directory tree."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    root_id = _resolve_directory(client, drive_id, args.path)

    if _is_json(args):

        def entry(f: File) -> dict[str, Any]:
            if f.is_directory:
                children = list(client.list_files(drive_id, f.id))
                return {
                    "name": f.name,
                    "is_directory": True,
                    "children": [entry(child) for child in children],
                }
            return {
                "name": f.name,
                "is_directory": False,
                "children": None,
            }

        root_files = list(client.list_files(drive_id, root_id))
        root = {
            "name": ".",
            "is_directory": True,
            "children": [entry(f) for f in root_files],
        }
        out.write(json.dumps(root, indent=2) + "\n")
        return

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

    out.write(".\n")
    walk(root_id)


def cmd_mkdir(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Create a directory."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)

    path = args.path.rstrip("/")
    if "/" in path:
        parent_path, dir_name = path.rsplit("/", 1)
        parent_id = client.resolve_path(drive_id, parent_path)
    else:
        parent_id = 1
        dir_name = path

    result = client.create_directory(drive_id, parent_id, dir_name)
    if _is_json(args):
        out.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return
    out.write(f"Created: {result.name} (id: {result.id})\n")


def cmd_upload(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Upload a file."""
    from pathlib import Path

    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    local_path = Path(args.local)
    directory_id = args.dir or 1

    if not local_path.exists():
        raise KDriveError(f"File not found: {local_path}")

    total = local_path.stat().st_size
    progress = _make_progress(local_path.name, total, sys.stderr, sys.stderr.isatty())

    if total < CHUNKED_THRESHOLD:
        data = local_path.read_bytes()
        if not getattr(args, "quiet", False) and not _is_json(args):
            out.write(f"Uploading {local_path.name} ({total / 1024:.1f}KB)...\n")
        result = client.upload_file(drive_id, directory_id, local_path.name, data)
    else:
        if not getattr(args, "quiet", False) and not _is_json(args):
            out.write(f"Uploading {local_path.name} ({total / 1024 / 1024:.1f}MB) — chunked...\n")
        result = client.upload_file_streaming(
            drive_id, directory_id, local_path.name, local_path, on_progress=progress
        )
        sys.stderr.write("\n")

    if _is_json(args):
        out.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return
    out.write(f"Uploaded: {result.name} (id: {result.id})\n")


def cmd_download(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Download a file."""
    from pathlib import Path

    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = int(args.file)
    info = client.get_file(drive_id, file_id)

    local_path = Path(args.local) if args.local else Path(info.name)
    if local_path.is_dir():
        local_path = local_path / info.name

    if not getattr(args, "quiet", False) and not _is_json(args):
        out.write(f"Downloading {info.name}...\n")
    resp = client.download_file(drive_id, file_id)
    total = int(resp.headers.get("Content-Length", 0)) if resp.headers else 0
    progress = _make_progress(info.name, total, sys.stderr, sys.stderr.isatty())
    received = 0
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                received += len(chunk)
                progress(received, total)
    if total > 0:
        sys.stderr.write("\n")

    if _is_json(args):
        out.write(
            json.dumps(
                {
                    "path": str(local_path),
                    "name": info.name,
                    "size": local_path.stat().st_size,
                },
                indent=2,
            )
            + "\n"
        )
        return
    out.write(f"Saved: {local_path} ({local_path.stat().st_size / 1024:.1f}KB)\n")


def cmd_search(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Search for files by name."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    results = list(client.search(drive_id, args.query))

    if _is_json(args):
        out.write(json.dumps([f.to_dict() for f in results], indent=2) + "\n")
        return

    if not results:
        out.write("No results.\n")
        return

    for f in results:
        _print_file_entry(f, show_id=args.show_id)


def cmd_rm(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Move a file to trash. Prompts for confirmation unless --yes is set."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    path = args.path

    if path.isdigit():
        file_id = int(path)
    else:
        file_id = client.resolve_path(drive_id, path)

    if not getattr(args, "yes", False):
        if not sys.stdin.isatty():
            raise KDriveError("Refusing to trash without --yes in non-interactive mode")
        response = input(f"Trash {path}? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            raise KDriveError("Aborted")

    client.trash_file(drive_id, file_id)
    if _is_json(args):
        out.write(json.dumps({"trashed": path}, indent=2) + "\n")
        return
    out.write(f"Trashed: {path}\n")


def cmd_info(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Get detailed file information."""
    import json

    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
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


def cmd_mv(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Move a file or directory to another directory.

    kDrive move is async — the operation runs in the background and a
    cancel_id is returned. Use /1/async/tasks/{id} to poll or
    /2/drive/{drive_id}/cancel to abort.
    """
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    src_id = _resolve_source_id(client, drive_id, args.src)
    dst_id = _resolve_directory(client, drive_id, args.dst)

    op = client.move_file(drive_id, src_id, dst_id, name=args.name)
    if _is_json(args):
        out.write(
            json.dumps(
                {
                    "cancel_id": op.cancel_id,
                    "valid_until": op.valid_until.isoformat() if op.valid_until else None,
                    "async": True,
                },
                indent=2,
            )
            + "\n"
        )
        return
    out.write(f"Move queued: cancel_id={op.cancel_id}\n")
    if not getattr(args, "quiet", False):
        out.write("(Move is async on the kDrive side; the operation runs in the background.)\n")


def cmd_cp(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Copy a file or directory to another directory."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    src_id = _resolve_source_id(client, drive_id, args.src)
    dst_id = _resolve_directory(client, drive_id, args.dst)

    result = client.copy_file(drive_id, src_id, dst_id, name=args.name)
    if _is_json(args):
        out.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return
    out.write(f"Copied: {result.name} (id: {result.id})\n")


def cmd_share_create(
    args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout
) -> None:
    """Create a public share link for a file."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = _resolve_source_id(client, drive_id, args.file)
    link = client.create_share_link(
        drive_id,
        file_id,
        right=args.right,
        password=args.password,
        valid_until=args.valid_until,
        can_download=args.can_download,
        can_edit=args.can_edit,
        can_see_info=args.can_see_info,
        can_comment=args.can_comment,
        can_request_access=args.can_request_access,
        can_see_stats=args.can_see_stats,
    )
    if _is_json(args):
        out.write(json.dumps({"url": link.url}, indent=2) + "\n")
        return
    out.write(f"{link.url}\n")


def cmd_share_get(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """Show the share-link settings for a file (JSON)."""
    import json

    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = _resolve_source_id(client, drive_id, args.file)
    link = client.get_share_link(drive_id, file_id)
    data = {
        "url": link.url,
        "file_id": link.file_id,
        "right": link.right,
        "valid_until": link.valid_until.isoformat() if link.valid_until else None,
        "capabilities": {
            "can_download": link.can_download,
            "can_edit": link.can_edit,
            "can_see_info": link.can_see_info,
            "can_comment": link.can_comment,
            "can_request_access": link.can_request_access,
            "can_see_stats": link.can_see_stats,
        },
        "access_blocked": link.access_blocked,
        "views": link.views,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        "created_by": link.created_by,
    }
    out.write(json.dumps(data, indent=2) + "\n")


def cmd_share_update(
    args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout
) -> None:
    """Partially update a share link. Only flags you pass are sent."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = _resolve_source_id(client, drive_id, args.file)

    changed = {
        "right": args.right,
        "password": args.password,
        "valid_until": args.valid_until,
        "can_download": args.can_download,
        "can_edit": args.can_edit,
        "can_see_info": args.can_see_info,
        "can_comment": args.can_comment,
        "can_request_access": args.can_request_access,
        "can_see_stats": args.can_see_stats,
    }
    kwargs = {k: v for k, v in changed.items() if v is not _UNSET}
    link = client.update_share_link(drive_id, file_id, **kwargs)
    if _is_json(args):
        out.write(json.dumps({"url": link.url}, indent=2) + "\n")
        return
    out.write(f"Updated: {link.url}\n")


def cmd_share_remove(
    args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout
) -> None:
    """Remove the share link from a file."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = _resolve_source_id(client, drive_id, args.file)
    client.delete_share_link(drive_id, file_id)
    if _is_json(args):
        out.write(json.dumps({"removed": args.file}, indent=2) + "\n")
        return
    out.write(f"Removed share link for {args.file}\n")


def cmd_share_ls(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """List files that have a share link."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    files = list(client.list_shared_files(drive_id))
    if _is_json(args):
        out.write(json.dumps([sf.to_dict() for sf in files], indent=2) + "\n")
        return
    if not files:
        out.write("(no shared files)\n")
        return
    for sf in files:
        out.write(f"  {sf.id:>10}  {sf.name}  (users: {sf.users})\n")


def cmd_trash_ls(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """List files in the trash."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    files = list(client.list_trash(drive_id))

    if _is_json(args):
        out.write(json.dumps([f.to_dict() for f in files], indent=2) + "\n")
        return
    if not files:
        out.write("(trash is empty)\n")
        return
    for f in files:
        marker = "d" if f.is_directory else "-"
        size_str = _format_size(f.size) if not f.is_directory else "DIR"
        out.write(f"  {marker} {f.id:>10}  {size_str:>8}  {f.name}\n")


def cmd_trash_empty(
    args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout
) -> None:
    """Permanently delete everything in the trash. Prompts unless --yes."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)

    if not getattr(args, "yes", False):
        if not sys.stdin.isatty():
            raise KDriveError("Refusing to empty trash without --yes in non-interactive mode")
        response = (
            input("Empty trash? This permanently deletes all trashed files. [y/N] ").strip().lower()
        )
        if response not in ("y", "yes"):
            raise KDriveError("Aborted")

    client.empty_trash(drive_id)
    if _is_json(args):
        out.write(json.dumps({"emptied": True}, indent=2) + "\n")
        return
    out.write("Trash emptied.\n")


def cmd_trash_restore(
    args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout
) -> None:
    """Restore a file from the trash. Async on the kDrive side; may return
    a cancel handle for polling or aborting."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)
    file_id = _resolve_source_id(client, drive_id, args.file)
    destination_id = 1 if args.to is None else _resolve_directory(client, drive_id, args.to)

    op = client.restore_file(drive_id, file_id, destination_id)
    if _is_json(args):
        if op is None:
            out.write(json.dumps({"restored": True}, indent=2) + "\n")
        else:
            out.write(
                json.dumps(
                    {
                        "cancel_id": op.cancel_id,
                        "valid_until": op.valid_until.isoformat() if op.valid_until else None,
                        "async": True,
                    },
                    indent=2,
                )
                + "\n"
            )
        return
    if op is None:
        out.write(f"Restored: {args.file}\n")
    else:
        out.write(f"Restore queued: cancel_id={op.cancel_id}\n")


def cmd_activity(args: argparse.Namespace, client: KDriveClient, out: TextIO = sys.stdout) -> None:
    """List recent drive activity (file ops, share changes, etc.)."""
    drive_id = args.drive or getattr(args, "default_drive", None) or _get_default_drive(client)

    file_ids: list[int] = []
    for f in args.files or []:
        file_ids.append(_resolve_source_id(client, drive_id, f))

    entries = list(
        client.list_activity(
            drive_id,
            from_=args.since,
            until=args.until,
            users=args.users,
            actions=args.actions,
            files=file_ids or None,
            limit=args.limit,
        )
    )

    if _is_json(args):
        out.write(json.dumps([a.to_dict() for a in entries], indent=2) + "\n")
        return
    if not entries:
        out.write("(no activity)\n")
        return

    for a in entries:
        ts = a.created_at.isoformat(timespec="seconds") if a.created_at else "?"
        user = f"user={a.user_id}" if a.user_id is not None else "system"
        path = a.new_path or a.old_path
        if a.old_path and a.new_path and a.old_path != a.new_path:
            path = f"{a.old_path} -> {a.new_path}"
        out.write(f"  {ts}  {a.action:<12}  {user}  {path}\n")


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
        out.write(f"  [{i + 1}] {d.name} ({d.id})\n")
    out.write("\n")
    raise KDriveError("Multiple drives found. Use --drive to specify.")


def _resolve_directory(client: KDriveClient, drive_id: int, path: str | None) -> int:
    """Resolve a path to a directory ID."""
    if path is None:
        return 1
    if path.isdigit():
        return int(path)
    return client.resolve_path(drive_id, path)


def _resolve_source_id(client: KDriveClient, drive_id: int, src: str) -> int:
    """Resolve a source reference (digit string or path) to a file/dir ID."""
    if src.isdigit():
        return int(src)
    return client.resolve_path(drive_id, src)


def add_drive_commands(
    parser: argparse.ArgumentParser, global_flags: argparse.ArgumentParser
) -> None:
    """Add kDrive subcommands to the parser."""
    drive_parser = parser.add_parser("drive", help="kDrive commands", parents=[global_flags])
    drive_sub = drive_parser.add_subparsers(dest="drive_cmd", required=True)

    # drive ls
    ls = drive_sub.add_parser("ls", help="List directory contents", parents=[global_flags])
    ls.add_argument("path", nargs="?", default=None)
    ls.add_argument("--drive", type=int, help="Drive ID")
    ls.add_argument("--id", dest="show_id", action="store_true", help="Show file IDs")
    ls.set_defaults(func=cmd_ls)

    # drive tree
    tree = drive_sub.add_parser("tree", help="Display directory tree", parents=[global_flags])
    tree.add_argument("path", nargs="?", default=None)
    tree.add_argument("--drive", type=int, help="Drive ID")
    tree.set_defaults(func=cmd_tree)

    # drive mkdir
    mkdir = drive_sub.add_parser("mkdir", help="Create a directory", parents=[global_flags])
    mkdir.add_argument("path", help="Directory path")
    mkdir.add_argument("--drive", type=int, help="Drive ID")
    mkdir.set_defaults(func=cmd_mkdir)

    # drive upload
    upload = drive_sub.add_parser("upload", help="Upload a file", parents=[global_flags])
    upload.add_argument("local", help="Local file path")
    upload.add_argument("--drive", type=int, help="Drive ID")
    upload.add_argument("--dir", type=int, default=1, help="Directory ID")
    upload.set_defaults(func=cmd_upload)

    # drive download
    download = drive_sub.add_parser("download", help="Download a file", parents=[global_flags])
    download.add_argument("file", help="File ID or path")
    download.add_argument("--local", help="Local destination path")
    download.add_argument("--drive", type=int, help="Drive ID")
    download.set_defaults(func=cmd_download)

    # drive search
    search = drive_sub.add_parser("search", help="Search for files", parents=[global_flags])
    search.add_argument("query", help="Search query")
    search.add_argument("--drive", type=int, help="Drive ID")
    search.add_argument("--id", dest="show_id", action="store_true", help="Show file IDs")
    search.set_defaults(func=cmd_search)

    # drive rm
    rm = drive_sub.add_parser("rm", help="Move file to trash", parents=[global_flags])
    rm.add_argument("path", help="File ID or path")
    rm.add_argument("--drive", type=int, help="Drive ID")
    rm.set_defaults(func=cmd_rm)

    # drive info
    info = drive_sub.add_parser("info", help="Get file details", parents=[global_flags])
    info.add_argument("path", help="File ID or path")
    info.add_argument("--drive", type=int, help="Drive ID")
    info.set_defaults(func=cmd_info)

    # drive mv
    mv = drive_sub.add_parser("mv", help="Move a file or directory", parents=[global_flags])
    mv.add_argument("src", help="Source file/dir (ID or path)")
    mv.add_argument("dst", help="Destination directory (ID or path)")
    mv.add_argument("--name", help="New name for rename-and-move")
    mv.add_argument("--drive", type=int, help="Drive ID")
    mv.set_defaults(func=cmd_mv)

    # drive cp
    cp = drive_sub.add_parser("cp", help="Copy a file or directory", parents=[global_flags])
    cp.add_argument("src", help="Source file/dir (ID or path)")
    cp.add_argument("dst", help="Destination directory (ID or path)")
    cp.add_argument("--name", help="New name for rename-and-copy")
    cp.add_argument("--drive", type=int, help="Drive ID")
    cp.set_defaults(func=cmd_cp)

    # drive share
    share = drive_sub.add_parser("share", help="Manage public share links", parents=[global_flags])
    share_sub = share.add_subparsers(dest="share_cmd", required=True)

    # share create
    share_create = share_sub.add_parser(
        "create", help="Create a share link", parents=[global_flags]
    )
    share_create.add_argument("file", help="File ID or path")
    share_create.add_argument(
        "--right", choices=["public", "password", "inherit"], default="public"
    )
    share_create.add_argument("--password", help="Password (when --right=password)")
    share_create.add_argument("--valid-until", type=int, default=None)
    for flag in (
        "can-download",
        "can-edit",
        "can-see-info",
        "can-comment",
        "can-request-access",
        "can-see-stats",
    ):
        dest = flag.replace("-", "_")
        share_create.add_argument(f"--{flag}", dest=dest, action="store_true")
        share_create.add_argument(f"--no-{flag}", dest=dest, action="store_false")
        share_create.set_defaults(**{dest: False})
    share_create.set_defaults(can_download=True)
    share_create.add_argument("--drive", type=int, help="Drive ID")
    share_create.set_defaults(func=cmd_share_create)

    # share get
    share_get = share_sub.add_parser("get", help="Get share-link settings", parents=[global_flags])
    share_get.add_argument("file", help="File ID or path")
    share_get.add_argument("--drive", type=int, help="Drive ID")
    share_get.set_defaults(func=cmd_share_get)

    # share update
    share_update = share_sub.add_parser(
        "update", help="Update a share link", parents=[global_flags]
    )
    share_update.add_argument("file", help="File ID or path")
    share_update.add_argument("--right", choices=["public", "password", "inherit"], default=_UNSET)
    share_update.add_argument("--password", default=_UNSET)
    share_update.add_argument("--valid-until", type=int, default=_UNSET)
    for flag in (
        "can-download",
        "can-edit",
        "can-see-info",
        "can-comment",
        "can-request-access",
        "can-see-stats",
    ):
        dest = flag.replace("-", "_")
        share_update.add_argument(f"--{flag}", dest=dest, action="store_true")
        share_update.add_argument(f"--no-{flag}", dest=dest, action="store_false")
        share_update.set_defaults(**{dest: _UNSET})
    share_update.add_argument("--drive", type=int, help="Drive ID")
    share_update.set_defaults(func=cmd_share_update)

    # share remove
    share_remove = share_sub.add_parser(
        "remove", help="Remove a share link", parents=[global_flags]
    )
    share_remove.add_argument("file", help="File ID or path")
    share_remove.add_argument("--drive", type=int, help="Drive ID")
    share_remove.set_defaults(func=cmd_share_remove)

    # share ls
    share_ls = share_sub.add_parser(
        "ls", help="List files with share links", parents=[global_flags]
    )
    share_ls.add_argument("--drive", type=int, help="Drive ID")
    share_ls.set_defaults(func=cmd_share_ls)

    # drive trash
    trash = drive_sub.add_parser("trash", help="Manage the trash", parents=[global_flags])
    trash_sub = trash.add_subparsers(dest="trash_cmd", required=True)

    # trash ls
    trash_ls = trash_sub.add_parser("ls", help="List trashed files", parents=[global_flags])
    trash_ls.add_argument("--drive", type=int, help="Drive ID")
    trash_ls.set_defaults(func=cmd_trash_ls)

    # trash empty
    trash_empty = trash_sub.add_parser(
        "empty", help="Permanently empty the trash", parents=[global_flags]
    )
    trash_empty.add_argument("--drive", type=int, help="Drive ID")
    trash_empty.set_defaults(func=cmd_trash_empty)

    # trash restore
    trash_restore = trash_sub.add_parser(
        "restore", help="Restore a file from the trash", parents=[global_flags]
    )
    trash_restore.add_argument("file", help="File ID or path")
    trash_restore.add_argument("--to", help="Destination directory (ID or path); defaults to root")
    trash_restore.add_argument("--drive", type=int, help="Drive ID")
    trash_restore.set_defaults(func=cmd_trash_restore)

    # drive activity
    activity = drive_sub.add_parser(
        "activity", help="List drive activity log", parents=[global_flags]
    )
    activity.add_argument(
        "--user", dest="users", action="append", type=int, help="Filter by user ID (repeatable)"
    )
    activity.add_argument(
        "--action",
        dest="actions",
        action="append",
        help="Filter by action type (repeatable)",
    )
    activity.add_argument(
        "--file",
        dest="files",
        action="append",
        help="Filter by file ID or path (repeatable)",
    )
    activity.add_argument("--since", type=int, help="Start timestamp (Unix seconds)")
    activity.add_argument("--until", type=int, help="End timestamp (Unix seconds)")
    activity.add_argument("--limit", type=int, default=10, help="Page size (default: 10)")
    activity.add_argument("--drive", type=int, help="Drive ID")
    activity.set_defaults(func=cmd_activity)
