"""Tests for value-object constructors and formatting helpers."""

from __future__ import annotations

from datetime import datetime

import pytest

from ik import Drive, File, MoveOperation, ShareLink, SharedFile
from ik.driver import _format_size


class TestFormatSize:
    @pytest.mark.parametrize(
        "size,expected",
        [
            (0, "0B"),
            (500, "500B"),
            (1024, "1.0K"),
            (1536, "1.5K"),
            (1024**2, "1.0M"),
            (5 * 1024**2, "5.0M"),
            (1024**3, "1.0G"),
            (10 * 1024**3, "10.0G"),
        ],
    )
    def test_boundaries(self, size: int, expected: str) -> None:
        assert _format_size(size) == expected


class TestDriveFromApi:
    def test_full_payload(self, drive_dict: dict) -> None:
        drive = Drive.from_api(drive_dict)
        assert drive.id == 42
        assert drive.name == "My Drive"
        assert drive.size == 10 * 1024**3
        assert drive.used_size == 3 * 1024**3
        assert drive.is_locked is False
        assert drive.has_operation_in_progress is False
        assert drive.created_at == datetime.fromisoformat(drive_dict["created_at"])

    def test_empty_dict_uses_defaults(self) -> None:
        drive = Drive.from_api({})
        assert drive.id == 0
        assert drive.name == "Unnamed"
        assert drive.size == 0
        assert drive.used_size == 0
        assert drive.is_locked is False
        assert drive.has_operation_in_progress is False
        assert drive.created_at is None

    def test_missing_created_at(self, drive_dict: dict) -> None:
        del drive_dict["created_at"]
        drive = Drive.from_api(drive_dict)
        assert drive.created_at is None


class TestFileFromApi:
    def test_full_payload(self, file_dict: dict) -> None:
        f = File.from_api(file_dict)
        assert f.id == 100
        assert f.name == "report.pdf"
        assert f.size == 4096
        assert f.is_directory is False
        assert f.parent_id == 1
        assert f.created_at == datetime.fromisoformat(file_dict["created_at"])
        assert f.modified_at == datetime.fromisoformat(file_dict["modified_at"])
        assert f.mime_type == "application/pdf"

    def test_type_dir_marks_directory(self, file_dict: dict) -> None:
        file_dict["type"] = "dir"
        f = File.from_api(file_dict)
        assert f.is_directory is True

    def test_empty_dict_uses_defaults(self) -> None:
        f = File.from_api({})
        assert f.id == 0
        assert f.name == "?"
        assert f.size == 0
        assert f.is_directory is False
        assert f.parent_id is None
        assert f.created_at is None
        assert f.modified_at is None
        assert f.mime_type is None

    def test_missing_timestamps(self, file_dict: dict) -> None:
        del file_dict["created_at"]
        del file_dict["modified_at"]
        f = File.from_api(file_dict)
        assert f.created_at is None
        assert f.modified_at is None


class TestDriveToDict:
    def test_serializes_all_fields(self) -> None:
        drive = Drive(
            id=1,
            name="Personal",
            size=10 * 1024**3,
            used_size=2 * 1024**3,
            is_locked=False,
            has_operation_in_progress=False,
            created_at=datetime(2024, 1, 2, 3, 4, 5),
        )
        d = drive.to_dict()
        assert d["id"] == 1
        assert d["name"] == "Personal"
        assert d["size"] == 10 * 1024**3
        assert d["used_size"] == 2 * 1024**3
        assert d["is_locked"] is False
        assert d["has_operation_in_progress"] is False
        assert d["created_at"] == "2024-01-02T03:04:05"

    def test_none_datetime(self) -> None:
        drive = Drive(
            id=0,
            name="x",
            size=0,
            used_size=0,
            is_locked=False,
            has_operation_in_progress=False,
            created_at=None,
        )
        assert drive.to_dict()["created_at"] is None


class TestFileToDict:
    def test_serializes_all_fields(self) -> None:
        f = File(
            id=100,
            name="report.pdf",
            size=4096,
            is_directory=False,
            parent_id=1,
            created_at=datetime(2024, 1, 2, 3, 4, 5),
            modified_at=datetime(2024, 1, 3, 4, 5, 6),
            mime_type="application/pdf",
        )
        d = f.to_dict()
        assert d == {
            "id": 100,
            "name": "report.pdf",
            "size": 4096,
            "is_directory": False,
            "parent_id": 1,
            "created_at": "2024-01-02T03:04:05",
            "modified_at": "2024-01-03T04:05:06",
            "mime_type": "application/pdf",
        }

    def test_none_fields(self) -> None:
        f = File(
            id=1,
            name="x",
            size=0,
            is_directory=False,
            parent_id=None,
            created_at=None,
            modified_at=None,
            mime_type=None,
        )
        d = f.to_dict()
        assert d["parent_id"] is None
        assert d["created_at"] is None
        assert d["modified_at"] is None
        assert d["mime_type"] is None


class TestMoveOperationToDict:
    def test_serializes(self) -> None:
        op = MoveOperation(cancel_id="abc-123", valid_until=datetime(2024, 6, 1, 12, 0, 0))
        d = op.to_dict()
        assert d == {"cancel_id": "abc-123", "valid_until": "2024-06-01T12:00:00"}

    def test_none_valid_until(self) -> None:
        op = MoveOperation(cancel_id="x", valid_until=None)
        assert op.to_dict() == {"cancel_id": "x", "valid_until": None}


class TestShareLinkToDict:
    def test_nested_capabilities(self) -> None:
        link = ShareLink(
            url="https://example.com/x",
            file_id=42,
            right="public",
            valid_until=datetime(2024, 12, 31, 23, 59, 59),
            can_download=True,
            can_edit=False,
            can_see_info=False,
            can_comment=False,
            can_request_access=False,
            can_see_stats=False,
            access_blocked=False,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 2, 2),
            created_by=7,
            views=3,
        )
        d = link.to_dict()
        assert d["url"] == "https://example.com/x"
        assert d["file_id"] == 42
        assert d["right"] == "public"
        assert d["valid_until"] == "2024-12-31T23:59:59"
        assert d["capabilities"] == {
            "can_download": True,
            "can_edit": False,
            "can_see_info": False,
            "can_comment": False,
            "can_request_access": False,
            "can_see_stats": False,
        }
        assert d["access_blocked"] is False
        assert d["created_at"] == "2024-01-01T00:00:00"
        assert d["updated_at"] == "2024-02-02T00:00:00"
        assert d["created_by"] == 7
        assert d["views"] == 3


class TestSharedFileToDict:
    def test_serializes(self) -> None:
        sf = SharedFile(id=5, name="doc.pdf", update_at=datetime(2024, 3, 4, 5, 6, 7), users=2)
        d = sf.to_dict()
        assert d == {
            "id": 5,
            "name": "doc.pdf",
            "update_at": "2024-03-04T05:06:07",
            "users": 2,
        }

    def test_none_update_at(self) -> None:
        sf = SharedFile(id=1, name="x", update_at=None, users=0)
        assert sf.to_dict()["update_at"] is None
