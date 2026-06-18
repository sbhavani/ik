"""Tests for KDriveClient — every public method, mocked requests.Session."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from ik import KDriveClient, KDriveError, MoveOperation, ShareLink
from tests.conftest import FIXTURES_DIR, make_response


def make_client(session_mock: Mock) -> KDriveClient:
    client = KDriveClient("test-token")
    client.session = session_mock
    return client


class TestConstructor:
    def test_sets_bearer_token_header(self) -> None:
        client = KDriveClient("abc123")
        assert client.session.headers["Authorization"] == "Bearer abc123"

    def test_sets_accept_header(self) -> None:
        client = KDriveClient("abc123")
        assert client.session.headers["Accept"] == "application/json"


class TestRequest:
    def test_happy_path_returns_body(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [{"id": 1}]})
        client = make_client(session)

        body = client._request("GET", "/foo")

        assert body == {"data": [{"id": 1}]}
        session.request.assert_called_once()

    def test_4xx_raises_kdrive_error(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            404,
            {
                "error": {
                    "code": "not_found",
                    "description": "Drive not found",
                }
            },
        )
        client = make_client(session)

        with pytest.raises(KDriveError, match="not_found.*Drive not found"):
            client._request("GET", "/foo")

    def test_non_json_body_returns_raw(self) -> None:
        # Status must be 2xx: the 4xx branch raises before we ever look at `body`.
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, json_body=None, text="oops")
        client = make_client(session)

        body = client._request("GET", "/foo")

        assert body == {"raw": "oops"}

    def test_streaming_returns_response_unchanged(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, chunks=[b"hello"])
        client = make_client(session)

        resp = client._request("GET", "/foo", stream=True)

        assert b"".join(resp.iter_content(chunk_size=8192)) == b"hello"
        # streaming responses must not be JSON-parsed
        resp.json.assert_not_called()


class TestAccountId:
    def test_fetches_and_caches(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [{"id": 999}]})
        client = make_client(session)

        assert client.account_id == 999
        assert client.account_id == 999
        # second access must not re-request
        assert session.request.call_count == 1

    def test_no_accounts_raises(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": []})
        client = make_client(session)

        with pytest.raises(KDriveError, match="No Infomaniak accounts"):
            _ = client.account_id


class TestDrives:
    def test_list_drives(self) -> None:
        session = Mock(spec=requests.Session)
        # First call: account_id discovery
        # Second call: drive list
        session.request.side_effect = [
            make_response(200, {"data": [{"id": 7}]}),
            make_response(200, {"data": [{"id": 42, "name": "D1"}]}),
        ]
        client = make_client(session)

        drives = client.list_drives()

        assert [d.id for d in drives] == [42]
        assert drives[0].name == "D1"

    def test_get_drive(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": {"id": 42, "name": "Solo"}})
        client = make_client(session)

        drive = client.get_drive(42)

        assert drive.id == 42
        assert drive.name == "Solo"


class TestFiles:
    def test_list_files_single_page(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [file_dict], "has_more": False})
        client = make_client(session)

        files = list(client.list_files(1, directory_id=1))

        assert len(files) == 1
        assert files[0].name == "report.pdf"

    def test_list_files_follows_cursor(self, file_dict: dict) -> None:
        first = file_dict | {"id": 1, "name": "a.txt"}
        second = file_dict | {"id": 2, "name": "b.txt"}
        third = file_dict | {"id": 3, "name": "c.txt"}
        session = Mock(spec=requests.Session)
        session.request.side_effect = [
            make_response(200, {"data": [first, second], "has_more": True, "cursor": "C1"}),
            make_response(200, {"data": [third], "has_more": False}),
        ]
        client = make_client(session)

        files = list(client.list_files(1, directory_id=1))

        assert [f.name for f in files] == ["a.txt", "b.txt", "c.txt"]
        assert session.request.call_count == 2
        # Second call must carry the cursor
        second_call_kwargs = session.request.call_args_list[1].kwargs
        assert second_call_kwargs["params"]["cursor"] == "C1"

    def test_get_file(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": file_dict})
        client = make_client(session)

        f = client.get_file(1, 100)

        assert f.id == 100
        assert f.mime_type == "application/pdf"

    def test_create_directory(self, file_dict: dict) -> None:
        file_dict = file_dict | {"id": 200, "name": "new", "type": "dir"}
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": file_dict})
        client = make_client(session)

        f = client.create_directory(1, parent_id=1, name="new")

        assert f.is_directory is True
        assert f.name == "new"
        # POST body shape: json_body, not data
        kwargs = session.request.call_args.kwargs
        assert kwargs["json"] == {"name": "new"}

    def test_upload_file_sends_bytes(self, file_dict: dict) -> None:
        file_dict = file_dict | {"id": 300, "name": "up.txt"}
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": file_dict})
        client = make_client(session)

        f = client.upload_file(drive_id=1, directory_id=2, file_name="up.txt", file_data=b"hi")

        assert f.id == 300
        kwargs = session.request.call_args.kwargs
        # Raw bytes go in `data`, total_size in params
        assert kwargs["data"] == b"hi"
        assert kwargs["params"]["total_size"] == 2
        assert kwargs["params"]["file_name"] == "up.txt"

    def test_download_file_returns_streaming_response(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, chunks=[b"abc", b"def"])
        client = make_client(session)

        resp = client.download_file(1, file_id=100)

        # streaming path: stream=True must be passed
        assert session.request.call_args.kwargs["stream"] is True
        assert list(resp.iter_content(chunk_size=8192)) == [b"abc", b"def"]

    def test_search(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [file_dict]})
        client = make_client(session)

        results = list(client.search(1, "report"))

        assert len(results) == 1
        assert session.request.call_args.kwargs["params"]["query"] == "report"

    def test_trash_file(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {})
        client = make_client(session)

        client.trash_file(1, file_id=999)

        # DELETE verb, no body
        assert session.request.call_args.args[0] == "DELETE"


class TestResolvePath:
    def test_single_segment(self, file_dict: dict) -> None:
        file_dict = file_dict | {"id": 50, "name": "Photos"}
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [file_dict], "has_more": False})
        client = make_client(session)

        assert client.resolve_path(1, "Photos") == 50

    def test_multi_segment(self, file_dict: dict) -> None:
        photos = file_dict | {"id": 50, "name": "Photos", "type": "dir"}
        vacation = file_dict | {"id": 51, "name": "Vacation", "type": "dir"}
        session = Mock(spec=requests.Session)
        # First call: list at root (1) — has Photos
        # Second call: list at Photos (50) — has Vacation
        session.request.side_effect = [
            make_response(200, {"data": [photos], "has_more": False}),
            make_response(200, {"data": [vacation], "has_more": False}),
        ]
        client = make_client(session)

        assert client.resolve_path(1, "Photos/Vacation") == 51

    def test_segment_not_found(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [file_dict], "has_more": False})
        client = make_client(session)

        with pytest.raises(KDriveError, match="'Nope' not found"):
            client.resolve_path(1, "Nope")


class TestMoveCopy:
    def test_move_file(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {"data": {"cancel_id": "abc-123", "valid_until": 1_700_000_000}},
        )
        client = make_client(session)

        op = client.move_file(drive_id=1, file_id=100, destination_directory_id=50)

        assert isinstance(op, MoveOperation)
        assert op.cancel_id == "abc-123"
        # URL embeds both file_id and destination_directory_id
        call_args = session.request.call_args
        assert call_args.args[0] == "POST"
        assert "/files/100/move/50" in call_args.args[1]
        # Default conflict=error, no name when not provided
        assert call_args.kwargs["json"] == {"conflict": "error"}

    def test_move_file_with_name_and_conflict(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"cancel_id": "x", "valid_until": 1}}
        )
        client = make_client(session)

        client.move_file(
            drive_id=1,
            file_id=100,
            destination_directory_id=50,
            name="renamed.pdf",
            conflict="rename",
        )

        body = session.request.call_args.kwargs["json"]
        assert body == {"conflict": "rename", "name": "renamed.pdf"}

    def test_copy_file(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": file_dict | {"id": 200, "name": "report-copy.pdf"}}
        )
        client = make_client(session)

        result = client.copy_file(drive_id=1, file_id=100, destination_directory_id=50)

        assert result.id == 200
        assert result.name == "report-copy.pdf"
        call_args = session.request.call_args
        assert call_args.args[0] == "POST"
        assert "/files/100/copy/50" in call_args.args[1]
        # Default conflict=rename
        assert call_args.kwargs["json"] == {"conflict": "rename"}

    def test_copy_file_with_name(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"id": 201, "name": "x", "type": "file"}}
        )
        client = make_client(session)

        client.copy_file(
            drive_id=1,
            file_id=100,
            destination_directory_id=50,
            name="renamed.pdf",
        )

        assert session.request.call_args.kwargs["json"] == {
            "conflict": "rename",
            "name": "renamed.pdf",
        }

    def test_copy_file_directory(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"id": 300, "name": "Photos", "type": "dir"}}
        )
        client = make_client(session)

        result = client.copy_file(drive_id=1, file_id=100, destination_directory_id=50)

        assert result.is_directory is True
        assert result.name == "Photos"


class TestTrash:
    def test_list_trash_single_page(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [file_dict], "has_more": False})
        client = make_client(session)

        files = list(client.list_trash(1))

        assert len(files) == 1
        assert files[0].name == "report.pdf"
        # GET verb, paginated endpoint
        assert session.request.call_args.args[0] == "GET"

    def test_list_trash_follows_cursor(self, file_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        page1 = {"data": [file_dict], "has_more": True, "cursor": "c1"}
        page2 = {"data": [], "has_more": False}
        session.request.return_value = make_response(200, page1)
        session.request.side_effect = [make_response(200, page1), make_response(200, page2)]
        client = make_client(session)

        files = list(client.list_trash(1))

        assert len(files) == 1
        # Two calls: first no cursor, second with cursor=c1
        assert session.request.call_count == 2
        assert session.request.call_args_list[1].kwargs["params"] == {"cursor": "c1"}

    def test_restore_file_sync(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": True})
        client = make_client(session)

        result = client.restore_file(drive_id=1, file_id=999, destination_directory_id=1)

        assert result is None  # sync → no cancel handle
        # POST verb, destination in body
        assert session.request.call_args.args[0] == "POST"
        assert session.request.call_args.kwargs["json"] == {"destination_directory_id": 1}

    def test_restore_file_async(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"cancel_id": "op-r-1", "valid_until": 1717200000}}
        )
        client = make_client(session)

        result = client.restore_file(drive_id=1, file_id=999)

        assert result is not None
        assert result.cancel_id == "op-r-1"

    def test_empty_trash(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": True})
        client = make_client(session)

        client.empty_trash(drive_id=1)

        # DELETE verb, no body
        assert session.request.call_args.args[0] == "DELETE"
        assert session.request.call_args.args[1] == "https://api.infomaniak.com/2/drive/1/trash"


class TestActivity:
    def test_list_activity_single_page(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {
                "data": [
                    {
                        "id": 1,
                        "created_at": 1717200000,
                        "action": "file_create",
                        "new_path": "/Photos/a.jpg",
                        "old_path": "",
                        "file_id": 100,
                        "user_id": 7,
                    }
                ],
                "has_more": False,
            },
        )
        client = make_client(session)

        entries = list(client.list_activity(1))

        assert len(entries) == 1
        assert entries[0].action == "file_create"
        assert entries[0].new_path == "/Photos/a.jpg"
        # GET verb, lang + limit + order required
        params = session.request.call_args.kwargs["params"]
        assert params["lang"] == "en"
        assert params["limit"] == 10

    def test_list_activity_filters(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": [], "has_more": False})
        client = make_client(session)

        list(
            client.list_activity(
                1,
                from_=1700000000,
                until=1800000000,
                users=[7, 8],
                actions=["file_create", "file_mv"],
                files=[100, 200],
                limit=50,
            )
        )

        params = session.request.call_args.kwargs["params"]
        assert params["from"] == 1700000000
        assert params["until"] == 1800000000
        assert params["users"] == [7, 8]
        assert params["actions"] == ["file_create", "file_mv"]
        assert params["files"] == [100, 200]
        assert params["limit"] == 50

    def test_list_activity_follows_cursor(self) -> None:
        session = Mock(spec=requests.Session)
        page1 = {
            "data": [{"id": 1, "created_at": 1, "action": "x"}],
            "has_more": True,
            "cursor": "C1",
        }
        page2 = {"data": [], "has_more": False}
        session.request.side_effect = [make_response(200, page1), make_response(200, page2)]
        client = make_client(session)

        entries = list(client.list_activity(1))

        assert len(entries) == 1
        assert session.request.call_count == 2
        assert session.request.call_args_list[1].kwargs["params"]["cursor"] == "C1"


class TestUploadStreaming:
    def test_streaming_small_file_single_chunk(self, tmp_path, file_dict: dict) -> None:
        f = tmp_path / "small.bin"
        f.write_bytes(b"abc")
        file_dict = file_dict | {"id": 300, "name": "small.bin"}
        session = Mock(spec=requests.Session)
        # start → chunk → finish
        session.request.side_effect = [
            make_response(200, {"data": {"session_token": "tok-1"}}),
            make_response(200, {}),
            make_response(200, {"data": file_dict}),
        ]
        client = make_client(session)

        result = client.upload_file_streaming(
            drive_id=1, directory_id=2, file_name="small.bin", file_path=f
        )

        assert result.id == 300
        # Three POSTs total: start, chunk, finish
        assert session.request.call_count == 3
        # Start body declares total_size=3, total_chunks=1
        start_body = session.request.call_args_list[0].kwargs["json"]
        assert start_body["total_size"] == 3
        assert start_body["total_chunks"] == 1
        assert start_body["directory_id"] == 2
        # Chunk call: raw bytes, chunk_number=1, chunk_size=3
        chunk_call = session.request.call_args_list[1]
        assert chunk_call.kwargs["data"] == b"abc"
        assert chunk_call.kwargs["params"] == {"chunk_number": 1, "chunk_size": 3}
        # Finish call: no body data
        finish_call = session.request.call_args_list[2]
        assert finish_call.kwargs["data"] is None

    def test_streaming_multi_chunk(self, tmp_path, file_dict: dict) -> None:
        f = tmp_path / "big.bin"
        # 20 bytes — 3 chunks of 8
        f.write_bytes(b"x" * 20)
        file_dict = file_dict | {"id": 301, "name": "big.bin"}
        session = Mock(spec=requests.Session)
        # start → 3 chunks → finish
        session.request.side_effect = [
            make_response(200, {"data": {"session_token": "tok-2"}}),
            make_response(200, {}),
            make_response(200, {}),
            make_response(200, {}),
            make_response(200, {"data": file_dict}),
        ]
        client = make_client(session)

        progress_calls: list[tuple[int, int]] = []
        client.upload_file_streaming(
            drive_id=1,
            directory_id=2,
            file_name="big.bin",
            file_path=f,
            chunk_size=8,
            on_progress=lambda sent, total: progress_calls.append((sent, total)),
        )

        # 3 chunk POSTs in order, with chunk_number 1/2/3
        chunk_calls = session.request.call_args_list[1:4]
        assert [c.kwargs["params"]["chunk_number"] for c in chunk_calls] == [1, 2, 3]
        # Last chunk is 4 bytes (20 - 8 - 8)
        assert chunk_calls[-1].kwargs["params"]["chunk_size"] == 4
        # Progress fires once per chunk, cumulative bytes
        assert progress_calls == [(8, 20), (16, 20), (20, 20)]

    def test_streaming_zero_byte_file(self, tmp_path, file_dict: dict) -> None:
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        file_dict = file_dict | {"id": 302, "name": "empty.bin", "size": 0}
        session = Mock(spec=requests.Session)
        # start → finish (no chunks for 0-byte)
        session.request.side_effect = [
            make_response(200, {"data": {"session_token": "tok-3"}}),
            make_response(200, {"data": file_dict}),
        ]
        client = make_client(session)

        result = client.upload_file_streaming(
            drive_id=1, directory_id=2, file_name="empty.bin", file_path=f
        )

        assert result.id == 302
        assert session.request.call_count == 2
        # Start declared total_chunks=0
        start_body = session.request.call_args_list[0].kwargs["json"]
        assert start_body["total_chunks"] == 0
        assert start_body["total_size"] == 0

    def test_streaming_no_progress_callback(self, tmp_path, file_dict: dict) -> None:
        # Sanity check: on_progress=None is the default and must not break the flow.
        f = tmp_path / "ok.bin"
        f.write_bytes(b"y" * 10)
        file_dict = file_dict | {"id": 303, "name": "ok.bin"}
        session = Mock(spec=requests.Session)
        session.request.side_effect = [
            make_response(200, {"data": {"session_token": "tok-4"}}),
            make_response(200, {}),
            make_response(200, {"data": file_dict}),
        ]
        client = make_client(session)

        result = client.upload_file_streaming(
            drive_id=1, directory_id=2, file_name="ok.bin", file_path=f
        )

        assert result.id == 303


class TestShareLinks:
    def test_create_share_link_defaults(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            201,
            {
                "data": {
                    "url": "https://kdrive.infomaniak.com/app/share/abc",
                    "file_id": 100,
                    "right": "public",
                    "capabilities": {"can_download": True},
                }
            },
        )
        client = make_client(session)

        link = client.create_share_link(drive_id=1, file_id=100)

        assert isinstance(link, ShareLink)
        assert link.url == "https://kdrive.infomaniak.com/app/share/abc"
        assert link.file_id == 100
        # Default body: right=public, can_download=True, all others False
        body = session.request.call_args.kwargs["json"]
        assert body["right"] == "public"
        assert body["can_download"] is True
        assert body["can_edit"] is False
        # POST to /files/{id}/link
        assert session.request.call_args.args[0] == "POST"
        assert "/files/100/link" in session.request.call_args.args[1]

    def test_create_share_link_with_password_and_validity(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            201, {"data": {"url": "https://x", "file_id": 100, "right": "password"}}
        )
        client = make_client(session)

        client.create_share_link(
            drive_id=1,
            file_id=100,
            right="password",
            password="hunter2",
            valid_until=1_700_000_000,
        )

        body = session.request.call_args.kwargs["json"]
        assert body["right"] == "password"
        assert body["password"] == "hunter2"
        assert body["valid_until"] == 1_700_000_000

    def test_get_share_link(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {
                "data": {
                    "url": "https://kdrive.example/s/xyz",
                    "file_id": 100,
                    "right": "public",
                    "valid_until": 1_700_000_000,
                    "capabilities": {
                        "can_download": True,
                        "can_edit": False,
                        "can_see_info": True,
                    },
                    "access_blocked": False,
                    "created_at": 1_600_000_000,
                    "updated_at": 1_650_000_000,
                    "created_by": 42,
                    "views": 7,
                }
            },
        )
        client = make_client(session)

        link = client.get_share_link(drive_id=1, file_id=100)

        assert session.request.call_args.args[0] == "GET"
        assert link.url == "https://kdrive.example/s/xyz"
        assert link.right == "public"
        assert link.can_download is True
        assert link.can_see_info is True
        assert link.can_edit is False
        assert link.created_by == 42
        assert link.views == 7
        # Unix timestamps converted to datetimes
        assert link.valid_until is not None
        assert link.valid_until.timestamp() == 1_700_000_000

    def test_update_share_link_only_sends_changed_fields(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"url": "https://x", "file_id": 100, "right": "public"}}
        )
        client = make_client(session)

        client.update_share_link(drive_id=1, file_id=100, can_edit=True)

        # PUT to the link endpoint
        assert session.request.call_args.args[0] == "PUT"
        body = session.request.call_args.kwargs["json"]
        # Only the changed field is sent
        assert body == {"can_edit": True}

    def test_update_share_link_valid_until_cleared(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"url": "https://x", "file_id": 100, "right": "public"}}
        )
        client = make_client(session)

        # valid_until=None means "clear the existing expiry"
        client.update_share_link(drive_id=1, file_id=100, valid_until=None)

        body = session.request.call_args.kwargs["json"]
        assert body == {"valid_until": None}

    def test_update_share_link_valid_until_omitted(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200, {"data": {"url": "https://x", "file_id": 100, "right": "public"}}
        )
        client = make_client(session)

        # Don't pass valid_until at all → must NOT appear in body
        client.update_share_link(drive_id=1, file_id=100, can_edit=True)

        body = session.request.call_args.kwargs["json"]
        assert "valid_until" not in body

    def test_delete_share_link(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {})
        client = make_client(session)

        client.delete_share_link(drive_id=1, file_id=100)

        # DELETE verb, no body, hits the link endpoint
        assert session.request.call_args.args[0] == "DELETE"
        assert "/files/100/link" in session.request.call_args.args[1]
        assert session.request.call_args.kwargs.get("json") is None

    def test_list_shared_files_single_page(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {
                "data": [
                    {
                        "id": 10,
                        "name": "shared.pdf",
                        "update_at": 1_700_000_000,
                        "users": 3,
                    },
                    {
                        "id": 11,
                        "name": "photo.jpg",
                        "update_at": 1_650_000_000,
                        "users": 0,
                    },
                ],
                "has_more": False,
            },
        )
        client = make_client(session)

        files = list(client.list_shared_files(drive_id=1))

        assert [f.id for f in files] == [10, 11]
        assert files[0].name == "shared.pdf"
        assert files[0].users == 3
        assert files[0].update_at is not None
        # GET on the v3 list endpoint
        assert session.request.call_args.args[0] == "GET"
        assert "/3/drive/1/files/links" in session.request.call_args.args[1]

    def test_list_shared_files_follows_cursor(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.side_effect = [
            make_response(
                200,
                {
                    "data": [{"id": 10, "name": "a", "update_at": 0, "users": 0}],
                    "has_more": True,
                    "cursor": "C1",
                },
            ),
            make_response(
                200,
                {
                    "data": [{"id": 11, "name": "b", "update_at": 0, "users": 0}],
                    "has_more": False,
                },
            ),
        ]
        client = make_client(session)

        files = list(client.list_shared_files(drive_id=1))

        assert [f.id for f in files] == [10, 11]
        assert session.request.call_count == 2
        # Second call carries the cursor
        assert session.request.call_args_list[1].kwargs["params"]["cursor"] == "C1"


class TestPublicClouds:
    def test_list_public_clouds(self, vps_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        # First call: account_id discovery; second: public_clouds list
        session.request.side_effect = [
            make_response(200, {"data": [{"id": 7}]}),
            make_response(200, {"data": [vps_dict]}),
        ]
        client = make_client(session)

        vpses = client.list_public_clouds()

        assert len(vpses) == 1
        assert vpses[0].id == 1001
        assert vpses[0].name == "My VPS Cloud"
        assert vpses[0].project_count == 3
        assert vpses[0].price == 12.0
        # Second call hits /1/public_clouds
        assert "/1/public_clouds" in session.request.call_args_list[1].args[1]

    def test_get_public_cloud(self, vps_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": vps_dict})
        client = make_client(session)

        v = client.get_public_cloud(1001)

        assert v.id == 1001
        assert v.name == "My VPS Cloud"
        assert v.description == "Production environment"
        assert "/1/public_clouds/1001" in session.request.call_args.args[1]


class TestMyKSuite:
    def test_list_my_ksuites(self, my_ksuite_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": my_ksuite_dict})
        client = make_client(session)

        mail = client.list_my_ksuites()

        assert len(mail) == 1
        assert mail[0].id == 1234
        assert mail[0].pack == "kSuite Standard"
        assert mail[0].mail == "5678"
        assert "/1/my_ksuite/current" in session.request.call_args.args[1]
        assert session.request.call_args.args[0] == "GET"

    def test_list_my_ksuites_empty_when_no_data(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": None})
        client = make_client(session)

        assert client.list_my_ksuites() == []

    def test_list_my_ksuites_empty_when_response_has_no_data_key(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {})
        client = make_client(session)

        assert client.list_my_ksuites() == []

    def test_get_my_ksuite(self, my_ksuite_dict: dict) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": my_ksuite_dict})
        client = make_client(session)

        m = client.get_my_ksuite(1234)

        assert m.id == 1234
        assert m.pack == "kSuite Standard"
        assert m.is_free is False
        assert "/1/my_ksuite/1234" in session.request.call_args.args[1]
        assert session.request.call_args.args[0] == "GET"


class TestListMailboxes:
    def test_returns_mailboxes(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {
                "data": [
                    {"id": 1, "name": "INBOX", "unread_count": 3, "message_count": 42},
                    {"id": 2, "name": "Sent", "unread_count": 0, "message_count": 18},
                ]
            },
        )
        client = make_client(session)

        boxes = client.list_mailboxes(99)

        assert len(boxes) == 2
        assert boxes[0].name == "INBOX"
        assert boxes[0].unread_count == 3
        assert boxes[1].name == "Sent"
        assert "/1/mail_hostings/99/mailboxes" in session.request.call_args.args[1]

    def test_empty_returns_empty_list(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(200, {"data": []})
        client = make_client(session)

        assert client.list_mailboxes(99) == []


class TestListMessages:
    def test_yields_messages(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = make_response(
            200,
            {
                "data": [
                    {
                        "id": 100,
                        "from": "a@x.com",
                        "to": ["b@x.com"],
                        "subject": "hello",
                        "date": 1736899200,
                        "has_attachments": False,
                        "size": 1024,
                    },
                    {
                        "id": 101,
                        "from": "b@x.com",
                        "to": ["a@x.com"],
                        "subject": "re: hello",
                        "has_attachments": True,
                        "size": 4096,
                    },
                ]
            },
        )
        client = make_client(session)

        msgs = list(client.list_messages(99, mailbox_id=1))

        assert len(msgs) == 2
        assert msgs[0].id == 100
        assert msgs[0].mailbox_id == 1
        assert msgs[1].has_attachments is True
        assert "/1/mail_hostings/99/mailboxes/1/messages" in session.request.call_args.args[1]

    def test_follows_cursor(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.side_effect = [
            make_response(
                200,
                {
                    "data": [{"id": 100, "from": "a", "subject": "x", "size": 1}],
                    "has_more": True,
                    "cursor": "C1",
                },
            ),
            make_response(
                200,
                {"data": [{"id": 101, "from": "b", "subject": "y", "size": 2}]},
            ),
        ]
        client = make_client(session)

        msgs = list(client.list_messages(99, mailbox_id=1))

        assert [m.id for m in msgs] == [100, 101]
        assert session.request.call_count == 2
        assert session.request.call_args_list[1].kwargs["params"]["cursor"] == "C1"


class TestGetMessage:
    def _raw_response(self, body: bytes) -> Mock:
        resp = Mock(spec=requests.Response)
        resp.status_code = 200
        resp.content = body
        resp.json.side_effect = ValueError("not json")
        resp.text = ""
        return resp

    def test_returns_message_body(self) -> None:
        session = Mock(spec=requests.Session)
        session.request.return_value = self._raw_response(
            (FIXTURES_DIR / "mail" / "plain.eml").read_bytes()
        )
        client = make_client(session)

        body = client.get_message(99, mailbox_id=1, msg_id=42)

        assert body.id == 42
        assert body.mailbox_id == 1
        assert body.from_ == "alice@example.com"
        assert body.subject == "Quick question"
        assert "/1/mail_hostings/99/mailboxes/1/messages/42" in session.request.call_args.args[1]

    def test_404_raises_kdrive_error(self) -> None:
        session = Mock(spec=requests.Session)
        err_resp = Mock(spec=requests.Response)
        err_resp.status_code = 404
        err_resp.json.return_value = {
            "error": {"code": "not_found", "description": "Message not found"}
        }
        err_resp.text = ""
        session.request.return_value = err_resp
        client = make_client(session)

        with pytest.raises(KDriveError, match="not_found"):
            client.get_message(99, mailbox_id=1, msg_id=42)
