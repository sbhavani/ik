"""Tests for src/ik/driver/ — every cmd_* function with an injected KDriveClient."""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from ik import Drive, File, KDriveClient, KDriveError, ShareLink, SharedFile
from ik.driver import (
    _get_default_drive,
    _make_progress,
    _resolve_directory,
    _resolve_source_id,
    cmd_cp,
    cmd_download,
    cmd_info,
    cmd_ls,
    cmd_mkdir,
    cmd_mv,
    cmd_rm,
    cmd_search,
    cmd_share_create,
    cmd_share_get,
    cmd_share_ls,
    cmd_share_remove,
    cmd_share_update,
    cmd_tree,
    cmd_upload,
)


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def make_file(
    *,
    id: int = 1,
    name: str = "f.txt",
    size: int = 100,
    is_directory: bool = False,
    parent_id: int | None = 1,
) -> File:
    return File(
        id=id,
        name=name,
        size=size,
        is_directory=is_directory,
        parent_id=parent_id,
        created_at=datetime(2024, 1, 1),
        modified_at=datetime(2024, 1, 2),
        mime_type=None if is_directory else "text/plain",
    )


def make_drive(id: int = 1, name: str = "D") -> Drive:
    return Drive(
        id=id,
        name=name,
        size=10 * 1024**3,
        used_size=1 * 1024**3,
        is_locked=False,
        has_operation_in_progress=False,
        created_at=datetime(2024, 1, 1),
    )


# ── cmd_ls ────────────────────────────────────────────────────────────


class TestCmdLs:
    def test_empty_directory(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_files.return_value = iter([])
        out = io.StringIO()

        cmd_ls(ns(drive=1, path=None, show_id=False), client, out=out)

        assert out.getvalue() == "(empty)\n"
        assert capsys.readouterr().out == ""

    def test_lists_files(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_files.return_value = iter(
            [make_file(id=10, name="a.txt"), make_file(id=11, name="b.txt")]
        )

        cmd_ls(ns(drive=1, path=None, show_id=False), client, out=io.StringIO())

        captured = capsys.readouterr().out
        assert "a.txt" in captured
        assert "b.txt" in captured
        # Without --id, the formatter has no id column — only marker, size, name.
        a_line = next(line for line in captured.splitlines() if "a.txt" in line)
        assert a_line.rstrip().endswith("a.txt")

    def test_show_id(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_files.return_value = iter([make_file(id=42, name="x.txt")])

        cmd_ls(ns(drive=1, path=None, show_id=True), client, out=io.StringIO())

        out = capsys.readouterr().out
        assert "42" in out
        assert "x.txt" in out

    def test_resolves_path(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 50
        client.list_files.return_value = iter([])

        cmd_ls(ns(drive=1, path="Photos", show_id=False), client, out=io.StringIO())

        client.resolve_path.assert_called_once_with(1, "Photos")
        # list_files must be called against the resolved dir
        client.list_files.assert_called_once_with(1, 50)

    def test_falls_back_to_default_drive(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = [make_drive(id=99)]
        client.list_files.return_value = iter([])

        cmd_ls(ns(drive=None, path=None, show_id=False), client, out=io.StringIO())

        client.list_drives.assert_called_once()
        client.list_files.assert_called_once_with(99, 1)


# ── cmd_tree ──────────────────────────────────────────────────────────


class TestCmdTree:
    def test_root_only(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_files.return_value = iter([])
        out = io.StringIO()

        cmd_tree(ns(drive=1, path=None), client, out=out)

        assert out.getvalue() == ".\n"

    def test_flat_dir(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_files.return_value = iter([make_file(name="a.txt"), make_file(name="b.txt")])
        out = io.StringIO()

        cmd_tree(ns(drive=1, path=None), client, out=out)

        lines = out.getvalue().splitlines()
        assert lines[0] == "."
        # First item gets "|--", last item gets "`--"
        assert "|-- a.txt" in lines
        assert "`-- b.txt" in lines

    def test_recurses_into_subdirs(self) -> None:
        client = Mock(spec=KDriveClient)
        # root lists one dir; that dir lists one file
        client.list_files.side_effect = [
            iter([make_file(id=10, name="sub", is_directory=True)]),
            iter([make_file(id=11, name="leaf.txt")]),
        ]
        out = io.StringIO()

        cmd_tree(ns(drive=1, path=None), client, out=out)

        text = out.getvalue()
        assert "sub" in text
        assert "leaf.txt" in text


# ── cmd_mkdir ─────────────────────────────────────────────────────────


class TestCmdMkdir:
    def test_top_level(self) -> None:
        client = Mock(spec=KDriveClient)
        client.create_directory.return_value = make_file(id=200, name="new", is_directory=True)
        out = io.StringIO()

        cmd_mkdir(ns(drive=1, path="new"), client, out=out)

        assert out.getvalue() == "Created: new (id: 200)\n"
        client.create_directory.assert_called_once_with(1, 1, "new")

    def test_nested_path_resolves_parent(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 50
        client.create_directory.return_value = make_file(id=201, name="child", is_directory=True)
        out = io.StringIO()

        cmd_mkdir(ns(drive=1, path="parent/child"), client, out=out)

        client.resolve_path.assert_called_once_with(1, "parent")
        client.create_directory.assert_called_once_with(1, 50, "child")

    def test_trailing_slash_ignored(self) -> None:
        client = Mock(spec=KDriveClient)
        client.create_directory.return_value = make_file(id=202, name="new", is_directory=True)

        cmd_mkdir(ns(drive=1, path="new/"), client, out=io.StringIO())

        client.create_directory.assert_called_once_with(1, 1, "new")


# ── cmd_upload ────────────────────────────────────────────────────────


class TestCmdUpload:
    def test_happy_path(self, tmp_path, capsys: pytest.CaptureFixture) -> None:
        local = tmp_path / "data.bin"
        local.write_bytes(b"hello world")
        client = Mock(spec=KDriveClient)
        client.upload_file.return_value = make_file(id=300, name="data.bin")
        out = io.StringIO()

        cmd_upload(ns(drive=1, local=str(local), dir=7), client, out=out)

        client.upload_file.assert_called_once_with(1, 7, "data.bin", b"hello world")
        assert "Uploading data.bin" in out.getvalue()
        assert "Uploaded: data.bin (id: 300)" in out.getvalue()

    def test_uses_root_directory_by_default(self, tmp_path) -> None:
        local = tmp_path / "x"
        local.write_bytes(b"x")
        client = Mock(spec=KDriveClient)
        client.upload_file.return_value = make_file(id=1, name="x")

        cmd_upload(ns(drive=1, local=str(local), dir=1), client, out=io.StringIO())

        # default dir is 1 (root)
        client.upload_file.assert_called_once()
        # Signature: upload_file(drive_id, directory_id, file_name, file_data)
        assert client.upload_file.call_args.args[1] == 1
        assert client.upload_file.call_args.args[2] == "x"

    def test_missing_local_file_raises(self) -> None:
        client = Mock(spec=KDriveClient)

        with pytest.raises(KDriveError, match="File not found"):
            cmd_upload(
                ns(drive=1, local="/nonexistent/path", dir=1),
                client,
                out=io.StringIO(),
            )


# ── cmd_download ──────────────────────────────────────────────────────


class TestCmdDownload:
    def test_happy_path(self, tmp_path) -> None:
        client = Mock(spec=KDriveClient)
        client.get_file.return_value = make_file(id=100, name="report.pdf")
        resp = Mock()
        resp.headers = {"Content-Length": "6"}
        resp.iter_content.return_value = iter([b"abc", b"def"])
        client.download_file.return_value = resp
        out = io.StringIO()
        dest = tmp_path / "out.pdf"

        cmd_download(ns(drive=1, file="100", local=str(dest)), client, out=out)

        client.download_file.assert_called_once_with(1, 100)
        assert dest.read_bytes() == b"abcdef"
        assert "Downloading report.pdf" in out.getvalue()
        assert f"Saved: {dest}" in out.getvalue()

    def test_local_directory_appends_filename(self, tmp_path) -> None:
        client = Mock(spec=KDriveClient)
        client.get_file.return_value = make_file(id=100, name="data.bin")
        resp = Mock()
        resp.headers = {}
        resp.iter_content.return_value = iter([b"x"])
        client.download_file.return_value = resp

        cmd_download(ns(drive=1, file="100", local=str(tmp_path)), client, out=io.StringIO())

        # tmp_path is a directory → filename should be appended inside it
        assert (tmp_path / "data.bin").exists()


# ── cmd_search ────────────────────────────────────────────────────────


class TestCmdSearch:
    def test_results(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.search.return_value = iter([make_file(id=10, name="invoice-1.pdf")])

        cmd_search(ns(drive=1, query="invoice", show_id=False), client, out=io.StringIO())

        out = capsys.readouterr().out
        assert "invoice-1.pdf" in out

    def test_no_results(self) -> None:
        client = Mock(spec=KDriveClient)
        client.search.return_value = iter([])
        out = io.StringIO()

        cmd_search(ns(drive=1, query="nothing", show_id=False), client, out=out)

        assert out.getvalue() == "No results.\n"

    def test_forwards_query(self) -> None:
        client = Mock(spec=KDriveClient)
        client.search.return_value = iter([])

        cmd_search(ns(drive=1, query="needle", show_id=False), client, out=io.StringIO())

        client.search.assert_called_once_with(1, "needle")


# ── cmd_rm ────────────────────────────────────────────────────────────


class TestCmdRm:
    def test_by_id(self) -> None:
        client = Mock(spec=KDriveClient)
        out = io.StringIO()

        cmd_rm(ns(drive=1, path="123"), client, out=out)

        client.trash_file.assert_called_once_with(1, 123)
        client.resolve_path.assert_not_called()
        assert out.getvalue() == "Trashed: 123\n"

    def test_by_path(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 456
        out = io.StringIO()

        cmd_rm(ns(drive=1, path="Docs/old.txt"), client, out=out)

        client.resolve_path.assert_called_once_with(1, "Docs/old.txt")
        client.trash_file.assert_called_once_with(1, 456)
        assert out.getvalue() == "Trashed: Docs/old.txt\n"


# ── cmd_info ──────────────────────────────────────────────────────────


class TestCmdInfo:
    def test_by_id(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_file.return_value = make_file(id=100, name="report.pdf", size=4096, parent_id=1)
        out = io.StringIO()

        cmd_info(ns(drive=1, path="100"), client, out=out)

        payload = json.loads(out.getvalue())
        assert payload["id"] == 100
        assert payload["name"] == "report.pdf"
        assert payload["type"] == "file"
        assert payload["size"] == 4096
        assert payload["parent_id"] == 1
        assert payload["created_at"] == "2024-01-01T00:00:00"

    def test_directory_marks_type(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_file.return_value = make_file(id=200, name="Photos", is_directory=True)
        out = io.StringIO()

        cmd_info(ns(drive=1, path="200"), client, out=out)

        assert json.loads(out.getvalue())["type"] == "directory"

    def test_by_path(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 7
        client.get_file.return_value = make_file(id=7, name="x")

        cmd_info(ns(drive=1, path="Docs/x"), client, out=io.StringIO())

        client.resolve_path.assert_called_once_with(1, "Docs/x")
        client.get_file.assert_called_once_with(1, 7)


# ── _get_default_drive ───────────────────────────────────────────────


class TestGetDefaultDrive:
    def test_single_drive_returns_id(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = [make_drive(id=42)]

        assert _get_default_drive(client) == 42

    def test_multiple_drives_raises(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = [
            make_drive(id=1, name="A"),
            make_drive(id=2, name="B"),
        ]

        with pytest.raises(KDriveError, match="Multiple drives"):
            _get_default_drive(client)
        # The prompt listing should have been written to stdout
        assert "A" in capsys.readouterr().out

    def test_no_drives_raises(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = []

        with pytest.raises(KDriveError, match="No drives"):
            _get_default_drive(client)


# ── _resolve_directory ───────────────────────────────────────────────


class TestResolveDirectory:
    def test_none_returns_root(self) -> None:
        client = Mock(spec=KDriveClient)
        assert _resolve_directory(client, 1, None) == 1
        client.resolve_path.assert_not_called()

    def test_digit_string_returns_int(self) -> None:
        client = Mock(spec=KDriveClient)
        assert _resolve_directory(client, 1, "42") == 42
        client.resolve_path.assert_not_called()

    def test_path_string_calls_resolve(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 99

        assert _resolve_directory(client, 1, "Photos") == 99
        client.resolve_path.assert_called_once_with(1, "Photos")


# ── _resolve_source_id ───────────────────────────────────────────────


class TestResolveSourceId:
    def test_digit_returns_int(self) -> None:
        client = Mock(spec=KDriveClient)
        assert _resolve_source_id(client, 1, "123") == 123
        client.resolve_path.assert_not_called()

    def test_path_calls_resolve(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 456

        assert _resolve_source_id(client, 1, "Docs/x") == 456
        client.resolve_path.assert_called_once_with(1, "Docs/x")


# ── cmd_mv ────────────────────────────────────────────────────────────


class TestCmdMv:
    def test_by_id(self) -> None:
        from ik import MoveOperation

        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 50  # for "Archive" dst
        client.move_file.return_value = MoveOperation(cancel_id="op-1", valid_until=None)
        out = io.StringIO()

        cmd_mv(ns(drive=1, src="123", dst="Archive", name=None), client, out=out)

        client.move_file.assert_called_once_with(1, 123, 50, name=None)
        assert "Move queued: cancel_id=op-1" in out.getvalue()
        assert "async" in out.getvalue().lower()

    def test_by_path(self) -> None:
        from ik import MoveOperation

        client = Mock(spec=KDriveClient)
        client.resolve_path.side_effect = [200, 50]
        client.move_file.return_value = MoveOperation(cancel_id="op-2", valid_until=None)
        out = io.StringIO()

        cmd_mv(
            ns(drive=1, src="Docs/old.txt", dst="Archive", name=None),
            client,
            out=out,
        )

        # First resolve = source path, second = destination directory
        assert client.resolve_path.call_args_list[0].args == (1, "Docs/old.txt")
        client.move_file.assert_called_once_with(1, 200, 50, name=None)

    def test_with_name(self) -> None:
        from ik import MoveOperation

        client = Mock(spec=KDriveClient)
        client.move_file.return_value = MoveOperation(cancel_id="op-3", valid_until=None)

        cmd_mv(
            ns(drive=1, src="123", dst="50", name="new.txt"),
            client,
            out=io.StringIO(),
        )

        # name forwarded to client
        assert client.move_file.call_args.kwargs["name"] == "new.txt"

    def test_default_drive(self) -> None:
        from ik import MoveOperation

        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = [make_drive(id=99)]
        client.move_file.return_value = MoveOperation(cancel_id="op-4", valid_until=None)

        cmd_mv(
            ns(drive=None, src="123", dst="Archive", name=None),
            client,
            out=io.StringIO(),
        )

        client.list_drives.assert_called_once()
        # drive_id comes from the default-drive fallback
        assert client.move_file.call_args.args[0] == 99


# ── cmd_cp ────────────────────────────────────────────────────────────


class TestCmdCp:
    def test_by_id(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 50  # for "Archive" dst
        client.copy_file.return_value = make_file(id=200, name="copy.pdf")
        out = io.StringIO()

        cmd_cp(ns(drive=1, src="123", dst="Archive", name=None), client, out=out)

        client.copy_file.assert_called_once_with(1, 123, 50, name=None)
        assert out.getvalue() == "Copied: copy.pdf (id: 200)\n"

    def test_by_path(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.side_effect = [200, 50]
        client.copy_file.return_value = make_file(id=201, name="x.txt")

        cmd_cp(
            ns(drive=1, src="Docs/x.txt", dst="Archive", name=None),
            client,
            out=io.StringIO(),
        )

        assert client.resolve_path.call_args_list[0].args == (1, "Docs/x.txt")
        client.copy_file.assert_called_once_with(1, 200, 50, name=None)

    def test_with_name(self) -> None:
        client = Mock(spec=KDriveClient)
        client.copy_file.return_value = make_file(id=202, name="renamed.pdf")
        out = io.StringIO()

        cmd_cp(
            ns(drive=1, src="123", dst="50", name="renamed.pdf"),
            client,
            out=out,
        )

        assert client.copy_file.call_args.kwargs["name"] == "renamed.pdf"
        assert out.getvalue() == "Copied: renamed.pdf (id: 202)\n"


# ── Threshold branching in cmd_upload ────────────────────────────────


class TestCmdUploadThreshold:
    def test_uses_oneshot_below_threshold(self, tmp_path) -> None:
        local = tmp_path / "small.bin"
        local.write_bytes(b"x" * 1024)  # 1 KB
        client = Mock(spec=KDriveClient)
        client.upload_file.return_value = make_file(id=1, name="small.bin")

        cmd_upload(ns(drive=1, local=str(local), dir=1), client, out=io.StringIO())

        client.upload_file.assert_called_once()
        client.upload_file_streaming.assert_not_called()

    def test_uses_chunked_above_threshold(self, tmp_path) -> None:
        from ik.driver import CHUNKED_THRESHOLD

        local = tmp_path / "big.bin"
        # One byte over the threshold — exercises the boundary cleanly.
        local.write_bytes(b"x" * (CHUNKED_THRESHOLD + 1))
        client = Mock(spec=KDriveClient)
        client.upload_file_streaming.return_value = make_file(id=2, name="big.bin")

        cmd_upload(ns(drive=1, local=str(local), dir=1), client, out=io.StringIO())

        client.upload_file_streaming.assert_called_once()
        client.upload_file.assert_not_called()
        # The streaming call must reference the actual file path
        # (4th positional arg in upload_file_streaming)
        assert client.upload_file_streaming.call_args.args[3] == local


# ── _make_progress ───────────────────────────────────────────────────


class TestMakeProgress:
    def test_disabled_returns_noop(self) -> None:
        stream = io.StringIO()
        cb = _make_progress("file.bin", 1000, stream, enabled=False)

        cb(500, 1000)
        cb(1000, 1000)

        assert stream.getvalue() == ""

    def test_unknown_total_returns_noop(self) -> None:
        stream = io.StringIO()
        cb = _make_progress("file.bin", 0, stream, enabled=True)

        cb(500, 0)
        cb(1000, 0)

        # No bar when total is unknown (e.g. download without Content-Length)
        assert stream.getvalue() == ""

    def test_renders_bar_when_enabled(self) -> None:
        stream = io.StringIO()
        cb = _make_progress("data.bin", 1000, stream, enabled=True)

        cb(500, 1000)
        out = stream.getvalue()

        # Bar uses '#' and '-' characters on a 30-char wide line
        assert "\rdata.bin:" in out
        assert "#" in out
        assert "-" in out
        assert "50.0%" in out
        # MB-scaled bytes appear in the suffix
        assert "MB" in out

    def test_full_progress_fully_fills_bar(self) -> None:
        stream = io.StringIO()
        cb = _make_progress("x.bin", 100, stream, enabled=True)

        cb(100, 100)
        out = stream.getvalue()

        # 100% — bar should be 30 '#' chars, no '-' remaining
        assert "[" + "#" * 30 + "]" in out
        assert "100.0%" in out


# ── cmd_share_* ──────────────────────────────────────────────────────


class TestCmdShare:
    def _link(self, **overrides) -> ShareLink:
        from datetime import datetime

        defaults = dict(
            url="https://kdrive.example/s/abc",
            file_id=100,
            right="public",
            valid_until=None,
            can_download=True,
            can_edit=False,
            can_see_info=False,
            can_comment=False,
            can_request_access=False,
            can_see_stats=False,
            access_blocked=False,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
            created_by=42,
            views=0,
        )
        defaults.update(overrides)
        return ShareLink(**defaults)

    def test_create_prints_url(self) -> None:
        client = Mock(spec=KDriveClient)
        client.create_share_link.return_value = self._link(url="https://kdrive.example/s/abc")
        out = io.StringIO()

        cmd_share_create(
            ns(
                drive=1,
                file="100",
                right="public",
                password=None,
                valid_until=None,
                can_download=True,
                can_edit=False,
                can_see_info=False,
                can_comment=False,
                can_request_access=False,
                can_see_stats=False,
            ),
            client,
            out=out,
        )

        assert out.getvalue() == "https://kdrive.example/s/abc\n"
        # Default right=public, can_download=True, all others False
        kwargs = client.create_share_link.call_args.kwargs
        assert kwargs["right"] == "public"
        assert kwargs["can_download"] is True
        assert kwargs["can_edit"] is False

    def test_create_with_password(self) -> None:
        client = Mock(spec=KDriveClient)
        client.create_share_link.return_value = self._link(right="password")
        out = io.StringIO()

        cmd_share_create(
            ns(
                drive=1,
                file="100",
                right="password",
                password="hunter2",
                valid_until=None,
                can_download=True,
                can_edit=False,
                can_see_info=False,
                can_comment=False,
                can_request_access=False,
                can_see_stats=False,
            ),
            client,
            out=out,
        )

        kwargs = client.create_share_link.call_args.kwargs
        assert kwargs["right"] == "password"
        assert kwargs["password"] == "hunter2"

    def test_create_by_path(self) -> None:
        client = Mock(spec=KDriveClient)
        client.resolve_path.return_value = 50
        client.create_share_link.return_value = self._link(file_id=50)
        out = io.StringIO()

        cmd_share_create(
            ns(
                drive=1,
                file="Docs/x",
                right="public",
                password=None,
                valid_until=None,
                can_download=True,
                can_edit=False,
                can_see_info=False,
                can_comment=False,
                can_request_access=False,
                can_see_stats=False,
            ),
            client,
            out=out,
        )

        client.resolve_path.assert_called_once_with(1, "Docs/x")
        assert client.create_share_link.call_args.args[1] == 50  # file_id

    def test_get_prints_json(self) -> None:
        client = Mock(spec=KDriveClient)
        client.get_share_link.return_value = self._link(right="password", can_edit=True)
        out = io.StringIO()

        cmd_share_get(ns(drive=1, file="100"), client, out=out)

        payload = json.loads(out.getvalue())
        assert payload["url"] == "https://kdrive.example/s/abc"
        assert payload["file_id"] == 100
        assert payload["right"] == "password"
        assert payload["capabilities"]["can_edit"] is True
        assert payload["capabilities"]["can_download"] is True
        assert "views" in payload
        assert "created_at" in payload

    def test_update_calls_update_with_only_set_args(self) -> None:
        from ik import _UNSET

        client = Mock(spec=KDriveClient)
        client.update_share_link.return_value = self._link()
        out = io.StringIO()

        # User passes only --can-edit
        cmd_share_update(
            ns(
                drive=1,
                file="100",
                right=_UNSET,
                password=_UNSET,
                valid_until=_UNSET,
                can_download=_UNSET,
                can_edit=True,
                can_see_info=_UNSET,
                can_comment=_UNSET,
                can_request_access=_UNSET,
                can_see_stats=_UNSET,
            ),
            client,
            out=out,
        )

        # Only can_edit is in the forwarded kwargs
        kwargs = client.update_share_link.call_args.kwargs
        assert kwargs == {"can_edit": True}
        assert "Updated:" in out.getvalue()

    def test_update_no_args_sends_nothing(self) -> None:
        from ik import _UNSET

        client = Mock(spec=KDriveClient)
        client.update_share_link.return_value = self._link()
        out = io.StringIO()

        # No flags passed — every arg stays at the _UNSET default
        cmd_share_update(
            ns(
                drive=1,
                file="100",
                right=_UNSET,
                password=_UNSET,
                valid_until=_UNSET,
                can_download=_UNSET,
                can_edit=_UNSET,
                can_see_info=_UNSET,
                can_comment=_UNSET,
                can_request_access=_UNSET,
                can_see_stats=_UNSET,
            ),
            client,
            out=out,
        )

        # No fields forwarded → empty PUT body
        assert client.update_share_link.call_args.kwargs == {}

    def test_update_with_no_can_download(self) -> None:
        from ik import _UNSET

        client = Mock(spec=KDriveClient)
        client.update_share_link.return_value = self._link(can_download=False)
        out = io.StringIO()

        cmd_share_update(
            ns(
                drive=1,
                file="100",
                right=_UNSET,
                password=_UNSET,
                valid_until=_UNSET,
                can_download=False,  # user explicitly set this
                can_edit=_UNSET,
                can_see_info=_UNSET,
                can_comment=_UNSET,
                can_request_access=_UNSET,
                can_see_stats=_UNSET,
            ),
            client,
            out=out,
        )

        # can_download=False is forwarded (not filtered as _UNSET)
        assert client.update_share_link.call_args.kwargs == {"can_download": False}

    def test_remove(self) -> None:
        client = Mock(spec=KDriveClient)
        out = io.StringIO()

        cmd_share_remove(ns(drive=1, file="100"), client, out=out)

        client.delete_share_link.assert_called_once_with(1, 100)
        assert out.getvalue() == "Removed share link for 100\n"

    def test_ls_empty(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_shared_files.return_value = iter([])
        out = io.StringIO()

        cmd_share_ls(ns(drive=1), client, out=out)

        assert out.getvalue() == "(no shared files)\n"

    def test_ls_lists_files(self) -> None:
        client = Mock(spec=KDriveClient)
        client.list_shared_files.return_value = iter(
            [
                SharedFile(id=10, name="a.pdf", update_at=None, users=3),
                SharedFile(id=11, name="b.jpg", update_at=None, users=0),
            ]
        )
        out = io.StringIO()

        cmd_share_ls(ns(drive=1), client, out=out)

        text = out.getvalue()
        assert "10" in text
        assert "a.pdf" in text
        assert "users: 3" in text
        assert "11" in text
        assert "b.jpg" in text
