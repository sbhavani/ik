"""Tests for value-object constructors and formatting helpers."""

from __future__ import annotations

from datetime import datetime

import pytest

from ik import Drive, File
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
