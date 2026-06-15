"""Tests for src/ik/driver/ — every cmd_* function with an injected KDriveClient."""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from ik import Drive, File, KDriveClient, KDriveError
from ik.driver import (
    _get_default_drive,
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
