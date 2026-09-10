"""Agent roles: role definitions with tools and permission overrides."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentRole:
    """A named agent role with tool access and permission overrides."""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    permissions: dict[str, str] = field(default_factory=dict)
    mode: str = "BUILD"
    max_iterations: int = 30


ROLES: dict[str, AgentRole] = {
    "orchestrator": AgentRole(
        name="orchestrator",
        description="Decomposes complex tasks and manages sub-agents",
        system_prompt=(
            "You are the orchestrator. Decompose the task into subtasks, assign them "
            "to sub-agents, verify results and synthesize the final report. "
            "You do not modify files yourself."
        ),
        tools=["read_file", "list_directory", "search_files", "execute_command"],
        permissions={"filesystem.write": "deny", "agent.spawn": "allow"},
        mode="ORCHESTRATOR",
    ),
    "planner": AgentRole(
        name="planner",
        description="Analyzes the project and produces an action plan",
        system_prompt=(
            "You are the planner. Inspect the project and produce a concise, "
            "ordered plan. Read-only: you never modify files."
        ),
        tools=["read_file", "list_directory", "search_files", "git_status", "git_diff"],
        permissions={"filesystem.write": "deny", "filesystem.delete": "deny",
                     "terminal.execute": "allow"},
        mode="PLAN",
    ),
    "coder": AgentRole(
        name="coder",
        description="Implements code changes",
        system_prompt=(
            "You are the coder. Implement the requested changes with precise edits. "
            "Verify by reading files before editing and running tests after."
        ),
        tools=["read_file", "write_file", "edit_file", "list_directory", "search_files",
               "execute_command"],
        permissions={"filesystem.write": "allow"},
        mode="BUILD",
    ),
    "reviewer": AgentRole(
        name="reviewer",
        description="Reviews code for bugs, security and quality",
        system_prompt=(
            "You are the reviewer. Analyze diffs and code for bugs, security issues, "
            "performance problems and missing tests. Report findings with severity "
            "HIGH/MEDIUM/LOW. Read-only."
        ),
        tools=["read_file", "list_directory", "search_files", "git_diff", "git_log"],
        permissions={"filesystem.write": "deny", "filesystem.delete": "deny"},
        mode="REVIEW",
    ),
    "researcher": AgentRole(
        name="researcher",
        description="Researches documentation and web resources",
        system_prompt=(
            "You are the researcher. Use web tools to find authoritative information "
            "and summarize findings with sources."
        ),
        tools=["web_fetch", "web_search", "read_file"],
        permissions={"web.fetch": "allow", "filesystem.write": "deny"},
        mode="AUTO",
    ),
    "tester": AgentRole(
        name="tester",
        description="Runs and repairs tests",
        system_prompt=(
            "You are the tester. Discover the test framework, run tests, analyze "
            "failures, fix them and re-run until green or the repair limit."
        ),
        tools=["read_file", "edit_file", "write_file", "execute_command", "list_directory",
               "search_files"],
        permissions={"filesystem.write": "allow", "terminal.execute": "allow"},
        mode="BUILD",
    ),
    "explorer": AgentRole(
        name="explorer",
        description="Maps project structure and key files",
        system_prompt=(
            "You are the explorer. Map the project: structure, entry points, "
            "dependencies and conventions. Read-only."
        ),
        tools=["list_directory", "read_file", "search_files"],
        permissions={"filesystem.write": "deny"},
        mode="PLAN",
    ),
    "debugger": AgentRole(
        name="debugger",
        description="Diagnoses and fixes bugs",
        system_prompt=(
            "You are the debugger. Reproduce the issue, isolate root cause, "
            "apply a minimal fix and verify with tests."
        ),
        tools=["read_file", "edit_file", "execute_command", "search_files", "list_directory"],
        permissions={"filesystem.write": "allow"},
        mode="BUILD",
    ),
    "security": AgentRole(
        name="security",
        description="Security review specialist",
        system_prompt=(
            "You are the security reviewer. Look for injection risks, path traversal, "
            "secrets handling, unsafe subprocess usage and permission weaknesses."
        ),
        tools=["read_file", "search_files", "list_directory", "git_diff"],
        permissions={"filesystem.write": "deny"},
        mode="REVIEW",
    ),
    "architect": AgentRole(
        name="architect",
        description="Architecture analysis and design",
        system_prompt=(
            "You are the architect. Assess module boundaries, dependencies and "
            "scalability; propose concrete structural improvements."
        ),
        tools=["read_file", "list_directory", "search_files"],
        permissions={"filesystem.write": "deny"},
        mode="PLAN",
    ),
}


def get_role(name: str) -> AgentRole | None:
    return ROLES.get(name.lower())


def list_roles() -> list[str]:
    return sorted(ROLES)
