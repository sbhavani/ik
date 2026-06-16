"""Tests for src/ik/cli.py — token/account resolution and top-level commands.

The interactive path of `cmd_configure` is untested (it uses `input()`); the
interesting logic lives in pure helpers `_read_config`, `_write_config`,
`_write_profile`, and `_resolve_default_profile`, which are all unit-tested.
"""

from __future__ import annotations

import argparse
import json
import os
from unittest.mock import Mock

import pytest

from ik import KDriveClient
from ik.cli import (
    _NoDefaultProfile,
    _cmd_configure_list,
    _migrate_v1_to_v3,
    _read_config,
    _resolve_account_id,
    _resolve_default_profile,
    _resolve_token,
    _validate_profile_name,
    _write_config,
    _write_profile,
    cmd_drives,
    cmd_whoami,
)


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ── _resolve_token ────────────────────────────────────────────────────


class TestResolveToken:
    def test_flag_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        assert _resolve_token(ns(token="from-flag"), profile=None) == "from-flag"

    def test_env_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_TOKEN", "from-env")
        assert _resolve_token(ns(token=None), profile=None) == "from-env"

    def test_config_file_when_no_flag_or_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"token": "from-config"}))
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        # v0.1 flat file migrates transparently to a "default" profile.
        assert _resolve_token(ns(token=None), profile="default") == "from-config"

    def test_missing_token_exits(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path / "absent.json"))

        with pytest.raises(SystemExit, match="No API token"):
            _resolve_token(ns(token=None), profile=None)

    def test_config_without_token_field_exits(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({}))  # no token key
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(config))

        with pytest.raises(SystemExit, match="No API token"):
            _resolve_token(ns(token=None), profile=None)


# ── _resolve_account_id ───────────────────────────────────────────────


class TestResolveAccountId:
    def test_env_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_ACCOUNT_ID", "12345")
        assert _resolve_account_id(profile=None) == 12345

    def test_config_when_no_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"account_id": 999}))
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        # v0.1 flat file migrates transparently.
        assert _resolve_account_id(profile="default") == 999

    def test_env_wins_over_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"account_id": 999}))
        monkeypatch.setenv("INFOMANIAK_ACCOUNT_ID", "111")
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_account_id(profile="default") == 111

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path / "absent.json"))

        assert _resolve_account_id(profile=None) is None


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
                        assert captured.profile is None

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

    def test_output_in_top_position(self) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        with patch.object(sys, "argv", ["ik", "--output", "json", "drives"]):
            with patch("ik.cli._resolve_token", return_value="t"):
                with patch("ik.cli.KDriveClient") as KC:
                    KC.return_value.list_drives.return_value = []
                    with patch("ik.cli.cmd_drives") as cd:
                        try:
                            _main()
                        except SystemExit:
                            pass
                        captured = cd.call_args.args[0]
                        assert captured.output == "json"

    def test_output_in_subcommand_position(self) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        with patch.object(sys, "argv", ["ik", "drives", "--output", "json"]):
            with patch("ik.cli._resolve_token", return_value="t"):
                with patch("ik.cli.KDriveClient") as KC:
                    KC.return_value.list_drives.return_value = []
                    with patch("ik.cli.cmd_drives") as cd:
                        try:
                            _main()
                        except SystemExit:
                            pass
                        captured = cd.call_args.args[0]
                        assert captured.output == "json"

    def test_profile_parsed_in_top_position(self, tmp_path) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t", "account_id": 1}},
                }
            )
        )
        with patch.object(sys, "argv", ["ik", "--profile", "work", "drives"]):
            with patch("ik.cli.CONFIG_PATH", str(config)):
                with patch("ik.cli._resolve_token", return_value="t") as rt:
                    # Patch account_id to None so main() doesn't write to
                    # the process environment (which would leak into later tests).
                    with patch("ik.cli._resolve_account_id", return_value=None):
                        with patch("ik.cli.KDriveClient") as KC:
                            KC.return_value.list_drives.return_value = []
                            with patch("ik.cli.cmd_drives") as cd:
                                try:
                                    _main()
                                except SystemExit:
                                    pass
                                captured = cd.call_args.args[0]
                                assert captured.profile == "work"
                                # _resolve_token receives the profile so it can read it.
                                assert rt.call_args.args[1] == "work"

    def test_profile_parsed_in_subcommand_position(self, tmp_path) -> None:
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t", "account_id": 1}},
                }
            )
        )
        with patch.object(sys, "argv", ["ik", "drives", "--profile", "work"]):
            with patch("ik.cli.CONFIG_PATH", str(config)):
                with patch("ik.cli._resolve_token", return_value="t") as rt:
                    with patch("ik.cli._resolve_account_id", return_value=None):
                        with patch("ik.cli.KDriveClient") as KC:
                            KC.return_value.list_drives.return_value = []
                            with patch("ik.cli.cmd_drives") as cd:
                                try:
                                    _main()
                                except SystemExit:
                                    pass
                                captured = cd.call_args.args[0]
                                assert captured.profile == "work"
                                assert rt.call_args.args[1] == "work"

    def test_profile_in_top_position_does_not_clobber_subcommand(self, tmp_path) -> None:
        """--profile at top reaches subcommands via argparse namespace merge."""
        import sys
        from unittest.mock import patch

        from ik.cli import main as _main

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t", "account_id": 1}},
                }
            )
        )
        with patch.object(sys, "argv", ["ik", "--profile", "work", "drives"]):
            with patch("ik.cli.CONFIG_PATH", str(config)):
                with patch("ik.cli._resolve_token", return_value="t") as rt:
                    with patch("ik.cli._resolve_account_id", return_value=None):
                        with patch("ik.cli.KDriveClient") as KC:
                            KC.return_value.list_drives.return_value = []
                            with patch("ik.cli.cmd_drives"):
                                try:
                                    _main()
                                except SystemExit:
                                    pass
                                # The token resolver saw the profile from the namespace.
                                assert rt.call_args.args[1] == "work"


# ── Profile config helpers ────────────────────────────────────────────


class TestMigrateV1ToV3:
    def test_passthrough_when_profiles_key_present(self) -> None:
        v3 = {"default": "work", "profiles": {"work": {"token": "x"}}}
        assert _migrate_v1_to_v3(v3) is v3

    def test_flat_token_and_account_id_migrated(self) -> None:
        result = _migrate_v1_to_v3({"token": "abc", "account_id": 5})
        assert result == {
            "default": "default",
            "profiles": {"default": {"token": "abc", "account_id": 5}},
        }

    def test_flat_token_only(self) -> None:
        result = _migrate_v1_to_v3({"token": "abc"})
        assert result == {
            "default": "default",
            "profiles": {"default": {"token": "abc"}},
        }

    def test_unknown_flat_keys_ignored(self) -> None:
        result = _migrate_v1_to_v3({"token": "abc", "garbage": 1})
        assert result == {
            "default": "default",
            "profiles": {"default": {"token": "abc"}},
        }

    def test_empty_dict_passthrough(self) -> None:
        assert _migrate_v1_to_v3({}) == {}

    def test_profiles_key_empty(self) -> None:
        assert _migrate_v1_to_v3({"profiles": {}}) == {"profiles": {}}


class TestReadConfig:
    def test_missing_file_returns_empty_dict(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(tmp_path / "absent.json"))
        assert _read_config() == {}

    def test_v1_flat_file_migrated_in_memory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"token": "abc", "account_id": 5}))
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        result = _read_config()
        assert result == {
            "default": "default",
            "profiles": {"default": {"token": "abc", "account_id": 5}},
        }

    def test_v3_passthrough(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        v3 = {
            "default": "work",
            "profiles": {"work": {"token": "w", "account_id": 1}},
        }
        config.write_text(json.dumps(v3))
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _read_config() == v3

    def test_corrupt_json_exits(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text("not json {{{")
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        with pytest.raises(SystemExit, match="Config file is corrupt"):
            _read_config()


class TestWriteConfig:
    def test_writes_indented(self, tmp_path) -> None:
        path = tmp_path / "sub" / "config.json"
        _write_config({"default": "x", "profiles": {}}, str(path))
        assert path.exists()
        # Newline-terminated, indent=2.
        content = path.read_text()
        assert content.endswith("\n")
        assert '  "default"' in content

    def test_creates_parent_dir(self, tmp_path) -> None:
        path = tmp_path / "deep" / "nested" / "config.json"
        _write_config({}, str(path))
        assert path.exists()


class TestWriteProfile:
    def test_creates_new_profile_in_empty_config(self) -> None:
        result = _write_profile({}, "work", "tok", 5)
        assert result == {
            "default": "work",
            "profiles": {"work": {"token": "tok", "account_id": 5}},
        }

    def test_appends_to_existing_profiles(self) -> None:
        config = {"default": "work", "profiles": {"work": {"token": "w", "account_id": 1}}}
        result = _write_profile(config, "personal", "p", 2)
        assert result["default"] == "work"  # not overwritten
        assert "work" in result["profiles"]
        assert result["profiles"]["personal"] == {"token": "p", "account_id": 2}

    def test_overwrites_existing_profile(self) -> None:
        config = {
            "default": "work",
            "profiles": {"work": {"token": "old", "account_id": 1}},
        }
        result = _write_profile(config, "work", "new", 9)
        assert result["profiles"]["work"] == {"token": "new", "account_id": 9}
        assert result["default"] == "work"

    def test_first_profile_becomes_default(self) -> None:
        result = _write_profile({"profiles": {}}, "alpha", "tok", None)
        assert result["default"] == "alpha"

    def test_existing_default_not_overwritten(self) -> None:
        config = {"default": "work", "profiles": {"work": {"token": "w"}}}
        result = _write_profile(config, "personal", "p", None)
        assert result["default"] == "work"  # still work, not personal

    def test_does_not_set_default_when_one_already_exists(self) -> None:
        config = {"default": "work", "profiles": {"work": {"token": "w"}}}
        result = _write_profile(config, "other", "o", None)
        assert result["default"] == "work"

    def test_set_default_if_first_false(self) -> None:
        result = _write_profile({}, "alpha", "tok", None, set_default_if_first=False)
        assert "default" not in result
        assert result["profiles"] == {"alpha": {"token": "tok", "account_id": None}}

    def test_account_id_none_stored_as_none(self) -> None:
        result = _write_profile({}, "work", "tok", None)
        assert result["profiles"]["work"]["account_id"] is None

    def test_does_not_mutate_input(self) -> None:
        config = {"default": "work", "profiles": {"work": {"token": "w"}}}
        snapshot = json.loads(json.dumps(config))
        _write_profile(config, "personal", "p", None)
        assert config == snapshot


# ── Profile resolution ────────────────────────────────────────────────


class TestResolveDefaultProfile:
    def test_config_with_default(self) -> None:
        config = {"default": "work", "profiles": {"work": {"token": "w"}}}
        assert _resolve_default_profile(config) == "work"

    def test_no_config_raises(self) -> None:
        with pytest.raises(_NoDefaultProfile):
            _resolve_default_profile({})

    def test_profiles_empty_raises(self) -> None:
        with pytest.raises(_NoDefaultProfile):
            _resolve_default_profile({"default": "work", "profiles": {}})

    def test_default_pointing_to_missing_profile_exits(self) -> None:
        config = {"default": "ghost", "profiles": {"work": {"token": "w"}}}
        with pytest.raises(SystemExit, match="Default profile 'ghost' not found"):
            _resolve_default_profile(config)

    def test_multiple_profiles_no_default_exits(self) -> None:
        config = {
            "profiles": {
                "work": {"token": "w"},
                "personal": {"token": "p"},
            }
        }
        with pytest.raises(SystemExit, match="Multiple profiles configured but no default"):
            _resolve_default_profile(config)


class TestValidateProfileName:
    def test_valid_names_pass(self) -> None:
        for name in ["work", "personal", "dev.1", "a-b-c", "X" * 64]:
            _validate_profile_name(name)  # should not raise

    def test_empty_string_exits(self) -> None:
        with pytest.raises(SystemExit, match="Invalid profile name"):
            _validate_profile_name("")

    def test_too_long_exits(self) -> None:
        with pytest.raises(SystemExit, match="Invalid profile name"):
            _validate_profile_name("a" * 65)

    def test_invalid_chars_exit(self) -> None:
        for name in ["work/personal", "../etc", "name with space", "name@host", "name!"]:
            with pytest.raises(SystemExit, match="Invalid profile name"):
                _validate_profile_name(name)


# ── Resolvers with profiles ───────────────────────────────────────────


class TestResolveTokenWithProfiles:
    def test_profile_token_used(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "from-profile", "account_id": 1}},
                }
            )
        )
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_token(ns(token=None), profile="work") == "from-profile"

    def test_flag_wins_over_profile_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "from-profile", "account_id": 1}},
                }
            )
        )
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_token(ns(token="from-flag"), profile="work") == "from-flag"

    def test_env_wins_over_profile_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "from-profile", "account_id": 1}},
                }
            )
        )
        monkeypatch.setenv("INFOMANIAK_TOKEN", "from-env")
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_token(ns(token=None), profile="work") == "from-env"

    def test_missing_profile_token_exits(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"profiles": {}}))
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        with pytest.raises(SystemExit, match="No API token found for profile 'work'"):
            _resolve_token(ns(token=None), profile="work")

    def test_token_flag_keeps_profile_account_id(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """--token wins for token; profile's account_id is still looked up."""
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "profile-tok", "account_id": 42}},
                }
            )
        )
        monkeypatch.delenv("INFOMANIAK_TOKEN", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        token = _resolve_token(ns(token="override-tok"), profile="work")
        assert token == "override-tok"
        # account_id is still resolved from the profile
        assert _resolve_account_id(profile="work") == 42


class TestResolveAccountIdWithProfiles:
    def test_profile_account_id_used(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t", "account_id": 99}},
                }
            )
        )
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_account_id(profile="work") == 99

    def test_env_wins_over_profile_account_id(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t", "account_id": 99}},
                }
            )
        )
        monkeypatch.setenv("INFOMANIAK_ACCOUNT_ID", "111")
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_account_id(profile="work") == 111

    def test_profile_with_no_account_id_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "default": "work",
                    "profiles": {"work": {"token": "t"}},
                }
            )
        )
        monkeypatch.delenv("INFOMANIAK_ACCOUNT_ID", raising=False)
        monkeypatch.setattr("ik.cli.CONFIG_PATH", str(config))

        assert _resolve_account_id(profile="work") is None


# ── `ik configure --list` ─────────────────────────────────────────────


class TestCmdConfigureList:
    def test_empty_config(self, capsys: pytest.CaptureFixture) -> None:
        _cmd_configure_list({}, output_format="text")
        assert capsys.readouterr().out == "(no profiles configured)\n"

    def test_lists_profiles_with_default_marker(self, capsys: pytest.CaptureFixture) -> None:
        config = {
            "default": "work",
            "profiles": {
                "work": {"token": "w", "account_id": 1},
                "personal": {"token": "p", "account_id": 2},
            },
        }
        _cmd_configure_list(config, output_format="text")
        out = capsys.readouterr().out
        assert "* work" in out
        assert "  personal" in out
        assert "1" in out
        assert "2" in out

    def test_missing_default_profile_marked(self, capsys: pytest.CaptureFixture) -> None:
        config = {
            "default": "ghost",
            "profiles": {"work": {"token": "w", "account_id": 1}},
        }
        _cmd_configure_list(config, output_format="text")
        out = capsys.readouterr().out
        # ghost is the default but not in profiles — list still renders existing ones
        assert "work" in out

    def test_json_output(self, capsys: pytest.CaptureFixture) -> None:
        config = {
            "default": "work",
            "profiles": {"work": {"token": "w", "account_id": 1}},
        }
        _cmd_configure_list(config, output_format="json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed == config

    def test_json_output_empty(self, capsys: pytest.CaptureFixture) -> None:
        _cmd_configure_list({}, output_format="json")
        out = capsys.readouterr().out
        assert json.loads(out) == {}
