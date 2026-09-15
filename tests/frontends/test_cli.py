"""CLI frontend tests (-p, --json, pipe) with a fake ChatSession (no network)."""

from __future__ import annotations

import io
import json
import sys
import sys as _sys

import pytest

import axiom.frontends.cli.main as _cli_shim  # noqa: F401

cli_module = _sys.modules["axiom.frontends.cli.main"]
from axiom.core.events import ContentChunk, Done
from axiom.core.models import ModelInfo
from axiom.core.state import GenerationState


class FakeSession:
    def __init__(self, config) -> None:
        self.config = config
        from types import SimpleNamespace

        self.client = SimpleNamespace(base_url="http://127.0.0.1:11434")

    async def startup(self):
        from axiom.core.chat import StartupReport

        model = ModelInfo(name="test-model:latest", capabilities=[])
        return StartupReport(
            ollama_available=True, version="0.0-test", models=[model], selected=model
        )

    async def send(self, prompt, **kwargs):
        yield ContentChunk(text="hello world")
        yield Done(state=GenerationState.COMPLETED, duration_ms=10)


@pytest.fixture()
def fake_session(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("AXIOM_HOME", str(tmp_path / "axiom-home"))
    monkeypatch.setattr(cli_module, "ChatSession", FakeSession)
    return FakeSession


class PipedStdin(io.StringIO):
    def isatty(self) -> bool:
        return False


class TtyStdin(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_prompt_flag_prints_answer(fake_session, capsys):
    code = cli_module.main(["-p", "hi"])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "hello world" in out


def test_json_mode_emits_ndjson(fake_session, capsys):
    code = cli_module.main(["--json", "-p", "hi"])
    assert code == 0
    out, _ = capsys.readouterr()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) >= 2
    payloads = [json.loads(ln) for ln in lines]
    types = {p.get("type") for p in payloads}
    assert "content" in types and "done" in types


def test_pipe_mode_reads_stdin(fake_session, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", PipedStdin("piped question"))
    code = cli_module.main([])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "hello world" in out


def test_no_prompt_returns_usage(fake_session, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", TtyStdin(""))
    code = cli_module.main([])
    assert code == cli_module.EXIT_USAGE


def test_list_models(fake_session, capsys):
    code = cli_module.main(["--list-models"])
    assert code == 0
    _, err = capsys.readouterr()
    assert "test-model" in err
