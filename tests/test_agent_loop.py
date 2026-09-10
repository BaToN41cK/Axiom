"""Real-behaviour tests for the agent loop using MockProvider."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom.agent.agent import Agent
from axiom.agent.loop import AgentLoop, LoopConfig
from axiom.models.mock import MockProvider
from axiom.permissions.manager import PermissionManager
from axiom.tools.registry import ToolContext, ToolRegistry


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def make_loop(workspace: Path, provider: MockProvider, permissions: PermissionManager | None = None,
              registry: ToolRegistry | None = None) -> AgentLoop:
    registry = registry or Agent(workspace=workspace).registry
    permissions = permissions or PermissionManager(config={
        "filesystem.read": "allow", "filesystem.write": "allow",
        "terminal.execute": "allow",
    })
    ctx = ToolContext(workspace=str(workspace), permission_manager=permissions, config={})
    return AgentLoop(
        provider=provider, registry=registry, tool_context=ctx,
        permission_manager=permissions, config=LoopConfig(max_iterations=10),
        project_summary="Python, pytest",
    )


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_completes_with_text_only(self, workspace: Path) -> None:
        provider = MockProvider(script=[{"content": "The answer is 42."}])
        loop = make_loop(workspace, provider)
        result = await loop.run("What is the answer?")
        assert result.status.value == "complete"
        assert result.final_text == "The answer is 42."
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_tool_call_round_trip(self, workspace: Path) -> None:
        (workspace / "notes.txt").write_text("hello", encoding="utf-8")
        provider = MockProvider(script=[
            {"tool_calls": [{"id": "c1", "name": "read_file", "arguments": {"path": "notes.txt"}}]},
            {"content": "The file contains: hello"},
        ])
        loop = make_loop(workspace, provider)
        result = await loop.run("Read notes.txt")
        assert result.status.value == "complete"
        assert "hello" in result.final_text
        assert result.tool_calls == 1
        # Provider saw the tool result in the follow-up message.
        second_call_messages = provider.calls[1]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_messages and "hello" in tool_messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_permission_denied_stops_eventually(self, workspace: Path) -> None:
        provider = MockProvider(script=[
            {"tool_calls": [{"id": "c1", "name": "write_file",
                             "arguments": {"path": "x.txt", "content": "data"}}]},
            {"tool_calls": [{"id": "c2", "name": "write_file",
                             "arguments": {"path": "y.txt", "content": "data"}}]},
            {"tool_calls": [{"id": "c3", "name": "write_file",
                             "arguments": {"path": "z.txt", "content": "data"}}]},
        ])
        permissions = PermissionManager(config={"filesystem.write": "deny"})
        loop = make_loop(workspace, provider, permissions=permissions)
        result = await loop.run("Write files")
        assert result.status.value == "failed"
        assert "denied" in result.error
        assert not (workspace / "x.txt").exists()

    @pytest.mark.asyncio
    async def test_write_file_via_tool(self, workspace: Path) -> None:
        provider = MockProvider(script=[
            {"tool_calls": [{"id": "c1", "name": "write_file",
                             "arguments": {"path": "out/new.txt", "content": "made by agent"}}]},
            {"content": "done"},
        ])
        loop = make_loop(workspace, provider)
        result = await loop.run("Create out/new.txt")
        assert result.status.value == "complete"
        assert (workspace / "out" / "new.txt").read_text(encoding="utf-8") == "made by agent"

    @pytest.mark.asyncio
    async def test_cancellation(self, workspace: Path) -> None:
        provider = MockProvider(script=[
            {"tool_calls": [{"id": "c1", "name": "read_file", "arguments": {"path": "a.txt"}}]},
        ])
        loop = make_loop(workspace, provider)
        loop.cancel()
        result = await loop.run("task")
        assert result.status.value == "cancelled"


class TestAgentModes:
    @pytest.mark.asyncio
    async def test_plan_mode_strips_write_tools(self, workspace: Path) -> None:
        agent = Agent(workspace=workspace, provider=MockProvider(script=[{"content": "plan only"}]))
        result = await agent.run_task("analyze", mode="PLAN")
        assert result.status.value == "complete"
        assert agent.registry.get("write_file") is None
        assert agent.registry.get("read_file") is not None
