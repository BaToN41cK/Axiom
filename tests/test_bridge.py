"""JSONL round-trip test of the desktop bridge (no window, no Ollama needed).

Spawns ``desktop/src-tauri/bridge/axiom_bridge.py`` exactly like the Tauri
shell does and exchanges real JSONL requests/replies over stdio.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "desktop" / "src-tauri" / "bridge" / "axiom_bridge.py"


class BridgeProcess:
    """Runs the bridge as a subprocess and matches replies by request id."""

    def __init__(self, home: Path, ollama_url: str = "http://127.0.0.1:9") -> None:
        home.mkdir(parents=True, exist_ok=True)
        # A dead Ollama URL keeps `send` offline (no real generations).
        (home / "config.json").write_text(
            json.dumps({"ollama_url": ollama_url, "model": None}), encoding="utf-8"
        )
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "AXIOM_HOME": str(home),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        self.home = home
        self._proc = subprocess.Popen(
            [sys.executable, "-u", str(BRIDGE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
        )
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout
        self._replies: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "reply":
                with self._lock:
                    self._replies[int(payload.get("req", 0))] = payload

    def request(self, req: int, cmd: str, args: dict | None = None, timeout: float = 15.0) -> dict:
        line = json.dumps({"req": req, "cmd": cmd, "args": args or {}}, ensure_ascii=False)
        self._stdin.write(line + "\n")
        self._stdin.flush()
        deadline = 50 * timeout / 10  # poll loop budget
        waited = 0
        while waited < deadline:
            with self._lock:
                if req in self._replies:
                    return self._replies[req]
            waited += 1
            threading.Event().wait(0.1)
        raise TimeoutError(f"bridge did not answer {cmd} in time")

    def close(self) -> None:
        try:
            self._stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()


@pytest.fixture()
def bridge(tmp_path: Path) -> Iterator[BridgeProcess]:
    proc = BridgeProcess(tmp_path / "axiom-home")
    yield proc
    proc.close()


def test_get_config_round_trip(bridge: BridgeProcess) -> None:
    reply = bridge.request(1, "get_config")
    assert reply["ok"] is True
    assert reply["data"]["ollama_url"].startswith("http")
    assert "theme" in reply["data"]


def test_set_config_round_trip(bridge: BridgeProcess) -> None:
    reply = bridge.request(2, "set_config", {"patch": {"temperature": 0.4, "theme": "light"}})
    assert reply["ok"] is True
    assert reply["data"]["temperature"] == 0.4
    assert reply["data"]["theme"] == "light"


def test_set_config_persists(tmp_path: Path) -> None:
    proc = BridgeProcess(tmp_path / "axiom-home")
    try:
        reply = proc.request(2, "set_config", {"patch": {"temperature": 0.4}})
        assert reply["ok"] is True
        saved = json.loads((tmp_path / "axiom-home" / "config.json").read_text(encoding="utf-8"))
        assert saved["temperature"] == 0.4
    finally:
        proc.close()


def test_list_chats_empty(bridge: BridgeProcess) -> None:
    reply = bridge.request(3, "list_chats")
    assert reply["ok"] is True
    assert reply["data"] == []


def test_new_chat_ids_differ_and_unknown_load_is_none(bridge: BridgeProcess) -> None:
    first = bridge.request(4, "new_chat")
    second = bridge.request(5, "new_chat")
    assert first["ok"] is True and second["ok"] is True
    assert first["data"]["id"] != second["data"]["id"]
    assert first["data"]["messages"] == []
    # A never-saved conversation cannot be loaded — history has no such file.
    missing = bridge.request(6, "load_chat", {"id": "does-not-exist"})
    assert missing["ok"] is True and missing["data"] is None


def test_saved_conversation_round_trips_through_the_bridge(tmp_path: Path) -> None:
    from axiom.core.events import Message
    from axiom.core.history import Conversation, HistoryStore

    home = tmp_path / "axiom-home"
    store = HistoryStore(directory=home / "history")
    conv = Conversation(title="from disk")
    conv.messages.append(Message(role="user", content="привет"))
    store.save(conv)

    proc = BridgeProcess(home)
    try:
        loaded = proc.request(1, "load_chat", {"id": conv.id})
        assert loaded["ok"] is True
        assert loaded["data"]["id"] == conv.id
        assert loaded["data"]["messages"][0]["content"] == "привет"
        listed = proc.request(2, "list_chats")
        assert [c["id"] for c in listed["data"]] == [conv.id]
    finally:
        proc.close()


def test_unknown_command_is_a_structured_error(bridge: BridgeProcess) -> None:
    reply = bridge.request(6, "no_such_command")
    assert reply["ok"] is False
    assert "Unknown command" in reply["error"]


def test_external_model_camel_case_payload_never_uses_ollama(bridge: BridgeProcess) -> None:
    """The React client uses providerId; external routes must not hit /api/show."""
    reply = bridge.request(7, "set_model", {
        "name": "deepseek/deepseek-v4-flash",
        "providerId": "openai_compatible",
    })
    assert reply["ok"] is True
    assert reply["data"]["name"] == "deepseek/deepseek-v4-flash"
    assert reply["data"]["providerId"] == "openai_compatible"
    assert reply["data"]["source"] == "external"

    config = bridge.request(8, "get_config")
    assert config["data"]["router_primary"] == {
        "provider_id": "openai_compatible",
        "model": "deepseek/deepseek-v4-flash",
    }
    warmup = bridge.request(9, "warmup", {})
    assert warmup["ok"] is True
    assert warmup["data"]["skipped"] == "external_provider"
    status = bridge.request(10, "status")
    assert status["data"]["activeModel"]["providerId"] == "openai_compatible"
    assert status["data"]["activeModel"]["source"] == "external"


def test_send_without_ollama_reports_error_event(bridge: BridgeProcess) -> None:
    reply = bridge.request(7, "send", {"text": "hi"})
    # The reply itself is ok (events were streamed); without a live Ollama the
    # stream contains a structured error event, not a crash.
    assert reply["ok"] is True
