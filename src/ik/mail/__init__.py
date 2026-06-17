"""Mail (kSuite) commands for ik CLI.

Thin slice in v0.4: `ik mail ls` lists the current user's kSuite
service container, `ik mail info <id>` shows details for one. Mailbox
and message-level commands are follow-up slices.
"""

from __future__ import annotations

import argparse
import json
import sys

from .. import KDriveClient, MyKSuite


def _is_json(args: argparse.Namespace) -> bool:
    return getattr(args, "output", "text") == "json"


def _mail_status(m: MyKSuite) -> str:
    return m.status.lower() if m.status else "unknown"


def _pack_label(m: MyKSuite) -> str:
    return m.pack or f"#{m.pack_id}"


def cmd_mail_ls(args: argparse.Namespace, client: KDriveClient, out=sys.stdout) -> None:
    if _is_json(args):
        out.write(json.dumps([m.to_dict() for m in client.list_my_ksuites()], indent=2) + "\n")
        return

    mail = client.list_my_ksuites()
    if not mail:
        print("No kSuite found.")
        return

    pack_w = max(len(_pack_label(m)) for m in mail)
    print(
        f"  {'ID':>6}  {'PACK':<{pack_w}}  {'STATUS':<10}  {'FREE':<3}  "
        f"{'RENEWAL':<10}  {'TRIAL EXPIRES':<12}"
    )
    for m in mail:
        free = "Yes" if m.is_free else "No"
        trial = m.trial_expiry_at.strftime("%Y-%m-%d") if m.trial_expiry_at else "-"
        renewal = m.has_auto_renew or "-"
        print(
            f"  {m.id:>6}  {_pack_label(m):<{pack_w}}  {_mail_status(m):<10}  {free:<3}  "
            f"{renewal:<10}  {trial:<12}"
        )


def cmd_mail_info(args: argparse.Namespace, client: KDriveClient, out=sys.stdout) -> None:
    m = client.get_my_ksuite(args.mail_id)

    if _is_json(args):
        out.write(json.dumps(m.to_dict(), indent=2) + "\n")
        return

    trial = m.trial_expiry_at.strftime("%Y-%m-%d") if m.trial_expiry_at else "-"
    free = "Yes" if m.is_free else "No"
    print(f"ID:                {m.id}")
    print(f"Pack:              {_pack_label(m)}")
    print(f"Pack ID:           {m.pack_id}")
    print(f"Status:            {_mail_status(m)}")
    print(f"Product:           {m.product or '-'}")
    print(f"Free:              {free}")
    print(f"Mail hosting:      {m.mail or '-'}")
    print(f"Drive hosting:     {m.drive or '-'}")
    print(f"Auto-renew:        {m.has_auto_renew or '-'}")
    print(f"Trial expires at:  {trial}")


def add_mail_commands(
    parser: argparse.ArgumentParser, global_flags: argparse.ArgumentParser
) -> None:
    """Add `ik mail ...` subcommands to the parser."""
    mail_parser = parser.add_parser("mail", help="Mail (kSuite) commands", parents=[global_flags])
    mail_sub = mail_parser.add_subparsers(dest="mail_cmd", required=True)

    # mail ls
    ls = mail_sub.add_parser("ls", help="List current kSuite", parents=[global_flags])
    ls.set_defaults(func=cmd_mail_ls)

    # mail info
    info = mail_sub.add_parser("info", help="Show kSuite details", parents=[global_flags])
    info.add_argument("mail_id", type=int, help="kSuite service ID")
    info.set_defaults(func=cmd_mail_info)
