"""Tests for src/ik/mail/__init__.py — `ik mail ls` and `ik mail info`."""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from ik import KDriveClient, Mailbox, Message, MessageBody, MyKSuite
from ik.mail import (
    cmd_mail_info,
    cmd_mail_ls,
    cmd_mail_mailboxes,
    cmd_mail_message,
    cmd_mail_messages,
)
from tests.conftest import FIXTURES_DIR


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def make_my_ksuite(
    id: int = 1234,
    pack: str = "kSuite Standard",
    pack_id: int = 7,
    status: str = "active",
    product: str = "ksuite",
    is_free: bool = False,
    drive: str | None = "9012",
    mail: str | None = "5678",
    has_auto_renew: str = "enabled",
    trial_expiry_at: datetime | None = datetime(2025, 1, 15),
) -> MyKSuite:
    return MyKSuite(
        id=id,
        pack=pack,
        pack_id=pack_id,
        status=status,
        product=product,
        is_free=is_free,
        drive=drive,
        mail=mail,
        has_auto_renew=has_auto_renew,
        trial_expiry_at=trial_expiry_at,
    )


# ── cmd_mail_ls ───────────────────────────────────────────────────────


class TestCmdMailLs:
    def test_no_ksuite(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = []

        cmd_mail_ls(ns(output="text"), client)

        assert capsys.readouterr().out == "No kSuite found.\n"

    def test_lists_ksuite(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite()]

        cmd_mail_ls(ns(output="text"), client)

        out = capsys.readouterr().out
        assert "1234" in out
        assert "kSuite Standard" in out
        assert "active" in out
        assert "No" in out  # is_free=False
        assert "enabled" in out
        assert "2025-01-15" in out

    def test_status_passed_through(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(status="SUSPENDED")]

        cmd_mail_ls(ns(output="text"), client)

        assert "suspended" in capsys.readouterr().out

    def test_trial_expiry_rendered(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(trial_expiry_at=datetime(2026, 7, 4))]

        cmd_mail_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        data_line = [ln for ln in out_lines if "1234" in ln][0]
        assert "2026-07-04" in data_line

    def test_null_trial_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(trial_expiry_at=None)]

        cmd_mail_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        data_line = [ln for ln in out_lines if "1234" in ln][0]
        assert " - " in f"  {data_line}  "

    def test_is_free_renders_yes(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(is_free=True)]

        cmd_mail_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        data_line = [ln for ln in out_lines if "1234" in ln][0]
        assert "Yes" in data_line

    def test_dynamic_pack_column_width(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [
            make_my_ksuite(id=1, pack="Short"),
            make_my_ksuite(id=2, pack="A Much Longer Pack Name"),
        ]

        cmd_mail_ls(ns(output="text"), client)

        out = capsys.readouterr().out
        # Header should be at least as wide as the longest pack
        header = [ln for ln in out.splitlines() if "PACK" in ln][0]
        assert len(header) >= len("A Much Longer Pack Name")

    def test_empty_pack_falls_back_to_pack_id(self, capsys: pytest.CaptureFixture) -> None:
        # Mirrors the live API response for a free kSuite: no `pack`
        # string, just `pack_id`. Text view should show "#1" not "Unnamed".
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(id=492079, pack="", pack_id=1)]

        cmd_mail_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        data_line = [ln for ln in out_lines if "492079" in ln][0]
        assert "#1" in data_line
        assert "Unnamed" not in data_line

    def test_null_renewal_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite(has_auto_renew="")]

        cmd_mail_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        data_line = [ln for ln in out_lines if "1234" in ln][0]
        # Renewal column should render "-" when has_auto_renew is empty
        assert "  -  " in f"  {data_line}  "

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = [make_my_ksuite()]
        out = io.StringIO()

        cmd_mail_ls(ns(output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == 1234
        assert parsed[0]["pack"] == "kSuite Standard"
        assert parsed[0]["pack_id"] == 7
        assert parsed[0]["is_free"] is False

    def test_json_output_empty(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_my_ksuites.return_value = []
        out = io.StringIO()

        cmd_mail_ls(ns(output="json"), client, out=out)

        assert json.loads(out.getvalue()) == []


# ── cmd_mail_info ─────────────────────────────────────────────────────


class TestCmdMailInfo:
    def test_prints_all_fields(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite()

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        out = capsys.readouterr().out
        assert "ID:                1234" in out
        assert "Pack:              kSuite Standard" in out
        assert "Pack ID:           7" in out
        assert "Status:            active" in out
        assert "Product:           ksuite" in out
        assert "Free:              No" in out
        assert "Mail hosting:      5678" in out
        assert "Drive hosting:     9012" in out
        assert "Auto-renew:        enabled" in out
        assert "Trial expires at:  2025-01-15" in out

    def test_empty_pack_renders_pack_id(self, capsys: pytest.CaptureFixture) -> None:
        # Mirrors the live API response for a free kSuite: no `pack`
        # string, just `pack_id: 1`. Text view should fall back to "#1".
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(
            pack="", pack_id=1, drive=None, mail=None
        )

        cmd_mail_info(ns(mail_id=492079, output="text"), client)

        out = capsys.readouterr().out
        assert "Pack:              #1" in out
        assert "Pack ID:           1" in out
        assert "Mail hosting:      -" in out
        assert "Drive hosting:     -" in out

    def test_null_drive_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(drive=None)

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Drive hosting:     -" in capsys.readouterr().out

    def test_null_mail_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(mail=None)

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Mail hosting:      -" in capsys.readouterr().out

    def test_null_trial_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(trial_expiry_at=None)

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Trial expires at:  -" in capsys.readouterr().out

    def test_status_lowercased(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(status="SUSPENDED")

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Status:            suspended" in capsys.readouterr().out

    def test_empty_status_renders_unknown(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(status="")

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Status:            unknown" in capsys.readouterr().out

    def test_is_free_renders_yes(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite(is_free=True)

        cmd_mail_info(ns(mail_id=1234, output="text"), client)

        assert "Free:              Yes" in capsys.readouterr().out

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite()
        out = io.StringIO()

        cmd_mail_info(ns(mail_id=1234, output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert parsed["id"] == 1234
        assert parsed["pack"] == "kSuite Standard"
        assert parsed["trial_expiry_at"] == "2025-01-15T00:00:00"

    def test_calls_get_my_ksuite_with_id(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_my_ksuite.return_value = make_my_ksuite()

        cmd_mail_info(ns(mail_id=42, output="text"), client)

        client.get_my_ksuite.assert_called_once_with(42)


# ── cmd_mail_mailboxes ────────────────────────────────────────────────


def make_mailbox(
    id: int = 1,
    name: str = "INBOX",
    parent_id: int | None = None,
    unread_count: int = 3,
    message_count: int = 42,
) -> Mailbox:
    return Mailbox(
        id=id,
        name=name,
        parent_id=parent_id,
        unread_count=unread_count,
        message_count=message_count,
    )


class TestCmdMailMailboxes:
    def test_no_hosting_id_errors(self) -> None:
        client = Mock(spec=KDriveClient)
        with pytest.raises(SystemExit, match="mail-hosting"):
            cmd_mail_mailboxes(ns(mail_hosting_id=None, output="text"), client)

    def test_lists_mailboxes(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_mailboxes.return_value = [
            make_mailbox(id=1, name="INBOX", unread_count=3, message_count=42),
            make_mailbox(id=2, name="Sent", unread_count=0, message_count=18),
            make_mailbox(id=3, name="Drafts", unread_count=0, message_count=1),
        ]

        cmd_mail_mailboxes(ns(mail_hosting_id=99, output="text"), client)

        out = capsys.readouterr().out
        assert "INBOX" in out
        assert "Sent" in out
        assert "Drafts" in out
        assert "3" in out  # unread
        assert "42" in out  # total

    def test_nested_folder_shows_parent(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_mailboxes.return_value = [
            make_mailbox(id=1, name="INBOX"),
            make_mailbox(id=4, name="Project X", parent_id=1),
        ]

        cmd_mail_mailboxes(ns(mail_hosting_id=99, output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        proj_line = [ln for ln in out_lines if "Project X" in ln][0]
        assert "1" in proj_line

    def test_no_mailboxes(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_mailboxes.return_value = []

        cmd_mail_mailboxes(ns(mail_hosting_id=99, output="text"), client)

        out = capsys.readouterr().out
        assert "No mailboxes" in out

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_mailboxes.return_value = [make_mailbox()]
        out = io.StringIO()

        cmd_mail_mailboxes(ns(mail_hosting_id=99, output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert isinstance(parsed, list)
        assert parsed[0]["name"] == "INBOX"
        assert parsed[0]["unread_count"] == 3


# ── cmd_mail_messages ─────────────────────────────────────────────────


def make_message(
    id: int = 100,
    mailbox_id: int = 1,
    from_: str = "alice@example.com",
    to: list[str] | None = None,
    cc: list[str] | None = None,
    subject: str = "Re: Q3 plan",
    date: datetime | None = datetime(2026, 6, 12, 9, 14, 23),
    has_attachments: bool = False,
    size: int = 12400,
    snippet: str | None = "Sounds good to me...",
) -> Message:
    return Message(
        id=id,
        mailbox_id=mailbox_id,
        from_=from_,
        to=to if to is not None else ["bob@example.com"],
        cc=cc if cc is not None else [],
        subject=subject,
        date=date,
        has_attachments=has_attachments,
        size=size,
        snippet=snippet,
    )


class TestCmdMailMessages:
    def test_no_hosting_id_errors(self) -> None:
        client = Mock(spec=KDriveClient)
        with pytest.raises(SystemExit, match="mail-hosting"):
            cmd_mail_messages(ns(mail_hosting_id=None, mailbox_id=1, output="text"), client)

    def test_lists_messages(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_messages.return_value = iter(
            [
                make_message(id=1, subject="short"),
                make_message(id=2, subject="Invoice #4521", has_attachments=True, size=48_000),
            ]
        )

        cmd_mail_messages(ns(mail_hosting_id=99, mailbox_id=1, output="text"), client)

        out = capsys.readouterr().out
        assert "alice@example.com" in out
        assert "Invoice #4521" in out
        assert "yes" in out  # attach indicator

    def test_truncates_long_subject(self, capsys: pytest.CaptureFixture) -> None:
        long_subj = "x" * 80
        client = Mock(spec=KDriveClient)
        client.list_messages.return_value = iter([make_message(id=1, subject=long_subj)])

        cmd_mail_messages(ns(mail_hosting_id=99, mailbox_id=1, output="text"), client)

        out = capsys.readouterr().out
        # Truncated to 50 chars (49 + ellipsis)
        assert "…" in out
        assert long_subj not in out  # not printed in full

    def test_no_messages(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_messages.return_value = iter([])

        cmd_mail_messages(ns(mail_hosting_id=99, mailbox_id=1, output="text"), client)

        out = capsys.readouterr().out
        assert "No messages" in out

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_messages.return_value = iter([make_message()])
        out = io.StringIO()

        cmd_mail_messages(ns(mail_hosting_id=99, mailbox_id=1, output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert isinstance(parsed, list)
        assert parsed[0]["from"] == "alice@example.com"
        assert parsed[0]["has_attachments"] is False


# ── cmd_mail_message ─────────────────────────────────────────────────


def _load_body(name: str, msg_id: int = 42, mailbox_id: int = 1) -> MessageBody:
    return MessageBody.from_mime(
        (FIXTURES_DIR / "mail" / name).read_bytes(),
        mailbox_id=mailbox_id,
        msg_id=msg_id,
    )


class TestCmdMailMessage:
    def test_prints_headers_and_body(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("plain.eml")

        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="text",
                html=False,
                raw=False,
                save_attachment=None,
                local=None,
            ),
            client,
        )

        out = capsys.readouterr().out
        assert "From:    alice@example.com" in out
        assert "To:      bob@example.com" in out
        assert "Subject: Quick question" in out
        assert "Are we still on for the 3pm?" in out
        assert "Attachments" not in out  # plain.eml has none

    def test_html_switches_body(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("multipart.eml")

        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="text",
                html=True,
                raw=False,
                save_attachment=None,
                local=None,
            ),
            client,
        )

        out = capsys.readouterr().out
        assert "<b>message</b>" in out
        # Plain version should NOT be the body when --html is set
        assert "Plain version of the message" not in out

    def test_raw_prints_mime(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        body = _load_body("plain.eml")
        client.get_message.return_value = body

        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="text",
                html=False,
                raw=True,
                save_attachment=None,
                local=None,
            ),
            client,
        )

        captured = capsys.readouterr()
        assert b"From: alice@example.com" in captured.out.encode()

    def test_prints_attachment_list(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("with_attachment.eml")

        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="text",
                html=False,
                raw=False,
                save_attachment=None,
                local=None,
            ),
            client,
        )

        out = capsys.readouterr().out
        assert "Attachments (1):" in out
        assert "report.pdf" in out
        assert "application/pdf" in out

    def test_save_attachment_writes_file(self, tmp_path, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("with_attachment.eml")

        target = tmp_path / "out.pdf"
        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="text",
                html=False,
                raw=False,
                save_attachment=1,
                local=str(target),
            ),
            client,
        )

        assert target.exists()
        assert target.stat().st_size > 0
        out = capsys.readouterr().out
        assert "Saved report.pdf" in out

    def test_save_attachment_out_of_range(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("with_attachment.eml")

        with pytest.raises(SystemExit, match="out of range"):
            cmd_mail_message(
                ns(
                    mail_hosting_id=99,
                    mailbox_id=1,
                    msg_id=42,
                    output="text",
                    html=False,
                    raw=False,
                    save_attachment=5,
                    local="/tmp/x",
                ),
                client,
            )

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_message.return_value = _load_body("plain.eml")
        out = io.StringIO()

        cmd_mail_message(
            ns(
                mail_hosting_id=99,
                mailbox_id=1,
                msg_id=42,
                output="json",
                html=False,
                raw=False,
                save_attachment=None,
                local=None,
            ),
            client,
            out=out,
        )

        parsed = json.loads(out.getvalue())
        assert parsed["from"] == "alice@example.com"
        assert parsed["subject"] == "Quick question"
        assert parsed["attachments"] == []


# ── _format_size branches ──────────────────────────────────────────────


class TestFormatSize:
    def test_bytes(self) -> None:
        from ik.mail import _format_size

        assert _format_size(0) == "0B"
        assert _format_size(512) == "512B"
        assert _format_size(1023) == "1023B"

    def test_kilobytes(self) -> None:
        from ik.mail import _format_size

        assert _format_size(1024) == "1.0K"
        assert _format_size(1536) == "1.5K"
        assert _format_size(1024 * 1024 - 1) == "1024.0K"

    def test_megabytes(self) -> None:
        from ik.mail import _format_size

        assert _format_size(1024**2) == "1.0M"
        assert _format_size(int(2.5 * 1024**2)) == "2.5M"

    def test_gigabytes(self) -> None:
        from ik.mail import _format_size

        assert _format_size(1024**3) == "1.0G"
        assert _format_size(3 * 1024**3) == "3.0G"


# ── _save_attachment error paths ──────────────────────────────────────


class TestSaveAttachmentErrors:
    def test_attachment_not_found_in_mime_exits(self, tmp_path) -> None:
        body = _load_body("with_attachment.eml")
        body.attachments[0].filename = "missing-from-mime.pdf"

        with pytest.raises(SystemExit) as exc_info:
            from ik.mail import _save_attachment

            _save_attachment(body, 1, str(tmp_path / "x"), io.StringIO())

        assert "missing-from-mime.pdf" in str(exc_info.value)
        assert "not found" in str(exc_info.value)
