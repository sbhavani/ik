"""Tests for src/ik/mail/__init__.py — `ik mail ls` and `ik mail info`."""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from ik import KDriveClient, MyKSuite
from ik.mail import cmd_mail_info, cmd_mail_ls


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def make_my_ksuite(
    id: int = 1234,
    pack: str = "kSuite Standard",
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
        assert "Status:            active" in out
        assert "Product:           ksuite" in out
        assert "Free:              No" in out
        assert "Mail hosting:      5678" in out
        assert "Drive hosting:     9012" in out
        assert "Auto-renew:        enabled" in out
        assert "Trial expires at:  2025-01-15" in out

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
