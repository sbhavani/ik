"""Mail (kSuite) commands for ik CLI.

v0.4 thin slice: `ik mail ls` / `ik mail info` for the kSuite service
container. v0.4 mailbox layer: `ik mail mailboxes` (list folders),
`ik mail messages` (list message metadata), `ik mail message` (read
full body + attachments). Send / folder-mgmt / search-across-mailboxes
are follow-up slices.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import KDriveClient, MessageBody, MyKSuite


def _is_json(args: argparse.Namespace) -> bool:
    return getattr(args, "output", "text") == "json"


def _mail_status(m: MyKSuite) -> str:
    return m.status.lower() if m.status else "unknown"


def _pack_label(m: MyKSuite) -> str:
    return m.pack or f"#{m.pack_id}"


def _format_size(n: int) -> str:
    """Tiny size formatter: 1234 -> '1.2K'. Mirrors `_format_size` in driver."""
    if n < 1024:
        return f"{n}B"
    if n < 1024**2:
        return f"{n / 1024:.1f}K"
    if n < 1024**3:
        return f"{n / 1024**2:.1f}M"
    return f"{n / 1024**3:.1f}G"


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


def _require_mail_hosting_id(args: argparse.Namespace) -> int:
    hosting_id = getattr(args, "mail_hosting_id", None)
    if hosting_id is None:
        sys.exit("Error: --mail-hosting <id> required (or set `default_mail` in your profile).")
    return hosting_id


def cmd_mail_mailboxes(args: argparse.Namespace, client: KDriveClient, out=None) -> None:
    """List mailbox folders inside a mail hosting."""
    if out is None:
        out = sys.stdout
    hosting_id = _require_mail_hosting_id(args)

    if _is_json(args):
        boxes = client.list_mailboxes(hosting_id)
        out.write(json.dumps([b.to_dict() for b in boxes], indent=2) + "\n")
        return

    boxes = client.list_mailboxes(hosting_id)
    if not boxes:
        out.write(f"No mailboxes found in mail hosting {hosting_id}.\n")
        return

    name_w = max(len(b.name) for b in boxes)
    parent_w = max((len(str(b.parent_id)) for b in boxes if b.parent_id is not None), default=1)
    out.write(
        f"  {'ID':>6}  {'NAME':<{name_w}}  {'PARENT':<{parent_w}}  {'UNREAD':>6}  {'MESSAGES':>8}\n"
    )
    for b in boxes:
        parent = str(b.parent_id) if b.parent_id is not None else "-"
        out.write(
            f"  {b.id:>6}  {b.name:<{name_w}}  {parent:<{parent_w}}  "
            f"{b.unread_count:>6}  {b.message_count:>8}\n"
        )


def cmd_mail_messages(args: argparse.Namespace, client: KDriveClient, out=None) -> None:
    """List messages in a mailbox (metadata only)."""
    if out is None:
        out = sys.stdout
    hosting_id = _require_mail_hosting_id(args)
    mailbox_id: int = args.mailbox_id

    msgs = list(client.list_messages(hosting_id, mailbox_id))

    if _is_json(args):
        out.write(json.dumps([m.to_dict() for m in msgs], indent=2) + "\n")
        return

    if not msgs:
        out.write(f"No messages in mailbox {mailbox_id}.\n")
        return

    # Truncate subjects wider than 50 chars so the table stays readable.
    SUBJECT_W = 50
    from_w = max(min(30, max(len(m.from_) for m in msgs)), 12)
    out.write(
        f"  {'ID':>6}  {'FROM':<{from_w}}  {'SUBJECT':<{SUBJECT_W}}  "
        f"{'DATE':<10}  {'ATTACH':>6}  {'SIZE':>8}\n"
    )
    for m in msgs:
        subj = m.subject if len(m.subject) <= SUBJECT_W else m.subject[: SUBJECT_W - 1] + "…"
        date = m.date.strftime("%Y-%m-%d") if m.date else "-"
        attach = "yes" if m.has_attachments else "-"
        size = _format_size(m.size)
        out.write(
            f"  {m.id:>6}  {m.from_:<{from_w}}  {subj:<{SUBJECT_W}}  "
            f"{date:<10}  {attach:>6}  {size:>8}\n"
        )


def cmd_mail_message(args: argparse.Namespace, client: KDriveClient, out=None) -> None:
    """Read one message — headers, body, attachments."""
    if out is None:
        out = sys.stdout
    hosting_id = _require_mail_hosting_id(args)
    msg_id: int = args.msg_id

    body = client.get_message(hosting_id, args.mailbox_id, msg_id)

    if getattr(args, "save_attachment", None) is not None:
        _save_attachment(body, args.save_attachment, args.local, out)
        return

    if _is_json(args):
        out.write(json.dumps(body.to_dict(), indent=2) + "\n")
        return

    if getattr(args, "raw", False):
        out.buffer.write(body.raw_mime)
        if not body.raw_mime.endswith(b"\n"):
            out.write("\n")
        return

    out.write(f"From:    {body.from_}\n")
    out.write(f"To:      {', '.join(body.to)}\n")
    if body.cc:
        out.write(f"Cc:      {', '.join(body.cc)}\n")
    out.write(f"Subject: {body.subject}\n")
    if body.date:
        out.write(f"Date:    {body.date.isoformat()}\n")
    out.write("\n")

    if getattr(args, "html", False):
        out.write(body.body_html or "")
    else:
        out.write(body.body_text or "")

    if body.attachments:
        out.write("\n")
        out.write(f"Attachments ({len(body.attachments)}):\n")
        for i, a in enumerate(body.attachments, 1):
            out.write(f"  {i}. {a.filename}  ({a.mime_type}, {_format_size(a.size)})\n")


def _save_attachment(body: MessageBody, index: int, local: str, out) -> None:
    """Decode and write attachment `index` (1-based) to `local`."""
    if not (1 <= index <= len(body.attachments)):
        sys.exit(f"Error: attachment index {index} out of range (1..{len(body.attachments)}).")
    target = body.attachments[index - 1]

    import email as _email
    from email.policy import default as _default_policy

    msg = _email.message_from_bytes(body.raw_mime, policy=_default_policy)
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" and (
            part.get_filename() == target.filename
        ):
            payload = part.get_payload(decode=True) or b""
            path = Path(local).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            out.write(f"Saved {target.filename} ({_format_size(len(payload))}) to {path}\n")
            return
    sys.exit(f"Error: attachment {target.filename} not found in message body.")


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

    # mail mailboxes
    boxes = mail_sub.add_parser("mailboxes", help="List mailbox folders", parents=[global_flags])
    boxes.add_argument(
        "mail_hosting_id",
        type=int,
        nargs="?",
        default=None,
        help="Mail hosting ID (defaults to profile's default_mail)",
    )
    boxes.set_defaults(func=cmd_mail_mailboxes)

    # mail messages
    msgs = mail_sub.add_parser(
        "messages", help="List messages in a mailbox", parents=[global_flags]
    )
    msgs.add_argument(
        "mail_hosting_id",
        type=int,
        nargs="?",
        default=None,
        help="Mail hosting ID (defaults to profile's default_mail)",
    )
    msgs.add_argument("mailbox_id", type=int, help="Mailbox / folder ID")
    msgs.set_defaults(func=cmd_mail_messages)

    # mail message
    msg = mail_sub.add_parser("message", help="Read one message", parents=[global_flags])
    msg.add_argument(
        "mail_hosting_id",
        type=int,
        nargs="?",
        default=None,
        help="Mail hosting ID (defaults to profile's default_mail)",
    )
    msg.add_argument("mailbox_id", type=int, help="Mailbox / folder ID")
    msg.add_argument("msg_id", type=int, help="Message ID")
    msg.add_argument(
        "--html",
        action="store_true",
        help="Print the HTML body instead of plain text",
    )
    msg.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw MIME source (for debugging / piping)",
    )
    msg.add_argument(
        "--save-attachment",
        type=int,
        default=None,
        metavar="N",
        help="Save attachment N (1-based) instead of printing the message",
    )
    msg.add_argument(
        "--local",
        default=None,
        metavar="PATH",
        help="Local path to write the attachment to (with --save-attachment)",
    )
    msg.set_defaults(func=cmd_mail_message)
