"""Agent facade: builds loop with router/model selection and runs commands."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from axiom.agent.context import ContextManager
from axiom.agent.loop import AgentLoop, LoopConfig, LoopResult
from axiom.agent_roles import get_role
from axiom.core.logging import get_logger
from axiom.core.types import ToolResult
from axiom.models.router import RouteDecision
from axiom.permissions.manager import PermissionManager
from axiom.tools import filesystem, git, terminal, web_tools
from axiom.tools.process import ProcessManager
from axiom.tools.project import detect_project
from axiom.tools.registry import ToolContext, ToolRegistry

logger = get_logger("agent")


def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


READ_FILE_SCHEMA = _schema(
    {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
    ["path"],
)
WRITE_FILE_SCHEMA = _schema(
    {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]
)
EDIT_FILE_SCHEMA = _schema(
    {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"},
     "replace_all": {"type": "boolean"}},
    ["path", "old_text", "new_text"],
)
PATH_SCHEMA = _schema({"path": {"type": "string"}}, ["path"])
DIR_SCHEMA = _schema({"path": {"type": "string"}}, [])
QUERY_SCHEMA = _schema({"query": {"type": "string"}, "path": {"type": "string"}}, ["query"])
COMMAND_SCHEMA = _schema({"command": {"type": "string"}, "timeout": {"type": "number"}},
                         ["command"])
URL_SCHEMA = _schema({"url": {"type": "string"}}, ["url"])
EMPTY_SCHEMA = _schema({}, [])


class Agent:
    """Top-level agent: owns tools, permissions, model router, project info."""

    def __init__(
        self,
        workspace: Path | None = None,
        config: dict[str, Any] | None = None,
        provider: Any = None,
    ) -> None:
        self.workspace = (workspace or Path.cwd()).resolve()
        self.config = config or {}
        self.registry = ToolRegistry()
        self.permissions = PermissionManager(
            config=self.config.get("permissions"),
            security_mode=self.config.get("security", {}).get("mode", "NORMAL"),
        )
        self.processes = ProcessManager()
        self.project = detect_project(self.workspace)
        self.provider = provider  # injected provider; set via set_provider()
        self.route: RouteDecision | None = None
        self.mode = "BUILD"
        self._register_tools()

    # -- setup -----------------------------------------------------------
    def _register_tools(self) -> None:
        reg = self.registry
        reg.register("read_file", "Read a text file inside the workspace", READ_FILE_SCHEMA,
                     handler=filesystem.read_file, permission="filesystem.read")
        reg.register("write_file", "Create or overwrite a file in the workspace",
                     WRITE_FILE_SCHEMA, handler=filesystem.write_file,
                     permission="filesystem.write")
        reg.register("edit_file", "Replace exact text in a file", EDIT_FILE_SCHEMA,
                     handler=filesystem.edit_file, permission="filesystem.write")
        reg.register("delete_file", "Delete a file or directory", PATH_SCHEMA,
                     handler=filesystem.delete_file, permission="filesystem.delete")
        reg.register("list_directory", "List directory contents", DIR_SCHEMA,
                     handler=filesystem.list_directory, permission="filesystem.read")
        reg.register("search_files", "Search file names and contents", QUERY_SCHEMA,
                     handler=filesystem.search_files, permission="filesystem.read")
        reg.register("execute_command", "Execute a shell command in the workspace",
                     COMMAND_SCHEMA, handler=terminal.execute_command,
                     permission="terminal.execute", timeout=120.0)
        reg.register("web_fetch", "Fetch a URL and return its content", URL_SCHEMA,
                     handler=web_tools.web_fetch, permission="web.fetch")
        reg.register("web_search", "Search the web", QUERY_SCHEMA,
                     handler=web_tools.web_search, permission="web.search")
        for name, fn in (("git_status", git.git_status), ("git_diff", git.git_diff),
                         ("git_log", git.git_log), ("git_branch", git.git_branch)):
            reg.register(fn.__name__, f"Git read tool: {name}", EMPTY_SCHEMA,
                         handler=fn, permission="git.read")

    # -- model -------------------------------------------------------------
    def set_provider(self, provider: Any, model_id: str = "") -> None:
        self.provider = provider
        if model_id:
            self.config.setdefault("model", {})["model"] = model_id

    def build_tool_context(self) -> ToolContext:
        return ToolContext(
            workspace=str(self.workspace),
            permission_manager=self.permissions,
            config=self.config,
            emit=self._emit,
        )

    # -- execution -----------------------------------------------------------
    async def run_task(
        self, task: str, mode: str = "BUILD", max_iterations: int | None = None,
        on_event: Any = None,
    ) -> LoopResult:
        """Run the model-driven loop for a task."""
        if self.provider is None:
            raise RuntimeError("No model provider configured; use set_provider() first")
        self.mode = mode
        cfg = LoopConfig(max_iterations=max_iterations or 30, mode=mode)
        # PLAN/REVIEW modes: strip write tools
        if mode in ("PLAN", "REVIEW"):
            for name in ("write_file", "edit_file", "delete_file"):
                self.registry.unregister(name)
        loop = AgentLoop(
            provider=self.provider,
            registry=self.registry,
            tool_context=self.build_tool_context(),
            permission_manager=self.permissions,
            config=cfg,
            project_summary=self.project.summary(),
            on_event=on_event or self._on_loop_event,
        )
        return await loop.run(task)

    # -- sub-agent runner (for orchestrator) ----------------------------------
    def make_subtask_runner(self, role: str):
        """Build a runner for the orchestrator executing subtasks with a role."""
        async def runner(subtask) -> str:
            role_def = get_role(role)
            if role_def is None:
                return f"Error: unknown role {role}"
            sub_permissions = PermissionManager(
                config={**(self.config.get("permissions") or {}), **role_def.permissions}
            )
            sub_registry = ToolRegistry()
            for spec in self.registry.list_tools():
                if role_def.tools and spec.name not in role_def.tools:
                    continue
                sub_registry.register(spec.name, spec.description, spec.parameters,
                                      handler=spec.handler, permission=spec.permission,
                                      timeout=spec.timeout)
            sub_context = ToolContext(
                workspace=str(self.workspace), permission_manager=sub_permissions,
                config=self.config,
            )
            sub_loop = AgentLoop(
                provider=self.provider,
                registry=sub_registry,
                tool_context=sub_context,
                permission_manager=sub_permissions,
                config=LoopConfig(max_iterations=min(15, role_def.max_iterations),
                                  mode=role_def.mode),
                project_summary=self.project.summary(),
            )
            result = await sub_loop.run(
                f"{subtask.description}\n\n(Role: {role_def.name}) {role_def.system_prompt}"
            )
            return result.final_text or result.error or f"[{result.status.value}]"
        return runner

    # -- verification -----------------------------------------------------------
    async def run_tests(self, command: str | None = None) -> dict[str, Any]:
        """Detect and run the test suite. Returns a report dict."""
        if command is None:
            if self.project.test_framework == "pytest" or self.project.language == "Python":
                command = "python -m pytest -q --no-header"
            elif self.project.test_framework == "cargo test":
                command = "cargo test"
            elif self.project.test_framework == "go test":
                command = "go test ./..."
            elif self.project.language.startswith("JS") and self.project.test_framework:
                command = "npm test"
            else:
                return {"ran": False, "reason": "no test framework detected"}
        start = time.monotonic()
        code, out, err = await terminal.run_shell(command, str(self.workspace), timeout=600.0)
        return {
            "ran": True,
            "command": command,
            "exit_code": code,
            "output": (out + err)[-5000:],
            "duration": time.monotonic() - start,
        }


    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        logger.debug("event %s %s", event_type, {k: str(v)[:80] for k, v in data.items()})

    def _on_loop_event(self, event_type: str, data: dict[str, Any]) -> None:
        pass  # default sink: logging only
