"""Tests for the `ik completion <shell>` subcommand and the
shipped completion scripts.

The three static scripts (ik.bash, ik.zsh, ik.fish) are checked in
and shipped as package data. We verify:
- The subcommand dispatches to the right script.
- The scripts contain the expected register-the-completer tokens.
- The bash script reads from `ik configure --list --output json`
  so dynamic profile completion works.
- All three scripts are reachable via importlib.resources (i.e. they
  were actually shipped as package data).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import pytest

from ik.cli import cmd_completion


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _run_ik(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ik.cli", *args],
        capture_output=True,
        text=True,
    )


# ── direct unit test of cmd_completion ───────────────────────────────


class TestCmdCompletion:
    def test_bash_writes_to_stdout(self, capsys: pytest.CaptureFixture) -> None:
        # Patch the resource lookup to return a known string so the test
        # doesn't depend on importlib.resources (which is also covered below).
        from ik import cli

        original = cli.resources.files

        class FakeFiles:
            def joinpath(self, name: str) -> "_FakeRes":
                return _FakeRes(f"FAKE-SCRIPT:{name}\n")

        class _FakeRes:
            def __init__(self, text: str) -> None:
                self.text = text

            def read_text(self) -> str:
                return self.text

        try:
            cli.resources.files = lambda pkg: FakeFiles()  # type: ignore[assignment]
            cmd_completion(ns(shell="bash"))
        finally:
            cli.resources.files = original  # type: ignore[assignment]

        captured = capsys.readouterr()
        assert captured.out == "FAKE-SCRIPT:ik.bash\n"


# ── subprocess-level smoke tests ──────────────────────────────────────


class TestCompletionScriptsViaSubprocess:
    def test_bash_prints_script(self) -> None:
        result = _run_ik("completion", "bash")
        assert result.returncode == 0
        assert result.stdout.startswith("# ik bash completion")
        assert "complete -F _ik ik" in result.stdout
        assert "_ik_profiles" in result.stdout

    def test_zsh_prints_script(self) -> None:
        result = _run_ik("completion", "zsh")
        assert result.returncode == 0
        assert result.stdout.startswith("#compdef ik")
        assert "_ik()" in result.stdout
        assert "_ik_profiles" in result.stdout

    def test_fish_prints_script(self) -> None:
        result = _run_ik("completion", "fish")
        assert result.returncode == 0
        assert "ik fish completion" in result.stdout
        assert "complete -c ik" in result.stdout
        assert "__ik_profiles" in result.stdout

    def test_bash_script_reads_profile_list_json(self) -> None:
        result = _run_ik("completion", "bash")
        # The bash script must call back to the binary to list profiles,
        # otherwise dynamic profile-name completion is broken.
        assert "ik configure --list --output json" in result.stdout
        assert '"profiles"' in result.stdout

    def test_unknown_shell_exits_nonzero(self) -> None:
        result = _run_ik("completion", "powershell")
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower()


# ── package data accessibility ───────────────────────────────────────


class TestCompletionShippedAsPackageData:
    def test_all_three_files_reachable(self) -> None:
        from importlib import resources

        files = {
            "bash": "ik.bash",
            "zsh": "ik.zsh",
            "fish": "ik.fish",
        }
        for shell, name in files.items():
            text = resources.files("ik.completions").joinpath(name).read_text()
            assert len(text) > 50, f"{shell} script is unexpectedly short"
            assert text, f"{shell} script is empty"
