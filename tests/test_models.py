"""Tests for value-object constructors and formatting helpers."""

from __future__ import annotations

from datetime import datetime

import pytest

from ik import Activity, Drive, File, MoveOperation, MyKSuite, ShareLink, SharedFile, VPS
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


class TestActivityToDict:
    def test_serializes_all_fields(self) -> None:
        a = Activity(
            id=42,
            created_at=datetime(2024, 1, 2, 3, 4, 5),
            action="file_mv",
            new_path="/Photos/2024/img.jpg",
            old_path="/Photos/img.jpg",
            file_id=999,
            user_id=7,
        )
        d = a.to_dict()
        assert d == {
            "id": 42,
            "created_at": "2024-01-02T03:04:05",
            "action": "file_mv",
            "new_path": "/Photos/2024/img.jpg",
            "old_path": "/Photos/img.jpg",
            "file_id": 999,
            "user_id": 7,
        }

    def test_none_fields(self) -> None:
        a = Activity(
            id=1,
            created_at=None,
            action="",
            new_path="",
            old_path="",
            file_id=None,
            user_id=None,
        )
        d = a.to_dict()
        assert d["created_at"] is None
        assert d["file_id"] is None
        assert d["user_id"] is None


class TestVPSFromApi:
    def test_full_payload(self, vps_dict: dict) -> None:
        from datetime import datetime

        v = VPS.from_api(vps_dict)
        assert v.id == 1001
        assert v.name == "My VPS Cloud"
        assert v.description == "Production environment"
        assert v.is_locked is False
        assert v.has_maintenance is False
        assert v.has_operation_in_progress is False
        assert v.project_count == 3
        assert v.price == 12.0
        # from_api uses local time (matches Activity/SharedFile/ShareLink pattern).
        assert v.created_at == datetime.fromtimestamp(1705314600)
        assert v.expired_at is None

    def test_falls_back_to_internal_name(self, vps_dict: dict) -> None:
        del vps_dict["customer_name"]
        vps_dict["internal_name"] = "vps-prod-01"
        v = VPS.from_api(vps_dict)
        assert v.name == "vps-prod-01"

    def test_empty_dict_uses_defaults(self) -> None:
        v = VPS.from_api({})
        assert v.id == 0
        assert v.name == "Unnamed"
        assert v.description == ""
        assert v.is_locked is False
        assert v.project_count == 0
        assert v.price is None
        assert v.created_at is None
        assert v.expired_at is None

    def test_missing_public_cloud_subobject(self, vps_dict: dict) -> None:
        del vps_dict["public_cloud"]
        v = VPS.from_api(vps_dict)
        assert v.project_count == 0
        assert v.price is None


class TestVPSToDict:
    def test_serializes_all_fields(self) -> None:
        from datetime import datetime

        v = VPS(
            id=1,
            name="vps",
            description="d",
            is_locked=False,
            has_maintenance=False,
            has_operation_in_progress=True,
            project_count=5,
            price=9.99,
            created_at=datetime(2024, 1, 2, 3, 4, 5),
            expired_at=None,
        )
        d = v.to_dict()
        assert d == {
            "id": 1,
            "name": "vps",
            "description": "d",
            "is_locked": False,
            "has_maintenance": False,
            "has_operation_in_progress": True,
            "project_count": 5,
            "price": 9.99,
            "created_at": "2024-01-02T03:04:05",
            "expired_at": None,
        }


class TestMyKSuiteFromApi:
    def test_full_payload(self, my_ksuite_dict: dict) -> None:
        from datetime import datetime

        m = MyKSuite.from_api(my_ksuite_dict)
        assert m.id == 1234
        assert m.pack == "kSuite Standard"
        assert m.status == "active"
        assert m.product == "ksuite"
        assert m.is_free is False
        assert m.drive == "9012"
        assert m.mail == "5678"
        assert m.has_auto_renew == "enabled"
        assert m.trial_expiry_at == datetime.fromtimestamp(1736899200)

    def test_empty_dict_uses_defaults(self) -> None:
        m = MyKSuite.from_api({})
        assert m.id == 0
        assert m.pack == "Unnamed"
        assert m.status == "Unknown"
        assert m.product == ""
        assert m.is_free is False
        assert m.drive is None
        assert m.mail is None
        assert m.has_auto_renew == ""
        assert m.trial_expiry_at is None

    def test_null_trial_expiry_at_is_none(self, my_ksuite_dict: dict) -> None:
        my_ksuite_dict["trial_expiry_at"] = None
        m = MyKSuite.from_api(my_ksuite_dict)
        assert m.trial_expiry_at is None

    def test_null_drive_and_mail_are_none(self, my_ksuite_dict: dict) -> None:
        my_ksuite_dict["drive"] = None
        my_ksuite_dict["mail"] = None
        m = MyKSuite.from_api(my_ksuite_dict)
        assert m.drive is None
        assert m.mail is None

    def test_empty_string_drive_becomes_none(self, my_ksuite_dict: dict) -> None:
        my_ksuite_dict["drive"] = ""
        my_ksuite_dict["mail"] = ""
        m = MyKSuite.from_api(my_ksuite_dict)
        assert m.drive is None
        assert m.mail is None


class TestMyKSuiteToDict:
    def test_serializes_all_fields(self) -> None:
        from datetime import datetime

        m = MyKSuite(
            id=1,
            pack="kSuite Free",
            status="active",
            product="ksuite",
            is_free=True,
            drive="9012",
            mail="5678",
            has_auto_renew="disabled",
            trial_expiry_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        d = m.to_dict()
        assert d == {
            "id": 1,
            "pack": "kSuite Free",
            "status": "active",
            "product": "ksuite",
            "is_free": True,
            "drive": "9012",
            "mail": "5678",
            "has_auto_renew": "disabled",
            "trial_expiry_at": "2024-06-01T12:00:00",
        }

    def test_none_fields(self) -> None:
        m = MyKSuite(
            id=0,
            pack="",
            status="",
            product="",
            is_free=False,
            drive=None,
            mail=None,
            has_auto_renew="",
            trial_expiry_at=None,
        )
        d = m.to_dict()
        assert d["drive"] is None
        assert d["mail"] is None
        assert d["trial_expiry_at"] is None
