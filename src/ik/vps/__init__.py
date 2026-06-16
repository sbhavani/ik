"""VPS (Public Cloud) commands for ik CLI.

Thin slice in v0.4: `ik vps ls` lists VPS Cloud service containers,
`ik vps info <id>` shows details for one. Mutations (start/stop/reboot,
project management, instance management) are follow-up slices.
"""

from __future__ import annotations

import argparse
import json
import sys

from .. import KDriveClient, VPS


def _is_json(args: argparse.Namespace) -> bool:
    return getattr(args, "output", "text") == "json"


def _vps_status(v: VPS) -> str:
    """Render a one-word status badge for the text list view."""
    if v.is_locked:
        return "locked"
    if v.has_maintenance:
        return "maintenance"
    if v.has_operation_in_progress:
        return "busy"
    return "active"


def cmd_vps_ls(args: argparse.Namespace, client: KDriveClient, out=sys.stdout) -> None:
    if _is_json(args):
        out.write(json.dumps([v.to_dict() for v in client.list_public_clouds()], indent=2) + "\n")
        return

    vpses = client.list_public_clouds()
    if not vpses:
        print("No VPS Cloud services found.")
        return

    name_w = max(len(v.name) for v in vpses)
    print(
        f"  {'ID':>6}  {'NAME':<{name_w}}  {'STATUS':<11}  {'PROJECTS':>8}  {'PRICE':>8}  CREATED"
    )
    for v in vpses:
        price = f"{v.price:.2f}" if v.price is not None else "-"
        created = v.created_at.strftime("%Y-%m-%d") if v.created_at else "-"
        print(
            f"  {v.id:>6}  {v.name:<{name_w}}  {_vps_status(v):<11}  {v.project_count:>8}  {price:>8}  {created}"
        )


def cmd_vps_info(args: argparse.Namespace, client: KDriveClient, out=sys.stdout) -> None:
    v = client.get_public_cloud(args.vps_id)

    if _is_json(args):
        out.write(json.dumps(v.to_dict(), indent=2) + "\n")
        return

    created = v.created_at.isoformat() if v.created_at else "-"
    expired = v.expired_at.isoformat() if v.expired_at else "-"
    print(f"ID:                  {v.id}")
    print(f"Name:                {v.name}")
    if v.description:
        print(f"Description:         {v.description}")
    print(f"Status:              {_vps_status(v)}")
    print(f"Locked:              {v.is_locked}")
    print(f"Maintenance:         {v.has_maintenance}")
    print(f"Operation in prog.:  {v.has_operation_in_progress}")
    print(f"Projects:            {v.project_count}")
    print(f"Price:               {v.price if v.price is not None else '-'}")
    print(f"Created at:          {created}")
    print(f"Expired at:          {expired}")


def add_vps_commands(
    parser: argparse.ArgumentParser, global_flags: argparse.ArgumentParser
) -> None:
    """Add `ik vps ...` subcommands to the parser."""
    vps_parser = parser.add_parser("vps", help="VPS Cloud commands", parents=[global_flags])
    vps_sub = vps_parser.add_subparsers(dest="vps_cmd", required=True)

    # vps ls
    ls = vps_sub.add_parser("ls", help="List VPS Cloud services", parents=[global_flags])
    ls.set_defaults(func=cmd_vps_ls)

    # vps info
    info = vps_sub.add_parser("info", help="Show VPS Cloud service details", parents=[global_flags])
    info.add_argument("vps_id", type=int, help="VPS Cloud service ID")
    info.set_defaults(func=cmd_vps_info)
