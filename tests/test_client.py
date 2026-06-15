"""Tests for KDriveClient — every public method, mocked requests.Session."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from ik import KDriveClient, KDriveError
from tests.conftest import make_response


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
