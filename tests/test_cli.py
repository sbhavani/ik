"""Tests for src/ik/cli.py — token/account resolution and top-level commands.

TODO: configure test — `cmd_configure` is interactive (uses `input()`) and writes
to `~/.config/ik/config.json`. Skipped per scope agreement. Refactor `configure`
to take a `token_prompt=input` parameter first, then add a test that supplies a
fake prompt and patches `open`/`os.makedirs`.
"""

from __future__ import annotations

import argparse
import json
import os
from unittest.mock import Mock

import pytest

from ik import KDriveClient
from ik.cli import _resolve_account_id, _resolve_token, cmd_drives, cmd_whoami


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ── _resolve_token ────────────────────────────────────────────────────


class TestResolveToken:
    def test_flag_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        assert _resolve_token(ns(token="from-flag")) == "from-flag"

    def test_env_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_TOKEN", "from-env")
        assert _resolve_token(ns(token=None)) == "from-env"

    def test_config_file_when_no_flag_or_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"token": "from-config"}))
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(config))

        assert _resolve_token(ns(token=None)) == "from-config"

    def test_missing_token_exits(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path / "absent.json"))

        with pytest.raises(SystemExit, match="No API token"):
            _resolve_token(ns(token=None))

    def test_config_without_token_field_exits(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({}))  # no token key
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(config))

        with pytest.raises(SystemExit, match="No API token"):
            _resolve_token(ns(token=None))


# ── _resolve_account_id ───────────────────────────────────────────────


class TestResolveAccountId:
    def test_env_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_ACCOUNT_ID", "12345")
        assert _resolve_account_id("any-token") == 12345

    def test_config_when_no_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"account_id": 999}))
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(config))

        assert _resolve_account_id("any-token") == 999

    def test_env_wins_over_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"account_id": 999}))
        monkeypatch.setenv("INFOMANIAK_ACCOUNT_ID", "111")
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(config))

        assert _resolve_account_id("any-token") == 111

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path / "absent.json"))

        assert _resolve_account_id("any-token") is None


# ── cmd_drives ────────────────────────────────────────────────────────


class TestCmdDrives:
    def test_no_drives(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = []

        cmd_drives(ns(), client)

        assert capsys.readouterr().out == "No drives found.\n"

    def test_lists_drives(self, capsys: pytest.CaptureFixture) -> None:
        from datetime import datetime

        from ik import Drive

        client = Mock(spec=KDriveClient)
        client.list_drives.return_value = [
            Drive(
                id=1,
                name="Personal",
                size=10 * 1024**3,
                used_size=2 * 1024**3,
                is_locked=False,
                has_operation_in_progress=False,
                created_at=datetime(2024, 1, 1),
            ),
            Drive(
                id=2,
                name="Locked",
                size=5 * 1024**3,
                used_size=1 * 1024**3,
                is_locked=True,
                has_operation_in_progress=False,
                created_at=datetime(2024, 1, 1),
            ),
        ]

        cmd_drives(ns(), client)

        out = capsys.readouterr().out
        assert "1" in out and "Personal" in out and "active" in out
        assert "2" in out and "Locked" in out and "locked" in out


# ── cmd_whoami ────────────────────────────────────────────────────────


class TestCmdWhoami:
    def test_no_accounts_exits(self) -> None:
        client = Mock(spec=KDriveClient)
        client._request.return_value = {"data": []}

        with pytest.raises(SystemExit, match="No accounts"):
            cmd_whoami(ns(), client)

    def test_prints_account_info(self, capsys: pytest.CaptureFixture) -> None:
        client = Mock(spec=KDriveClient)
        client._request.return_value = {
            "data": [{"id": 7, "name": "Alice", "email": "alice@example.com"}]
        }

        cmd_whoami(ns(), client)

        out = capsys.readouterr().out
        assert "Account ID: 7" in out
        assert "Name: Alice" in out
        assert "Email: alice@example.com" in out


# ── global --quiet / --yes parsing ────────────────────────────────────


class TestGlobalFlags:
    def test_defaults(self) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        with patch.object(sys, "argv", ["ik", "drives"]):
            with patch("ik.cli._resolve_token", return_value="t"):
                with patch("ik.cli.KDriveClient") as KC:
                    KC.return_value.list_drives.return_value = []
                    with patch("ik.cli.cmd_drives") as cd:
                        try:
                            _main()
                        except SystemExit:
                            pass
                        captured = cd.call_args.args[0]
                        assert captured.quiet is False
                        assert captured.yes is False

    def test_quiet_and_yes_parsed(self) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        with patch.object(sys, "argv", ["ik", "--quiet", "--yes", "drives"]):
            with patch("ik.cli._resolve_token", return_value="t"):
                with patch("ik.cli.KDriveClient") as KC:
                    KC.return_value.list_drives.return_value = []
                    with patch("ik.cli.cmd_drives") as cd:
                        try:
                            _main()
                        except SystemExit:
                            pass
                        captured = cd.call_args.args[0]
                        assert captured.quiet is True
                        assert captured.yes is True
