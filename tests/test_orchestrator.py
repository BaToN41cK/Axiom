"""Multi-agent orchestrator tests with a mock task runner."""

from __future__ import annotations

import asyncio

import pytest

from axiom.agent_roles import get_role, list_roles
from axiom.orchestrator import Orchestrator
from axiom.permissions.manager import PermissionManager


class TestRoles:
    def test_all_spec_roles_exist(self) -> None:
        roles = list_roles()
        for expected in ("orchestrator", "planner", "coder", "reviewer", "researcher",
                         "tester", "explorer", "debugger", "security", "architect"):
            assert expected in roles

    def test_reviewer_is_read_only(self) -> None:
        reviewer = get_role("reviewer")
        assert reviewer.permissions.get("filesystem.write") == "deny"


def make_orchestrator(results: dict[str, str]) -> Orchestrator:
    async def runner(subtask) -> str:
        return results.get(subtask.role, f"done: {subtask.description}")

    return Orchestrator(task_runner=runner, max_agents=5, max_depth=2,
                        parent_permissions=PermissionManager(config={}))


class TestOrchestratorRun:
    def test_sync_plan_three_agents(self) -> None:
        orch = Orchestrator()
        tasks = orch.create_plan("проанализируй проект и проведи review", num_agents=3)
        assert len(tasks) >= 3
        roles = {t.role for t in tasks}
        assert "reviewer" in roles or "security" in roles

    @pytest.mark.asyncio
    async def test_run_synthesizes(self) -> None:
        orch = make_orchestrator({"explorer": "structure mapped", "reviewer": "2 bugs found"})
        report = await orch.run("review the project")
        assert "ORCHESTRATOR REPORT" in report
        assert "structure mapped" in report
        assert orch.get_status()["total_agents"] >= 2
        assert all(a.status == "done" for a in orch.agents)

    @pytest.mark.asyncio
    async def test_max_agents_limit(self) -> None:
        async def runner(subtask):
            return "x"

        orch = Orchestrator(task_runner=runner, max_agents=2)
        orch.create_plan("analyze and test and fix the architecture")
        # manually saturate
        from axiom.orchestrator import AgentInstance

        orch._agents = [AgentInstance(), AgentInstance()]
        report = await orch.run("analyze and test and fix the architecture")
        assert "max agent limit" in report
        # Agents beyond the limit must report max agent limit.
        assert any(a.status == "done" or "max agent limit" in a.output for a in orch.agents)


    @pytest.mark.asyncio
    async def test_failing_subtask_reported(self) -> None:
        async def runner(subtask):
            raise RuntimeError("boom")

        orch = Orchestrator(task_runner=runner)
        report = await orch.run("review project")
        assert "Error: boom" in report
        assert orch.get_status()["failed"] >= 1

    def test_no_runner_raises(self) -> None:
        orch = Orchestrator()
        raised = False
        try:
            asyncio.run(orch.run("x"))
        except ValueError:
            raised = True
        assert raised
