"""CLI smoke tests (no real API needed)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from axiom.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLI:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "axiom" in result.output

    def test_models_listing(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--models"])
        assert result.exit_code == 0
        assert "GPT-OSS-120B" in result.output
        assert "PROVIDERS" in result.output

    def test_doctor_runs(self, runner: CliRunner, tmp_path) -> None:
        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(main, ["--doctor"])
        finally:
            os.chdir(old_cwd)
        assert "AXIOM DOCTOR" in result.output

    def test_oneshot_requires_key(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["do something"])
        assert result.exit_code == 1
        assert "API key" in result.output

    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--doctor" in result.output
