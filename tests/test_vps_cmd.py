"""Tests for src/ik/vps/__init__.py — `ik vps ls` and `ik vps info`."""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from ik import KDriveClient, VPS
from ik.vps import cmd_vps_info, cmd_vps_ls


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def make_vps(
    id: int = 1001,
    name: str = "My VPS Cloud",
    description: str = "Production environment",
    is_locked: bool = False,
    has_maintenance: bool = False,
    has_operation_in_progress: bool = False,
    project_count: int = 3,
    price: float | None = 12.0,
    created_at: datetime | None = datetime(2024, 1, 15, 10, 30, 0),
    expired_at: datetime | None = None,
) -> VPS:
    return VPS(
        id=id,
        name=name,
        description=description,
        is_locked=is_locked,
        has_maintenance=has_maintenance,
        has_operation_in_progress=has_operation_in_progress,
        project_count=project_count,
        price=price,
        created_at=created_at,
        expired_at=expired_at,
    )


# ── cmd_vps_ls ────────────────────────────────────────────────────────


class TestCmdVpsLs:
    def test_no_vpses(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = []

        cmd_vps_ls(ns(output="text"), client)

        assert capsys.readouterr().out == "No VPS Cloud services found.\n"

    def test_lists_vpses(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [
            make_vps(id=1, name="Alpha", project_count=2, price=5.0),
            make_vps(id=2, name="Bravo", project_count=4, price=15.0),
        ]

        cmd_vps_ls(ns(output="text"), client)

        out = capsys.readouterr().out
        assert "1" in out and "Alpha" in out and "2" in out and "Bravo" in out
        assert "5.00" in out and "15.00" in out
        assert "active" in out  # status badge for non-locked, non-maintenance

    def test_status_badge_locked(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [make_vps(is_locked=True)]

        cmd_vps_ls(ns(output="text"), client)

        assert "locked" in capsys.readouterr().out

    def test_status_badge_maintenance(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [make_vps(has_maintenance=True)]

        cmd_vps_ls(ns(output="text"), client)

        assert "maintenance" in capsys.readouterr().out

    def test_status_badge_busy(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [make_vps(has_operation_in_progress=True)]

        cmd_vps_ls(ns(output="text"), client)

        assert "busy" in capsys.readouterr().out

    def test_price_none_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [make_vps(price=None)]

        cmd_vps_ls(ns(output="text"), client)

        out_lines = capsys.readouterr().out.splitlines()
        # Find the row for our vps and check the price column is "-"
        data_line = [ln for ln in out_lines if "1001" in ln][0]
        assert "  -  " in f"  {data_line}  "

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_public_clouds.return_value = [make_vps()]
        out = io.StringIO()

        cmd_vps_ls(ns(output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == 1001
        assert parsed[0]["name"] == "My VPS Cloud"
        assert parsed[0]["project_count"] == 3


# ── cmd_vps_info ──────────────────────────────────────────────────────


class TestCmdVpsInfo:
    def test_prints_all_fields(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps()

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        out = capsys.readouterr().out
        assert "ID:                  1001" in out
        assert "Name:                My VPS Cloud" in out
        assert "Description:         Production environment" in out
        assert "Status:              active" in out
        assert "Projects:            3" in out
        assert "Price:               12.0" in out
        assert "Created at:          2024-01-15T10:30:00" in out

    def test_skips_description_when_empty(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(description="")

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        out = capsys.readouterr().out
        assert "Description:" not in out

    def test_status_locked(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(is_locked=True)

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        assert "Status:              locked" in capsys.readouterr().out

    def test_status_maintenance(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(has_maintenance=True)

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        assert "Status:              maintenance" in capsys.readouterr().out

    def test_status_busy(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(has_operation_in_progress=True)

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        assert "Status:              busy" in capsys.readouterr().out

    def test_expired_at_rendered(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(expired_at=datetime(2025, 1, 1))

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        assert "Expired at:          2025-01-01T00:00:00" in capsys.readouterr().out

    def test_price_none_renders_dash(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps(price=None)

        cmd_vps_info(ns(vps_id=1001, output="text"), client)

        assert "Price:               -" in capsys.readouterr().out

    def test_json_output(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps()
        out = io.StringIO()

        cmd_vps_info(ns(vps_id=1001, output="json"), client, out=out)

        parsed = json.loads(out.getvalue())
        assert parsed["id"] == 1001
        assert parsed["name"] == "My VPS Cloud"
        assert parsed["project_count"] == 3

    def test_calls_get_public_cloud_with_id(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.get_public_cloud.return_value = make_vps()

        cmd_vps_info(ns(vps_id=42, output="text"), client)

        client.get_public_cloud.assert_called_once_with(42)
